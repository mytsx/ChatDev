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
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from entity.configs import AgentConfig
from runtime.node.agent.providers.cli_provider_base import CliProviderBase, NormalizedEvent
from utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)


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
    # MCP config override — Gemini reads .gemini/settings.json in cwd
    # ------------------------------------------------------------------

    # Instance attribute to track the backup path for cleanup
    _gemini_settings_backup: Optional[str] = None
    _gemini_settings_path: Optional[str] = None

    def _create_mcp_config(
        self,
        node_id: str,
        session_id: str,
        server_port: int,
        *,
        tooling_configs=None,
        workspace_root=None,
    ) -> Optional[str]:
        """Write MCP servers to ``{workspace}/.gemini/settings.json``.

        Gemini CLI has no ``--mcp-config`` flag.  It reads MCP server
        definitions from the project-level ``.gemini/settings.json`` file
        (created by ``gemini mcp add``).

        Strategy:
        1. Use the base class to build the MCP config dict (temp file).
        2. Read the temp file to get the servers dict.
        3. If ``.gemini/settings.json`` already exists, back it up.
        4. Merge our servers into the settings and write to
           ``{workspace}/.gemini/settings.json``.
        5. On cleanup, restore the original file (or remove ours).

        Returns the path to ``.gemini/settings.json`` (used as a sentinel
        for cleanup — Gemini doesn't use ``--mcp-config``).
        """
        # Build the MCP servers dict via the base class temp file
        temp_path = super()._create_mcp_config(
            node_id, session_id, server_port,
            tooling_configs=tooling_configs,
            workspace_root=workspace_root,
        )
        if not temp_path:
            return None

        cwd = workspace_root or os.getcwd()

        try:
            # Read the generated config from temp file
            with open(temp_path, "r") as f:
                new_config = json.load(f)
            new_servers = new_config.get("mcpServers", {})
            if not new_servers:
                return None

            # Target: {workspace}/.gemini/settings.json
            gemini_dir = Path(cwd) / ".gemini"
            gemini_dir.mkdir(parents=True, exist_ok=True)
            settings_path = gemini_dir / "settings.json"

            # Back up existing settings.json if present
            if settings_path.exists():
                backup_path = str(settings_path) + ".chatdev_backup"
                shutil.copy2(str(settings_path), backup_path)
                self._gemini_settings_backup = backup_path

                # Merge: existing settings + our servers
                try:
                    with open(settings_path, "r") as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    existing = {}

                existing_servers = existing.get("mcpServers", {})
                existing_servers.update(new_servers)
                existing["mcpServers"] = existing_servers
                merged = existing
            else:
                self._gemini_settings_backup = None
                merged = {"mcpServers": new_servers}

            # Write merged settings
            with open(settings_path, "w") as f:
                json.dump(merged, f, indent=2)

            self._gemini_settings_path = str(settings_path)
            logger.debug(
                "Gemini MCP config written to %s with %d server(s)",
                settings_path, len(new_servers),
            )
            return str(settings_path)

        except Exception as exc:
            logger.warning("Failed to create Gemini MCP config: %s", exc)
            return None
        finally:
            # Always remove the temp file — Gemini doesn't use it
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _cleanup_mcp_config(self, config_path: Optional[str]) -> None:
        """Restore original ``.gemini/settings.json`` after execution."""
        if not config_path:
            return

        settings_path = Path(config_path)
        backup_path = self._gemini_settings_backup

        try:
            if backup_path and Path(backup_path).exists():
                # Restore original settings
                shutil.move(backup_path, str(settings_path))
                logger.debug("Restored original Gemini settings from backup")
            elif settings_path.exists():
                # We created it — remove it
                settings_path.unlink()
                # Remove .gemini dir if empty
                gemini_dir = settings_path.parent
                if gemini_dir.exists() and not any(gemini_dir.iterdir()):
                    gemini_dir.rmdir()
                logger.debug("Removed Gemini settings.json (no original existed)")
        except Exception as exc:
            logger.warning("Failed to clean up Gemini MCP config: %s", exc)
        finally:
            self._gemini_settings_backup = None
            self._gemini_settings_path = None
