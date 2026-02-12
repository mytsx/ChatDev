"""Gemini CLI provider implementation.

Uses the Gemini CLI (gemini -p) as the LLM backend, leveraging the user's
Google account instead of requiring a separate API key.

Gemini CLI works in its native agentic mode with built-in tools
(read_file, write_file, replace, glob, grep_search, run_shell_command, etc.)
to accomplish tasks.  The provider returns the text result from Gemini's work.

Streaming uses ``--output-format stream-json`` which emits NDJSON events with
types: init, message, tool_use, tool_result, error, result.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from entity.configs import AgentConfig
from runtime.node.agent.providers.cli_provider_base import CliProviderBase, NormalizedEvent
from utils.token_tracker import TokenUsage


class GeminiCliProvider(CliProviderBase):
    """Provider that uses Gemini CLI (gemini -p) as the LLM backend.

    This provider calls the ``gemini`` binary via subprocess, using the user's
    Google account.  No API key is needed.

    Supports persistent sessions via --resume flag and NDJSON streaming
    via --output-format stream-json.
    """

    CLI_BINARY_NAME = "gemini"
    CLI_FALLBACK_PATHS = [
        "/usr/local/bin/gemini",
        "/opt/homebrew/bin/gemini",
        "~/.local/bin/gemini",
    ]
    PROVIDER_NAME = "gemini-cli"
    SESSIONS_FILE = ".gemini_sessions.json"

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _resolve_model_flag(self) -> Optional[str]:
        name = (self.model_name or "").lower().strip()
        if not name or name in ("gemini", "default"):
            return None
        # gemini CLI accepts full model IDs directly
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
        cmd = [client, "-p", prompt, "--output-format", "stream-json"]

        # Non-interactive auto-approve all tool calls
        cmd.extend(["--approval-mode", "yolo"])

        if session_id:
            cmd.extend(["--resume", session_id])

        if self._model_flag:
            cmd.extend(["--model", self._model_flag])

        # Gemini CLI doesn't have --max-turns flag; it's configured in settings.
        # We pass it as env var GEMINI_MAX_TURNS if the CLI supports it.
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
            "--output-format", "stream-json",
            "--approval-mode", "yolo",
            "--resume", session_id,
        ]
        if self._model_flag:
            cmd.extend(["--model", self._model_flag])
        return cmd

    def _normalize_event(self, raw_event: dict) -> NormalizedEvent:
        """Normalize Gemini CLI NDJSON events.

        Gemini uses flat top-level event types (init, message, tool_use,
        tool_result, error, result) instead of Claude's nested assistant/user
        wrappers.
        """
        event_type = raw_event.get("type")

        if event_type == "init":
            return NormalizedEvent(
                type="init",
                session_id=raw_event.get("session_id"),
                raw=raw_event,
            )

        if event_type == "message":
            role = raw_event.get("role", "")
            content = raw_event.get("content", "")
            if role == "assistant" and content:
                return NormalizedEvent(
                    type="text",
                    text=content,
                    raw=raw_event,
                )
            # User messages or empty assistant messages — skip
            return NormalizedEvent(type="text", text="", raw=raw_event)

        if event_type == "tool_use":
            return NormalizedEvent(
                type="tool_start",
                tool_name=raw_event.get("tool_name", "unknown"),
                tool_input=raw_event.get("parameters", {}),
                tool_id=raw_event.get("tool_id"),
                raw=raw_event,
            )

        if event_type == "tool_result":
            output = raw_event.get("output", "")
            return NormalizedEvent(
                type="tool_end",
                tool_id=raw_event.get("tool_id"),
                tool_result=output if isinstance(output, str) else str(output)[:200],
                raw=raw_event,
            )

        if event_type == "result":
            stats = raw_event.get("stats", {})
            return NormalizedEvent(
                type="result",
                session_id=raw_event.get("session_id"),
                result_text=raw_event.get("content", ""),
                usage=stats,
                raw=raw_event,
            )

        if event_type == "error":
            return NormalizedEvent(
                type="error",
                text=raw_event.get("message", raw_event.get("error", "")),
                raw=raw_event,
            )

        return NormalizedEvent(type="text", text="", raw=raw_event)

    def extract_token_usage(self, response: Any) -> TokenUsage:
        if not isinstance(response, dict):
            return TokenUsage()

        stats = response.get("stats", {}) or {}
        if not stats:
            # Try usage field as fallback
            stats = response.get("usage", {}) or {}

        input_tokens = stats.get("input_tokens", 0)
        output_tokens = stats.get("output_tokens", 0)
        total_tokens = stats.get("total_tokens", input_tokens + output_tokens)

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            metadata=stats,
        )

    def _build_mcp_config_dict(self, servers: Dict[str, Any]) -> dict:
        """Build MCP config in Gemini CLI settings.json format.

        Gemini CLI uses the same ``mcpServers`` key for stdio-based servers.
        """
        return {"mcpServers": servers}

    # ------------------------------------------------------------------
    # MCP config override — Gemini uses env var instead of --mcp-config
    # ------------------------------------------------------------------

    def _create_mcp_config(
        self,
        node_id: str,
        session_id: str,
        server_port: int,
        *,
        tooling_configs=None,
        workspace_root=None,
    ) -> Optional[str]:
        """Create MCP config and set GEMINI_SETTINGS_FILE env var.

        Gemini CLI reads MCP server configuration from settings.json rather
        than a ``--mcp-config`` flag.  We create a temporary settings file
        and point to it via the ``GEMINI_SETTINGS_FILE`` environment variable.

        Falls back to the base class implementation which creates the temp
        file.  The command builder doesn't use ``--mcp-config``, so the file
        path is used only for env var injection.
        """
        config_path = super()._create_mcp_config(
            node_id, session_id, server_port,
            tooling_configs=tooling_configs,
            workspace_root=workspace_root,
        )
        if config_path:
            os.environ["GEMINI_SETTINGS_FILE"] = config_path
        return config_path

    @staticmethod
    def _cleanup_mcp_config(config_path: Optional[str]) -> None:
        if config_path:
            os.environ.pop("GEMINI_SETTINGS_FILE", None)
            try:
                os.unlink(config_path)
            except OSError:
                pass
