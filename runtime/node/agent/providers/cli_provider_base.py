"""Abstract base class for CLI-based agent providers.

Provides shared infrastructure for providers that shell out to an agentic CLI
binary (Claude Code, Gemini CLI, Copilot CLI, etc.):

- Binary discovery and validation
- Thread-safe persistent session management
- Subprocess execution with NDJSON streaming
- Idle/stall detection with automatic session recovery
- Workspace snapshot diffing for file change tracking
- MCP server configuration forwarding
- Gitignore-aware file filtering
- Token usage tracking
"""

import json
import logging
import os
import re
import signal
import subprocess
import shutil
import tempfile
import threading
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from entity.configs import AgentConfig
from entity.configs.node.tooling import McpLocalConfig, McpRemoteConfig, ToolingConfig
from entity.messages import Message, MessageRole
from entity.tool_spec import ToolSpec
from runtime.node.agent.providers.base import ModelProvider
from runtime.node.agent.providers.response import ModelResponse
from utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)


@dataclass
class NormalizedEvent:
    """Normalized NDJSON event that all CLI providers produce.

    Each CLI emits different event schemas.  Subclasses implement
    ``_normalize_event()`` to convert raw events into this common format
    so the streaming and logging infrastructure remains provider-agnostic.
    """

    type: str  # "init" | "text" | "tool_start" | "tool_end" | "result" | "error"
    session_id: Optional[str] = None
    text: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[dict] = None
    tool_result: Optional[str] = None
    tool_id: Optional[str] = None
    result_text: Optional[str] = None
    usage: Optional[dict] = None
    raw: dict = field(default_factory=dict)


class CliProviderBase(ModelProvider):
    """Abstract base class for providers that shell out to an agentic CLI binary.

    Subclasses must set the following class attributes and implement the
    abstract methods listed below.

    Class attributes::

        CLI_BINARY_NAME   – executable name, e.g. ``"claude"``
        CLI_FALLBACK_PATHS – list of absolute paths to search if not in PATH
        PROVIDER_NAME     – registry key, e.g. ``"claude-code"``
        SESSIONS_FILE     – workspace file for persisting sessions

    Abstract methods::

        _resolve_model_flag, _build_command, _build_resume_command,
        _normalize_event, extract_token_usage, _build_mcp_config_dict
    """

    # --- Subclass-provided class attributes ---
    CLI_BINARY_NAME: str = ""
    CLI_FALLBACK_PATHS: List[str] = []
    PROVIDER_NAME: str = ""
    SESSIONS_FILE: str = ".cli_sessions.json"

    # --- Thread-safe session storage (per-subclass via __init_subclass__) ---
    _sessions: Dict[str, str] = {}
    _sessions_lock: threading.Lock = threading.Lock()

    def __init_subclass__(cls, **kwargs):
        """Give each subclass its own independent session storage."""
        super().__init_subclass__(**kwargs)
        cls._sessions = {}
        cls._sessions_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    @classmethod
    def get_session(cls, node_id: str) -> Optional[str]:
        with cls._sessions_lock:
            return cls._sessions.get(node_id)

    @classmethod
    def set_session(cls, node_id: str, session_id: str) -> None:
        with cls._sessions_lock:
            cls._sessions[node_id] = session_id

    @classmethod
    def clear_session(cls, node_id: str) -> None:
        with cls._sessions_lock:
            cls._sessions.pop(node_id, None)

    @classmethod
    def clear_all_sessions(cls) -> None:
        with cls._sessions_lock:
            cls._sessions.clear()

    @classmethod
    def save_sessions_to_workspace(cls, workspace_root: str) -> None:
        path = Path(workspace_root) / cls.SESSIONS_FILE
        with cls._sessions_lock:
            if cls._sessions:
                path.write_text(json.dumps(cls._sessions))

    @classmethod
    def load_sessions_from_workspace(cls, workspace_root: str) -> None:
        path = Path(workspace_root) / cls.SESSIONS_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text())
                with cls._sessions_lock:
                    cls._sessions.update(data)
            except (json.JSONDecodeError, OSError):
                pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._binary_path = self._find_binary()
        self._model_flag = self._resolve_model_flag()

    def _find_binary(self) -> str:
        """Locate the CLI binary."""
        path = shutil.which(self.CLI_BINARY_NAME)
        if path:
            return path
        for candidate in self.CLI_FALLBACK_PATHS:
            expanded = os.path.expanduser(candidate)
            if os.path.isfile(expanded):
                return expanded
        raise FileNotFoundError(
            f"{self.CLI_BINARY_NAME} CLI not found. "
            f"Install it or ensure '{self.CLI_BINARY_NAME}' is in PATH."
        )

    @property
    def is_cli_provider(self) -> bool:
        """Trait flag used by agent_executor to detect CLI-based providers."""
        return True

    def create_client(self):
        return self._binary_path

    # ------------------------------------------------------------------
    # Abstract methods — subclasses MUST implement
    # ------------------------------------------------------------------

    @abstractmethod
    def _resolve_model_flag(self) -> Optional[str]:
        """Map ``self.model_name`` to the CLI-specific ``--model`` value."""

    @abstractmethod
    def _build_command(
        self,
        client: str,
        prompt: str,
        session_id: Optional[str],
        mcp_config_path: Optional[str],
        max_turns: int,
        **kwargs,
    ) -> List[str]:
        """Build the subprocess command list for a fresh or resumed call."""

    @abstractmethod
    def _build_resume_command(
        self,
        client: str,
        session_id: str,
        prompt: str,
        mcp_config_path: Optional[str],
        max_turns: int,
        **kwargs,
    ) -> List[str]:
        """Build the subprocess command for resuming after stall or completion check."""

    @abstractmethod
    def _normalize_event(self, raw_event: dict) -> NormalizedEvent:
        """Convert a raw NDJSON event dict into a ``NormalizedEvent``."""

    @abstractmethod
    def _build_mcp_config_dict(self, servers: Dict[str, Any]) -> dict:
        """Wrap the *servers* dict into the CLI-specific MCP config JSON structure."""

    # ------------------------------------------------------------------
    # call_model — shared orchestration
    # ------------------------------------------------------------------

    def call_model(
        self,
        client: str,
        conversation: List[Message],
        timeline: List[Any],
        tool_specs: Optional[List[ToolSpec]] = None,
        **kwargs,
    ) -> ModelResponse:
        stream_callback = kwargs.pop("stream_callback", None)
        session_id = kwargs.pop("session_id", "")
        server_port = kwargs.pop("server_port", 8000)
        node_id = getattr(self.config, "node_id", None)
        workspace_root = getattr(self.config, "workspace_root", None)

        existing_session = self.get_session(node_id) if node_id else None
        is_continuation = existing_session is not None

        tooling_configs = getattr(self.config, "tooling", None) or []
        mcp_config_path = self._create_mcp_config(
            node_id or "", session_id, server_port,
            tooling_configs=tooling_configs,
            workspace_root=workspace_root,
        )

        prompt = self._build_prompt(
            conversation, tool_specs,
            is_continuation=is_continuation,
            workspace_root=workspace_root,
        )

        configured_turns = getattr(self.config, "max_turns", None)
        max_turns = configured_turns or (40 if existing_session else 30)

        cmd = self._build_command(
            client, prompt, existing_session, mcp_config_path, max_turns,
        )

        cwd = None
        if workspace_root:
            ws_path = Path(workspace_root)
            ws_path.mkdir(parents=True, exist_ok=True)
            cwd = str(ws_path)

        before_snapshot = self._snapshot_workspace(cwd) if cwd else {}

        timeout = kwargs.pop("timeout", 600)
        idle_timeout = kwargs.pop("idle_timeout", 900)

        try:
            raw_response, stderr_text = self._run_streaming(
                cmd, cwd, timeout, stream_callback,
                idle_timeout=idle_timeout,
            )

            if raw_response.get("error") == "timeout":
                if node_id and not existing_session:
                    self.clear_session(node_id)
                return ModelResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content=f"[Error: {self.CLI_BINARY_NAME} CLI timed out]",
                    ),
                    raw_response=raw_response,
                )

            if raw_response.get("error") == "stall":
                stall_session = raw_response.get("session_id") or (
                    self.get_session(node_id) if node_id else None
                )
                if stall_session:
                    if stream_callback:
                        stream_callback("stall_detected", {
                            "session_id": stall_session,
                            "idle_timeout": idle_timeout,
                        })
                    raw_response, stderr_text = self._resume_after_stall(
                        client, stall_session, cwd, timeout, stream_callback,
                        mcp_config_path, idle_timeout=idle_timeout,
                    )
                    if raw_response.get("error") in ("timeout", "stall"):
                        if node_id:
                            self.clear_session(node_id)
                        return ModelResponse(
                            message=Message(
                                role=MessageRole.ASSISTANT,
                                content="[Error: Agent stalled and recovery failed]",
                            ),
                            raw_response=raw_response,
                        )
                else:
                    return ModelResponse(
                        message=Message(
                            role=MessageRole.ASSISTANT,
                            content="[Error: Agent stalled, no session to resume]",
                        ),
                        raw_response=raw_response,
                    )

            self._track_token_usage(raw_response)

            # Session resume error → retry without resume
            error_msg = raw_response.get("error", "")
            if existing_session and error_msg and (
                "session" in error_msg.lower() or "resume" in error_msg.lower()
            ):
                if node_id:
                    self.clear_session(node_id)
                cmd_retry = self._build_command(
                    client, prompt, None, mcp_config_path, configured_turns or 30,
                )
                raw_response, stderr_text = self._run_streaming(
                    cmd_retry, cwd, timeout, stream_callback,
                    idle_timeout=idle_timeout,
                )
                if raw_response.get("error") == "timeout":
                    return ModelResponse(
                        message=Message(
                            role=MessageRole.ASSISTANT,
                            content=f"[Error: {self.CLI_BINARY_NAME} CLI timed out on retry]",
                        ),
                        raw_response=raw_response,
                    )
                self._track_token_usage(raw_response)

            # Workspace diff
            if cwd:
                after_snapshot = self._snapshot_workspace(cwd)
                raw_response["file_changes"] = self._diff_workspace(
                    before_snapshot, after_snapshot,
                )

            if stream_callback is not None:
                raw_response["_streamed"] = True

            # Save session
            new_session_id = raw_response.get("session_id")
            if new_session_id and node_id:
                self.set_session(node_id, new_session_id)
                if cwd:
                    self.save_sessions_to_workspace(cwd)

            # Output validation — short response → resume for completion
            response_text = raw_response.get("result", "")
            resume_sid = new_session_id or (self.get_session(node_id) if node_id else None)
            if (
                resume_sid
                and len(response_text) < 1000
                and not raw_response.get("error")
                and not is_continuation
            ):
                raw_response, stderr_text = self._resume_for_completion(
                    client, resume_sid, cwd, timeout, stream_callback,
                    mcp_config_path,
                )
                self._track_token_usage(raw_response)
                updated_sid = raw_response.get("session_id")
                if updated_sid and node_id:
                    self.set_session(node_id, updated_sid)

            return self._build_stream_response(raw_response, stderr_text)
        finally:
            self._cleanup_mcp_config(mcp_config_path)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _run_streaming(
        self,
        cmd: List[str],
        cwd: Optional[str],
        timeout: int,
        stream_callback: Optional[Any],
        idle_timeout: int = 900,
    ) -> tuple:
        """Run CLI with Popen, parse NDJSON stream via ``_normalize_event``.

        Returns ``(raw_response_dict, stderr_text)``.
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            start_new_session=True,
        )

        timed_out = False
        stalled = False

        def _kill_tree():
            """Kill the entire process group so child processes don't hold
            the pipe open after the main process is killed."""
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass

        def _kill():
            nonlocal timed_out
            timed_out = True
            _kill_tree()

        def _kill_stall():
            nonlocal stalled
            stalled = True
            _kill_tree()

        timer = threading.Timer(timeout, _kill)
        timer.start()

        idle_timer = threading.Timer(idle_timeout, _kill_stall)
        idle_timer.start()

        accumulated_text: List[str] = []
        session_id: Optional[str] = None
        result_data: dict = {}
        pending_tool: Optional[dict] = None
        tool_start_time: Optional[float] = None
        tool_call_timeout = idle_timeout  # same duration for stuck tool calls

        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                normalized = self._normalize_event(event)

                # Only reset idle timer on meaningful events (not empty text)
                is_meaningful = not (
                    normalized.type == "text" and not normalized.text
                )
                if is_meaningful:
                    idle_timer.cancel()
                    idle_timer = threading.Timer(idle_timeout, _kill_stall)
                    idle_timer.start()

                # Check tool-call timeout: if a single tool call runs too long
                if tool_start_time and pending_tool:
                    elapsed = time.time() - tool_start_time
                    if elapsed > tool_call_timeout:
                        logger.warning(
                            "Tool call '%s' exceeded %ds, killing process",
                            pending_tool.get("name", "unknown"),
                            tool_call_timeout,
                        )
                        stalled = True
                        process.kill()
                        break

                if normalized.type == "init":
                    session_id = normalized.session_id or session_id

                elif normalized.type == "text":
                    text = normalized.text or ""
                    if text:
                        accumulated_text.append(text)
                        if stream_callback:
                            stream_callback("text_delta", {"text": text})
                    if pending_tool and stream_callback:
                        stream_callback("tool_end", pending_tool)
                        pending_tool = None
                        tool_start_time = None

                elif normalized.type == "tool_start":
                    if pending_tool and stream_callback:
                        stream_callback("tool_end", pending_tool)
                    pending_tool = {
                        "name": normalized.tool_name or "unknown",
                        "input": normalized.tool_input or {},
                        "id": normalized.tool_id,
                    }
                    tool_start_time = time.time()
                    if stream_callback:
                        stream_callback("tool_start", pending_tool)

                elif normalized.type == "tool_end":
                    tool_start_time = None
                    if pending_tool and stream_callback:
                        pending_tool["result"] = (
                            normalized.tool_result
                            if isinstance(normalized.tool_result, str)
                            else str(normalized.tool_result or "")[:200]
                        )
                        stream_callback("tool_end", pending_tool)
                        pending_tool = None

                elif normalized.type == "result":
                    tool_start_time = None
                    if pending_tool and stream_callback:
                        stream_callback("tool_end", pending_tool)
                        pending_tool = None
                    result_data = normalized.raw
                    session_id = normalized.session_id or session_id
                    if normalized.result_text:
                        accumulated_text.append(normalized.result_text)

                elif normalized.type == "error":
                    if normalized.text:
                        accumulated_text.append(f"[Error]: {normalized.text}")

        finally:
            timer.cancel()
            idle_timer.cancel()
            process.wait()

        stderr_text = ""
        try:
            stderr_text = process.stderr.read() if process.stderr else ""
        except Exception:
            pass

        if timed_out:
            return {"error": "timeout"}, stderr_text

        if stalled:
            return {"error": "stall", "session_id": session_id}, stderr_text

        raw_response = self._parse_stream_result(result_data, accumulated_text, session_id)
        raw_response["_returncode"] = process.returncode
        return raw_response, stderr_text

    def _parse_stream_result(
        self,
        result_data: dict,
        accumulated_text: List[str],
        session_id: Optional[str],
    ) -> dict:
        if result_data:
            raw = dict(result_data)
            if not raw.get("result") and accumulated_text:
                raw["result"] = "\n".join(accumulated_text)
            if session_id:
                raw.setdefault("session_id", session_id)
            return raw
        return {
            "result": "\n".join(accumulated_text) if accumulated_text else "",
            "session_id": session_id,
            "type": "result",
        }

    # ------------------------------------------------------------------
    # Resume helpers
    # ------------------------------------------------------------------

    def _resume_for_completion(
        self,
        client: str,
        session_id: str,
        cwd: Optional[str],
        timeout: int,
        stream_callback: Optional[Any],
        mcp_config_path: Optional[str],
    ) -> tuple:
        completion_prompt = (
            "Your previous response was incomplete — you ran out of turns before "
            "writing your deliverable. Please write your COMPLETE deliverable now. "
            "Do NOT do any more research or tool calls. Use the knowledge you already "
            "gathered to produce your full output document immediately."
        )
        configured_turns = getattr(self.config, "max_turns", None)
        cmd = self._build_resume_command(
            client, session_id, completion_prompt, mcp_config_path,
            configured_turns or 20,
        )
        return self._run_streaming(cmd, cwd, timeout, stream_callback)

    def _resume_after_stall(
        self,
        client: str,
        session_id: str,
        cwd: Optional[str],
        timeout: int,
        stream_callback: Optional[Any],
        mcp_config_path: Optional[str],
        idle_timeout: int = 900,
    ) -> tuple:
        resume_prompt = (
            "Your previous session was interrupted due to inactivity. "
            "Continue where you left off and complete your remaining work."
        )
        configured_turns = getattr(self.config, "max_turns", None)
        cmd = self._build_resume_command(
            client, session_id, resume_prompt, mcp_config_path,
            configured_turns or 20,
        )
        return self._run_streaming(
            cmd, cwd, timeout, stream_callback,
            idle_timeout=idle_timeout,
        )

    # ------------------------------------------------------------------
    # Response building
    # ------------------------------------------------------------------

    def _build_stream_response(
        self, raw_response: dict, stderr_text: str,
    ) -> ModelResponse:
        response_text = raw_response.get("result", "")
        if not response_text and stderr_text:
            response_text = f"[{self.CLI_BINARY_NAME} Error]: {stderr_text[:500]}"
        return ModelResponse(
            message=Message(role=MessageRole.ASSISTANT, content=response_text),
            raw_response=raw_response,
        )

    # ------------------------------------------------------------------
    # Token tracking
    # ------------------------------------------------------------------

    def _track_token_usage(self, raw_response: dict) -> None:
        token_tracker = getattr(self.config, "token_tracker", None)
        if not token_tracker:
            return
        usage = self.extract_token_usage(raw_response)
        node_id = getattr(self.config, "node_id", "ALL")
        usage.node_id = node_id
        usage.model_name = self.model_name
        usage.workflow_id = token_tracker.workflow_id
        usage.provider = self.PROVIDER_NAME
        token_tracker.record_usage(
            node_id, self.model_name, usage, provider=self.PROVIDER_NAME,
        )

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        conversation: List[Message],
        tool_specs: Optional[List[ToolSpec]],
        is_continuation: bool = False,
        workspace_root: Optional[Any] = None,
    ) -> str:
        parts: List[str] = []

        if is_continuation:
            for msg in conversation:
                text = msg.text_content()
                if msg.role == MessageRole.USER:
                    parts.append(f"[User]:\n{text}")
                elif msg.role == MessageRole.TOOL:
                    tool_name = msg.metadata.get("tool_name", "unknown")
                    call_id = msg.tool_call_id or "unknown"
                    parts.append(
                        f"[Tool Result for '{tool_name}' (call_id: {call_id})]:\n{text}"
                    )
        else:
            for msg in conversation:
                text = msg.text_content()
                if msg.role == MessageRole.SYSTEM:
                    parts.append(f"[System Instructions]:\n{text}")
                elif msg.role == MessageRole.USER:
                    parts.append(f"[User]:\n{text}")
                elif msg.role == MessageRole.ASSISTANT:
                    parts.append(f"[Assistant]:\n{text}")
                elif msg.role == MessageRole.TOOL:
                    tool_name = msg.metadata.get("tool_name", "unknown")
                    call_id = msg.tool_call_id or "unknown"
                    parts.append(
                        f"[Tool Result for '{tool_name}' (call_id: {call_id})]:\n{text}"
                    )

        if tool_specs and not is_continuation:
            parts.append(self._format_tool_specs(tool_specs, workspace_root))

        if workspace_root and not is_continuation:
            parts.append(
                f"[Working Directory]: {workspace_root}\n"
                "Your current working directory is set to the project workspace above. "
                "All files you create with your Write tool will be saved there. "
                "Use relative paths (e.g. 'main.py', 'src/utils.py') for all file operations."
            )

        if not is_continuation:
            parts.append(
                "[Progress Reporting]:\n"
                "You have a report_progress MCP tool available. Call it at natural "
                "transition points (e.g. after analyzing requirements, before starting "
                "implementation, after writing key files, before/after running tests). "
                "Keep reports concise (1-2 sentences). Do NOT over-report — 2-5 calls "
                "per session is ideal. If reporting fails, continue your work normally."
            )

        if not is_continuation:
            parts.append(
                "[Turn Budget & Output Priority]:\n"
                "You have a LIMITED number of agentic turns. Your PRIMARY deliverable "
                "(document, code, report) is MORE important than exhaustive research.\n"
                "- Spend at most 60% of your effort on research and analysis\n"
                "- Reserve at least 40% for writing your final deliverable output\n"
                "- If you have gathered enough context, STOP researching and START writing\n"
                "- Do NOT end your response with 'I will now...' or 'Let me next...' — "
                "always produce a complete deliverable before your turns run out\n"
                "- Limit sequential thinking (mcp sequentialthinking) to maximum 5 steps — "
                "consolidate your analysis into fewer, deeper steps rather than many shallow ones\n"
                "- If you must choose between perfect research and a complete deliverable, "
                "ALWAYS choose the complete deliverable"
            )

        return "\n\n".join(parts)

    def _format_tool_specs(
        self, tool_specs: List[ToolSpec], workspace_root: Optional[Any] = None,
    ) -> str:
        tool_mappings: List[str] = []
        for spec in tool_specs:
            name = spec.name
            desc = spec.description or ""
            if "save_file" in name or "write" in name.lower():
                tool_mappings.append(
                    f"- {name}: {desc}\n"
                    "  -> Use your Write tool to create/save files with relative paths."
                )
            elif "read_file" in name or "read" in name.lower():
                tool_mappings.append(
                    f"- {name}: {desc}\n"
                    "  -> Use your Read tool to read file contents."
                )
            elif "run" in name.lower() or "exec" in name.lower() or "bash" in name.lower():
                tool_mappings.append(
                    f"- {name}: {desc}\n"
                    "  -> Use your Bash tool to execute commands."
                )
            else:
                tool_mappings.append(f"- {name}: {desc}")

        lines = [
            "[Task Capabilities — Native Tool Mapping]:",
            "You have built-in tools: Write, Edit, Read, Bash.",
            "The following tasks are expected. Use your tools directly to accomplish them:",
            "",
        ]
        lines.extend(tool_mappings)
        lines.append("")
        lines.append(
            "CRITICAL: Create all files using your Write tool with RELATIVE paths "
            "(e.g. 'main.py', not absolute paths). "
            "Your working directory is already set to the project workspace."
        )
        if workspace_root:
            lines.append(f"Workspace: {workspace_root}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # MCP config helpers
    # ------------------------------------------------------------------

    def _create_mcp_config(
        self,
        node_id: str,
        session_id: str,
        server_port: int,
        *,
        tooling_configs: Optional[List[ToolingConfig]] = None,
        workspace_root: Optional[str] = None,
    ) -> Optional[str]:
        """Create a temporary MCP config JSON file.

        Includes the built-in chatdev-reporter server and any YAML-defined
        MCP servers.  Returns the path to the temp file, or *None*.
        """
        try:
            servers: Dict[str, Any] = {}

            # built-in chatdev-reporter
            mcp_server_path = str(
                Path(__file__).resolve().parents[4]
                / "mcp_servers"
                / "chatdev_reporter.py"
            )
            if session_id and Path(mcp_server_path).exists():
                servers["chatdev-reporter"] = {
                    "command": "python",
                    "args": [mcp_server_path],
                    "env": {
                        "CHATDEV_SERVER_URL": f"http://127.0.0.1:{server_port}",
                        "CHATDEV_SESSION_ID": session_id,
                        "CHATDEV_NODE_ID": node_id,
                    },
                }

            # YAML-defined MCP servers
            if tooling_configs:
                env_map: Dict[str, str] = dict(os.environ)
                if workspace_root:
                    env_map["WORKSPACE_ROOT"] = str(workspace_root)

                _seen_counter: Dict[str, int] = {}
                for tc in tooling_configs:
                    if tc.type not in ("mcp_local", "mcp_remote"):
                        continue

                    if tc.type == "mcp_remote":
                        cfg_r = tc.config
                        if not isinstance(cfg_r, McpRemoteConfig):
                            continue
                        server_name = (tc.prefix or "").strip()
                        if not server_name:
                            try:
                                from urllib.parse import urlparse
                                host = urlparse(cfg_r.server).hostname or ""
                                parts = host.replace(".", "-").split("-")
                                server_name = (
                                    parts[1] if len(parts) > 2 and parts[0] == "mcp"
                                    else parts[0] if parts else "mcp-remote"
                                )
                            except Exception:
                                server_name = "mcp-remote"

                        base_name = server_name
                        counter = _seen_counter.get(base_name, 0) + 1
                        _seen_counter[base_name] = counter
                        if counter > 1:
                            server_name = f"{base_name}-{counter}"
                        while server_name in servers:
                            counter += 1
                            _seen_counter[base_name] = counter
                            server_name = f"{base_name}-{counter}"

                        entry_r: Dict[str, Any] = {
                            "type": "http",
                            "url": cfg_r.server,
                        }
                        if cfg_r.headers:
                            entry_r["headers"] = dict(cfg_r.headers)

                        resolved_r = self._resolve_env_dict(entry_r, env_map)
                        if resolved_r is None:
                            continue
                        servers[server_name] = resolved_r
                        continue

                    cfg = tc.config
                    if not isinstance(cfg, McpLocalConfig):
                        continue

                    server_name = (tc.prefix or "").strip()
                    if not server_name:
                        server_name = self._infer_mcp_server_name(
                            cfg.command, cfg.args,
                        )

                    base_name = server_name
                    counter = _seen_counter.get(base_name, 0) + 1
                    _seen_counter[base_name] = counter
                    if counter > 1:
                        server_name = f"{base_name}-{counter}"
                    while server_name in servers:
                        counter += 1
                        _seen_counter[base_name] = counter
                        server_name = f"{base_name}-{counter}"

                    entry: Dict[str, Any] = {
                        "command": cfg.command,
                        "args": list(cfg.args) if cfg.args else [],
                    }
                    if cfg.env:
                        entry["env"] = dict(cfg.env)
                    if cfg.cwd:
                        entry["cwd"] = cfg.cwd

                    resolved = self._resolve_env_dict(entry, env_map)
                    if resolved is None:
                        continue
                    servers[server_name] = resolved

            if not servers:
                return None

            config = self._build_mcp_config_dict(servers)

            fd, path = tempfile.mkstemp(suffix=".json", prefix="chatdev_mcp_")
            with os.fdopen(fd, "w") as f:
                json.dump(config, f)
            return path
        except Exception:
            return None

    @staticmethod
    def _infer_mcp_server_name(command: str, args: List[str]) -> str:
        candidate = ""
        for arg in (args or []):
            if arg.startswith("-"):
                continue
            if arg.startswith(("/", "./", "../", "~")):
                continue
            if "/" in arg and "@" not in arg:
                continue
            candidate = arg
            break

        if candidate:
            name = candidate.rsplit("/", 1)[-1]
            name = name.removesuffix(".py").removesuffix(".js")
            name = name.replace("_", "-")
            return name or "mcp-server"

        return command.replace("_", "-")

    _ENV_PLACEHOLDER = re.compile(r"\$ENV\{([A-Za-z0-9_]+)\}")

    @staticmethod
    def _resolve_env_str(value: str, env_map: Dict[str, str]) -> tuple:
        ok = True

        def replacer(m: re.Match) -> str:
            nonlocal ok
            var_name = m.group(1)
            val = env_map.get(var_name)
            if val is None:
                ok = False
                return m.group(0)
            return val

        resolved = CliProviderBase._ENV_PLACEHOLDER.sub(replacer, value)
        return resolved, ok

    @staticmethod
    def _resolve_env_dict(
        entry: Dict[str, Any], env_map: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        all_ok = True

        if "args" in entry and isinstance(entry["args"], list):
            new_args = []
            for a in entry["args"]:
                if isinstance(a, str):
                    resolved, ok = CliProviderBase._resolve_env_str(a, env_map)
                    if not ok:
                        all_ok = False
                    new_args.append(resolved)
                else:
                    new_args.append(a)
            entry["args"] = new_args

        for key in ("cwd", "url", "command"):
            if key in entry and isinstance(entry[key], str):
                resolved, ok = CliProviderBase._resolve_env_str(entry[key], env_map)
                if not ok:
                    all_ok = False
                entry[key] = resolved

        for key in ("env", "headers"):
            if key in entry and isinstance(entry[key], dict):
                new_dict = {}
                for k, v in entry[key].items():
                    if isinstance(v, str):
                        resolved, ok = CliProviderBase._resolve_env_str(v, env_map)
                        if not ok:
                            all_ok = False
                        new_dict[k] = resolved
                    else:
                        new_dict[k] = v
                entry[key] = new_dict

        return entry if all_ok else None

    @staticmethod
    def _cleanup_mcp_config(config_path: Optional[str]) -> None:
        if config_path:
            try:
                os.unlink(config_path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Workspace scanning
    # ------------------------------------------------------------------

    _SCAN_EXCLUDE_DIRS = frozenset({
        "__pycache__", ".git", ".venv", "venv", "node_modules",
        ".mypy_cache", ".pytest_cache", "attachments",
        "dist", ".build", "Build", "DerivedData",
        "Pods", ".dart_tool", ".pub-cache",
        ".gradle", ".idea", ".vs", ".vscode",
        "target", "obj",
        "coverage", ".nyc_output",
        "generated",
    })

    _SCAN_EXCLUDE_FILES = frozenset({
        "firebase-debug.log",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
    })

    _SNAPSHOT_HIDDEN_WHITELIST = frozenset({".github"})

    @staticmethod
    def _load_gitignore_spec(workspace_root: str):
        try:
            import pathspec
            gitignore_path = Path(workspace_root) / ".gitignore"
            if gitignore_path.exists():
                with open(gitignore_path, "r") as f:
                    return pathspec.PathSpec.from_lines("gitwildmatch", f)
        except Exception:
            pass
        return None

    def _snapshot_workspace(self, workspace_root: str) -> Dict[str, tuple]:
        snapshot: Dict[str, tuple] = {}
        root = Path(workspace_root)
        if not root.exists():
            return snapshot

        gitignore_spec = self._load_gitignore_spec(workspace_root)

        for item in root.rglob("*"):
            if not item.is_file():
                continue
            rel = item.relative_to(root)
            if any(
                (part.startswith(".") and part not in self._SNAPSHOT_HIDDEN_WHITELIST)
                or part in self._SCAN_EXCLUDE_DIRS
                for part in rel.parts[:-1]
            ):
                continue
            if rel.name in self._SCAN_EXCLUDE_FILES:
                continue
            if gitignore_spec and gitignore_spec.match_file(str(rel)):
                continue
            try:
                st = item.stat()
                snapshot[str(rel)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                continue
        return snapshot

    @staticmethod
    def _diff_workspace(
        before: Dict[str, tuple],
        after: Dict[str, tuple],
    ) -> List[Dict[str, Any]]:
        changes: List[Dict[str, Any]] = []
        for path, (size, mtime) in after.items():
            if path not in before:
                changes.append({"path": path, "change": "created", "size": size})
            elif before[path] != (size, mtime):
                changes.append({"path": path, "change": "modified", "size": size})
        for path in before:
            if path not in after:
                changes.append({"path": path, "change": "deleted", "size": 0})
        return changes

    # ------------------------------------------------------------------
    # Legacy fallback parser
    # ------------------------------------------------------------------

    def _parse_cli_output(self, result: subprocess.CompletedProcess) -> dict:
        stdout = result.stdout or ""
        if not stdout.strip():
            return {
                "result": "",
                "error": result.stderr or "empty response",
                "returncode": result.returncode,
            }
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict) and parsed.get("type") == "result":
                    return parsed
            except json.JSONDecodeError:
                continue
        return {"result": stdout.strip(), "type": "text_fallback"}
