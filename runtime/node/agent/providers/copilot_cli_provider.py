"""Copilot CLI provider implementation.

Uses GitHub Copilot CLI (copilot -p) as the LLM backend, leveraging the
user's GitHub Copilot subscription instead of requiring a separate API key.

Copilot CLI works in its native agentic mode with built-in tools for
file read/write, shell execution, and code analysis.

Note: Copilot CLI does NOT support NDJSON streaming output in ``-p`` mode
(feature request #52).  This provider uses plain text output and relies on
workspace diffing to detect file changes.  Tool events are not streamed
in real time.
"""

import json
import subprocess
import threading
from typing import Any, Dict, List, Optional

from entity.configs import AgentConfig
from runtime.node.agent.providers.cli_provider_base import CliProviderBase, NormalizedEvent
from utils.token_tracker import TokenUsage


class CopilotCliProvider(CliProviderBase):
    """Provider that uses GitHub Copilot CLI (copilot -p) as the LLM backend.

    This provider calls the ``copilot`` binary via subprocess, using the
    user's GitHub Copilot subscription.  No API key is needed.

    Supports persistent sessions via --resume flag.  Because Copilot CLI
    does not yet support structured JSON output in programmatic mode,
    tool streaming events are not available — file changes are detected
    via workspace snapshot diffing.
    """

    CLI_BINARY_NAME = "copilot"
    CLI_FALLBACK_PATHS = [
        "/usr/local/bin/copilot",
        "/opt/homebrew/bin/copilot",
        "~/.local/bin/copilot",
    ]
    PROVIDER_NAME = "copilot-cli"
    SESSIONS_FILE = ".copilot_sessions.json"

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _resolve_model_flag(self) -> Optional[str]:
        name = (self.model_name or "").lower().strip()
        if not name or name in ("copilot", "default"):
            return None
        return name

    def _build_command(
        self,
        client: str,
        prompt: str,
        session_id: Optional[str],
        mcp_config_path: Optional[str],
        max_turns: int,
        **kwargs,
    ) -> List[str]:
        cmd = [client, "-p", prompt]

        # Auto-approve all tool calls (≈ dangerously-skip-permissions)
        cmd.append("--yolo")

        if session_id:
            cmd.extend(["--resume", session_id])

        if mcp_config_path:
            # Copilot requires @ prefix for file paths (vs inline JSON)
            cmd.extend(["--additional-mcp-config", f"@{mcp_config_path}"])

        if self._model_flag:
            cmd.extend(["--model", self._model_flag])

        return cmd

    def _build_resume_command(
        self,
        client: str,
        session_id: str,
        prompt: str,
        mcp_config_path: Optional[str],
        max_turns: int,
        **kwargs,
    ) -> List[str]:
        cmd = [
            client, "-p", prompt,
            "--yolo",
            "--resume", session_id,
        ]
        if mcp_config_path:
            cmd.extend(["--additional-mcp-config", f"@{mcp_config_path}"])
        if self._model_flag:
            cmd.extend(["--model", self._model_flag])
        return cmd

    def _normalize_event(self, raw_event: dict) -> NormalizedEvent:
        """Copilot CLI does not emit NDJSON in -p mode.

        This method handles the case where the line happens to be valid
        JSON (e.g. a future Copilot version adds streaming support).
        For now, most lines from Copilot are plain text and never reach
        this method — see ``_run_streaming`` override below.
        """
        event_type = raw_event.get("type", "")

        if event_type == "result":
            return NormalizedEvent(
                type="result",
                session_id=raw_event.get("session_id"),
                result_text=raw_event.get("result", ""),
                usage=raw_event.get("usage"),
                raw=raw_event,
            )

        if event_type == "system":
            return NormalizedEvent(
                type="init",
                session_id=raw_event.get("session_id"),
                raw=raw_event,
            )

        # Unknown JSON event — treat as text
        return NormalizedEvent(
            type="text",
            text=json.dumps(raw_event),
            raw=raw_event,
        )

    def _run_streaming(
        self,
        cmd: List[str],
        cwd: Optional[str],
        timeout: int,
        stream_callback: Optional[Any],
        idle_timeout: int = 900,
    ) -> tuple:
        """Run Copilot CLI and capture plain text output.

        Copilot's ``-p`` mode outputs plain text, not NDJSON.  We read
        stdout line by line, accumulate text, and rely on workspace diffing
        for file change detection.  Each line resets the idle timer.
        """
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=cwd,
        )

        timed_out = False
        stalled = False

        def _kill():
            nonlocal timed_out
            timed_out = True
            process.kill()

        def _kill_stall():
            nonlocal stalled
            stalled = True
            process.kill()

        timer = threading.Timer(timeout, _kill)
        timer.start()

        idle_timer = threading.Timer(idle_timeout, _kill_stall)
        idle_timer.start()

        accumulated_text: List[str] = []
        session_id: Optional[str] = None

        try:
            for line in process.stdout:
                idle_timer.cancel()
                idle_timer = threading.Timer(idle_timeout, _kill_stall)
                idle_timer.start()

                line = line.rstrip("\n")

                # Try JSON parse in case Copilot emits structured data
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        if event.get("type") == "system":
                            session_id = event.get("session_id") or session_id
                            continue
                        if event.get("type") == "result":
                            session_id = event.get("session_id") or session_id
                            result_text = event.get("result", "")
                            if result_text:
                                accumulated_text.append(result_text)
                            break
                except (json.JSONDecodeError, ValueError):
                    pass

                # Plain text line — accumulate and stream
                if line.strip():
                    accumulated_text.append(line)
                    if stream_callback:
                        stream_callback("text_delta", {"text": line})

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

        raw_response = {
            "result": "\n".join(accumulated_text) if accumulated_text else "",
            "session_id": session_id,
            "type": "result",
            "_returncode": process.returncode,
        }
        return raw_response, stderr_text

    def extract_token_usage(self, response: Any) -> TokenUsage:
        """Copilot CLI does not expose token usage in -p mode."""
        return TokenUsage()

    def _build_mcp_config_dict(self, servers: Dict[str, Any]) -> dict:
        """Copilot CLI uses the same mcpServers format for --additional-mcp-config."""
        return {"mcpServers": servers}
