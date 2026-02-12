"""Claude Code provider implementation.

Uses the Claude Code CLI (claude -p) as the LLM backend, leveraging the user's
Max subscription instead of requiring a separate API key.

Claude Code works in its native agentic mode, using its own built-in tools
(Write, Edit, Read, Bash) to accomplish tasks like writing code, running tests,
etc. The provider returns the text result from Claude's work.
"""

from typing import Any, Dict, List, Optional

from entity.configs import AgentConfig
from runtime.node.agent.providers.cli_provider_base import CliProviderBase, NormalizedEvent
from utils.token_tracker import TokenUsage


class ClaudeCodeProvider(CliProviderBase):
    """Provider that uses Claude Code CLI (claude -p) as the LLM backend.

    This provider calls the ``claude`` binary via subprocess, using the user's
    Max subscription. No ANTHROPIC_API_KEY is needed.

    Supports persistent sessions via --resume flag, allowing context to be
    preserved across multiple calls for the same agent node.
    """

    CLI_BINARY_NAME = "claude"
    CLI_FALLBACK_PATHS = [
        "/usr/local/bin/claude",
        "/opt/homebrew/bin/claude",
        "~/.local/bin/claude",
    ]
    PROVIDER_NAME = "claude-code"
    SESSIONS_FILE = ".claude_sessions.json"

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _resolve_model_flag(self) -> Optional[str]:
        name = (self.model_name or "").lower().strip()
        if not name or name in ("claude", "default"):
            return None
        if name in ("sonnet", "opus", "haiku"):
            return name
        if "opus" in name:
            return "opus"
        if "sonnet" in name:
            return "sonnet"
        if "haiku" in name:
            return "haiku"
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
        cmd.append("--verbose")
        cmd.append("--dangerously-skip-permissions")

        if session_id:
            cmd.extend(["--resume", session_id])

        cmd.extend(["--max-turns", str(max_turns)])

        if mcp_config_path:
            cmd.extend(["--mcp-config", mcp_config_path])

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
            "--output-format", "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--resume", session_id,
            "--max-turns", str(max_turns),
        ]
        if mcp_config_path:
            cmd.extend(["--mcp-config", mcp_config_path])
        if self._model_flag:
            cmd.extend(["--model", self._model_flag])
        return cmd

    def _normalize_event(self, raw_event: dict) -> NormalizedEvent:
        """Normalize Claude Code NDJSON events.

        Claude uses nested content blocks inside ``assistant`` and ``user``
        message wrappers, unlike Gemini's flat event types.
        """
        event_type = raw_event.get("type")

        if event_type == "system":
            return NormalizedEvent(
                type="init",
                session_id=raw_event.get("session_id"),
                raw=raw_event,
            )

        if event_type == "assistant":
            msg = raw_event.get("message", {})
            content_blocks = msg.get("content", [])
            # Process blocks — return the first meaningful event.
            # Multiple blocks in one message are handled by accumulated processing.
            for block in content_blocks:
                block_type = block.get("type")
                if block_type == "tool_use":
                    return NormalizedEvent(
                        type="tool_start",
                        tool_name=block.get("name", "unknown"),
                        tool_input=block.get("input", {}),
                        tool_id=block.get("id"),
                        raw=raw_event,
                    )
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        return NormalizedEvent(
                            type="text",
                            text=text,
                            raw=raw_event,
                        )
            return NormalizedEvent(type="text", text="", raw=raw_event)

        if event_type == "user":
            msg = raw_event.get("message", {})
            content_blocks = msg.get("content", [])
            for block in content_blocks:
                if block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    return NormalizedEvent(
                        type="tool_end",
                        tool_result=(
                            result_content
                            if isinstance(result_content, str)
                            else str(result_content)[:200]
                        ),
                        raw=raw_event,
                    )
            return NormalizedEvent(type="text", text="", raw=raw_event)

        if event_type == "result":
            return NormalizedEvent(
                type="result",
                session_id=raw_event.get("session_id"),
                result_text=raw_event.get("result", ""),
                usage=raw_event.get("usage"),
                raw=raw_event,
            )

        return NormalizedEvent(type="text", text="", raw=raw_event)

    def extract_token_usage(self, response: Any) -> TokenUsage:
        if not isinstance(response, dict):
            return TokenUsage()

        usage = response.get("usage", {}) or {}
        cost = response.get("total_cost_usd", 0) or 0

        model_usage = response.get("modelUsage", {})
        if model_usage and not usage.get("input_tokens"):
            for _model, stats in model_usage.items():
                input_tokens = stats.get("inputTokens", 0)
                output_tokens = stats.get("outputTokens", 0)
                return TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    metadata={"total_cost_usd": cost, **stats},
                )

        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            metadata={"total_cost_usd": cost},
        )

    def _build_mcp_config_dict(self, servers: Dict[str, Any]) -> dict:
        return {"mcpServers": servers}
