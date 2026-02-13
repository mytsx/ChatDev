"""Comprehensive CLI provider tests.

Covers all provider functionality:
- Session management (get/set/clear/save/load)
- Binary discovery (_find_binary)
- Model flag resolution (_resolve_model_flag) — Claude, Gemini, Copilot
- Command building (_build_command, _build_resume_command) — all 3
- Event normalization (_normalize_event) — all 3
- Token usage extraction (extract_token_usage) — all 3
- MCP config creation (_create_mcp_config, _build_mcp_config_dict)
- MCP server name inference (_infer_mcp_server_name)
- Environment variable resolution (_resolve_env_str, _resolve_env_dict)
- Prompt building (_build_prompt)
- Workspace snapshot & diff (_snapshot_workspace, _diff_workspace)
- Stream parsing (_parse_stream_result, _parse_cli_output)
- Response building (_build_stream_response)
- call_model orchestration (timeout, stall recovery, session retry)
- Copilot _run_streaming (plain text mode)
- Gemini MCP config override (_create_mcp_config settings.json)

Run:
    uv run python tests/test_cli_providers.py
"""

import json
import os
import stat
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.node.agent.providers.claude_code_provider import ClaudeCodeProvider
from runtime.node.agent.providers.gemini_cli_provider import GeminiCliProvider
from runtime.node.agent.providers.copilot_cli_provider import CopilotCliProvider
from runtime.node.agent.providers.cli_provider_base import CliProviderBase, NormalizedEvent
from entity.messages import Message, MessageRole
from utils.token_tracker import TokenUsage


# ─── Helpers ────────────────────────────────────────────────────────────────

def _create_mock_script(script_body: str) -> str:
    """Create a temporary executable bash script."""
    fd, path = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(script_body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def _create_mock_config(**overrides):
    """Create a minimal AgentConfig-like mock."""
    config = MagicMock()
    config.node_id = overrides.get("node_id", "test-node")
    config.workspace_root = overrides.get("workspace_root", None)
    config.max_turns = overrides.get("max_turns", 5)
    config.tooling = overrides.get("tooling", [])
    config.base_url = overrides.get("base_url", "")
    config.api_key = overrides.get("api_key", "")
    config.name = overrides.get("name", "sonnet")
    config.provider = overrides.get("provider", "claude-code")
    config.params = overrides.get("params", {})
    config.token_tracker = overrides.get("token_tracker", None)
    return config


def _make_provider(cls, model_name="sonnet", model_flag=None):
    """Create a provider instance without __init__ (bypass binary check)."""
    provider = object.__new__(cls)
    provider.config = _create_mock_config(name=model_name)
    provider.model_name = model_name
    provider._model_flag = model_flag
    provider._binary_path = f"/usr/local/bin/{cls.CLI_BINARY_NAME}"
    return provider


# ═══════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def test_session_isolation():
    """Each subclass gets its own _sessions dict."""
    ClaudeCodeProvider.clear_all_sessions()
    GeminiCliProvider.clear_all_sessions()
    CopilotCliProvider.clear_all_sessions()

    ClaudeCodeProvider.set_session("node-A", "claude-sess-1")
    GeminiCliProvider.set_session("node-A", "gemini-sess-1")
    CopilotCliProvider.set_session("node-A", "copilot-sess-1")

    assert ClaudeCodeProvider.get_session("node-A") == "claude-sess-1"
    assert GeminiCliProvider.get_session("node-A") == "gemini-sess-1"
    assert CopilotCliProvider.get_session("node-A") == "copilot-sess-1"

    ClaudeCodeProvider.clear_session("node-A")
    assert ClaudeCodeProvider.get_session("node-A") is None
    assert GeminiCliProvider.get_session("node-A") == "gemini-sess-1"  # unaffected

    ClaudeCodeProvider.clear_all_sessions()
    GeminiCliProvider.clear_all_sessions()
    CopilotCliProvider.clear_all_sessions()
    print("  PASS: Session isolation between providers")


def test_session_save_load():
    """Sessions persist to workspace file and reload."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ClaudeCodeProvider.clear_all_sessions()
        ClaudeCodeProvider.set_session("dev", "sess-abc")
        ClaudeCodeProvider.set_session("qa", "sess-xyz")
        ClaudeCodeProvider.save_sessions_to_workspace(tmpdir)

        path = Path(tmpdir) / ClaudeCodeProvider.SESSIONS_FILE
        assert path.exists(), "Sessions file should be created"

        data = json.loads(path.read_text())
        assert data["dev"] == "sess-abc"
        assert data["qa"] == "sess-xyz"

        ClaudeCodeProvider.clear_all_sessions()
        assert ClaudeCodeProvider.get_session("dev") is None

        ClaudeCodeProvider.load_sessions_from_workspace(tmpdir)
        assert ClaudeCodeProvider.get_session("dev") == "sess-abc"
        assert ClaudeCodeProvider.get_session("qa") == "sess-xyz"

        ClaudeCodeProvider.clear_all_sessions()
    print("  PASS: Session save/load to workspace")


def test_session_get_nonexistent():
    """Getting a non-existent session returns None."""
    ClaudeCodeProvider.clear_all_sessions()
    assert ClaudeCodeProvider.get_session("nonexistent") is None
    print("  PASS: Non-existent session returns None")


def test_session_load_corrupt_file():
    """Loading a corrupt sessions file doesn't crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / ClaudeCodeProvider.SESSIONS_FILE
        path.write_text("not valid json {{{")
        ClaudeCodeProvider.clear_all_sessions()
        ClaudeCodeProvider.load_sessions_from_workspace(tmpdir)
        assert ClaudeCodeProvider.get_session("any") is None
    print("  PASS: Corrupt sessions file handled gracefully")


# ═══════════════════════════════════════════════════════════════════════════
# MODEL FLAG RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def test_claude_model_flag():
    """Claude provider maps model names correctly."""
    p = _make_provider(ClaudeCodeProvider)

    test_cases = [
        ("", None),
        ("claude", None),
        ("default", None),
        ("sonnet", "sonnet"),
        ("opus", "opus"),
        ("haiku", "haiku"),
        ("claude-sonnet-4", "sonnet"),
        ("claude-opus-4", "opus"),
        ("claude-haiku-4", "haiku"),
        ("custom-model-id", "custom-model-id"),
    ]
    for name, expected in test_cases:
        p.model_name = name
        result = p._resolve_model_flag()
        assert result == expected, f"Claude model '{name}': expected {expected}, got {result}"

    print("  PASS: Claude model flag resolution")


def test_gemini_model_flag():
    """Gemini provider maps model names correctly."""
    p = _make_provider(GeminiCliProvider, model_name="gemini")

    test_cases = [
        ("", None),
        ("gemini", None),
        ("default", None),
        ("gemini-2.5-pro", "gemini-2.5-pro"),
        ("custom", "custom"),
    ]
    for name, expected in test_cases:
        p.model_name = name
        result = p._resolve_model_flag()
        assert result == expected, f"Gemini model '{name}': expected {expected}, got {result}"

    print("  PASS: Gemini model flag resolution")


def test_copilot_model_flag():
    """Copilot provider maps model names correctly."""
    p = _make_provider(CopilotCliProvider, model_name="copilot")

    test_cases = [
        ("", None),
        ("copilot", None),
        ("default", None),
        ("gpt-4o", "gpt-4o"),
        ("claude-3.5-sonnet", "claude-3.5-sonnet"),
    ]
    for name, expected in test_cases:
        p.model_name = name
        result = p._resolve_model_flag()
        assert result == expected, f"Copilot model '{name}': expected {expected}, got {result}"

    print("  PASS: Copilot model flag resolution")


# ═══════════════════════════════════════════════════════════════════════════
# COMMAND BUILDING
# ═══════════════════════════════════════════════════════════════════════════

def test_claude_build_command_fresh():
    """Claude builds correct command for fresh session."""
    p = _make_provider(ClaudeCodeProvider, model_flag="sonnet")
    cmd = p._build_command(
        client="/usr/local/bin/claude",
        prompt="Write hello world",
        session_id=None,
        mcp_config_path=None,
        max_turns=30,
    )
    assert cmd[0] == "/usr/local/bin/claude"
    assert "-p" in cmd
    assert "Write hello world" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--max-turns" in cmd
    assert "30" in cmd
    assert "--model" in cmd
    assert "sonnet" in cmd
    assert "--resume" not in cmd
    print("  PASS: Claude build command (fresh)")


def test_claude_build_command_resume():
    """Claude builds correct command with session resume."""
    p = _make_provider(ClaudeCodeProvider, model_flag="opus")
    cmd = p._build_command(
        client="claude",
        prompt="Continue work",
        session_id="sess-abc-123",
        mcp_config_path="/tmp/mcp.json",
        max_turns=20,
    )
    assert "--resume" in cmd
    assert "sess-abc-123" in cmd
    assert "--mcp-config" in cmd
    assert "/tmp/mcp.json" in cmd
    assert "--model" in cmd
    assert "opus" in cmd
    print("  PASS: Claude build command (resume + MCP)")


def test_claude_build_resume_command():
    """Claude _build_resume_command includes all required flags."""
    p = _make_provider(ClaudeCodeProvider, model_flag="haiku")
    cmd = p._build_resume_command(
        client="claude",
        session_id="sess-resume",
        prompt="Complete your work",
        mcp_config_path=None,
        max_turns=15,
    )
    assert "--resume" in cmd
    assert "sess-resume" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert "--max-turns" in cmd
    assert "15" in cmd
    assert "--model" in cmd
    assert "haiku" in cmd
    print("  PASS: Claude build resume command")


def test_gemini_build_command():
    """Gemini builds correct command."""
    p = _make_provider(GeminiCliProvider, model_flag="gemini-2.5-pro")
    cmd = p._build_command(
        client="gemini",
        prompt="Analyze code",
        session_id=None,
        mcp_config_path=None,
        max_turns=30,
    )
    assert cmd[0] == "gemini"
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert "stream-json" in cmd
    assert "--approval-mode" in cmd
    assert "yolo" in cmd
    assert "--model" in cmd
    assert "gemini-2.5-pro" in cmd
    assert "--resume" not in cmd
    assert "--max-turns" not in cmd  # Gemini doesn't support --max-turns
    print("  PASS: Gemini build command")


def test_gemini_build_resume_command():
    """Gemini resume includes --resume and --approval-mode."""
    p = _make_provider(GeminiCliProvider, model_flag=None)
    cmd = p._build_resume_command(
        client="gemini",
        session_id="gem-sess",
        prompt="Continue",
        mcp_config_path=None,
        max_turns=20,
    )
    assert "--resume" in cmd
    assert "gem-sess" in cmd
    assert "--approval-mode" in cmd
    assert "yolo" in cmd
    assert "--model" not in cmd  # No model flag when None
    print("  PASS: Gemini build resume command")


def test_copilot_build_command():
    """Copilot builds correct command."""
    p = _make_provider(CopilotCliProvider, model_flag="gpt-4o")
    cmd = p._build_command(
        client="copilot",
        prompt="Fix bug",
        session_id="cop-sess",
        mcp_config_path="/tmp/mcp.json",
        max_turns=10,
    )
    assert cmd[0] == "copilot"
    assert "-p" in cmd
    assert "--yolo" in cmd
    assert "--resume" in cmd
    assert "cop-sess" in cmd
    assert "--additional-mcp-config" in cmd
    assert "@/tmp/mcp.json" in cmd  # Copilot uses @ prefix
    assert "--model" in cmd
    assert "gpt-4o" in cmd
    print("  PASS: Copilot build command")


def test_copilot_build_resume_command():
    """Copilot resume command."""
    p = _make_provider(CopilotCliProvider, model_flag=None)
    cmd = p._build_resume_command(
        client="copilot",
        session_id="cop-resume",
        prompt="Continue",
        mcp_config_path=None,
        max_turns=10,
    )
    assert "--resume" in cmd
    assert "cop-resume" in cmd
    assert "--yolo" in cmd
    assert "--model" not in cmd
    assert "--additional-mcp-config" not in cmd
    print("  PASS: Copilot build resume command")


# ═══════════════════════════════════════════════════════════════════════════
# EVENT NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def test_claude_normalize_system():
    """Claude: system event → init."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({"type": "system", "session_id": "s1"})
    assert event.type == "init"
    assert event.session_id == "s1"
    print("  PASS: Claude normalize system → init")


def test_claude_normalize_assistant_text():
    """Claude: assistant text block → text."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hello world"}]},
    })
    assert event.type == "text"
    assert event.text == "Hello world"
    print("  PASS: Claude normalize assistant text")


def test_claude_normalize_assistant_tool_use():
    """Claude: assistant tool_use block → tool_start."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({
        "type": "assistant",
        "message": {"content": [{
            "type": "tool_use",
            "name": "Write",
            "input": {"path": "main.py"},
            "id": "tool-42",
        }]},
    })
    assert event.type == "tool_start"
    assert event.tool_name == "Write"
    assert event.tool_input == {"path": "main.py"}
    assert event.tool_id == "tool-42"
    print("  PASS: Claude normalize tool_use → tool_start")


def test_claude_normalize_user_tool_result():
    """Claude: user tool_result block → tool_end."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result",
            "content": "File created successfully",
        }]},
    })
    assert event.type == "tool_end"
    assert event.tool_result == "File created successfully"
    print("  PASS: Claude normalize tool_result → tool_end")


def test_claude_normalize_result():
    """Claude: result event → result."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({
        "type": "result",
        "session_id": "s2",
        "result": "Task complete",
        "usage": {"input_tokens": 100},
    })
    assert event.type == "result"
    assert event.session_id == "s2"
    assert event.result_text == "Task complete"
    print("  PASS: Claude normalize result")


def test_claude_normalize_empty_assistant():
    """Claude: assistant with empty content → empty text."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({
        "type": "assistant",
        "message": {"content": []},
    })
    assert event.type == "text"
    assert event.text == ""
    print("  PASS: Claude normalize empty assistant")


def test_claude_normalize_unknown_type():
    """Claude: unknown event type → empty text."""
    p = _make_provider(ClaudeCodeProvider)
    event = p._normalize_event({"type": "unknown_event", "data": "something"})
    assert event.type == "text"
    assert event.text == ""
    print("  PASS: Claude normalize unknown type")


def test_gemini_normalize_init():
    """Gemini: init event → init."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({"type": "init", "session_id": "gem-1"})
    assert event.type == "init"
    assert event.session_id == "gem-1"
    print("  PASS: Gemini normalize init")


def test_gemini_normalize_message():
    """Gemini: message event → text."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "message",
        "role": "assistant",
        "content": "Analyzing code...",
    })
    assert event.type == "text"
    assert event.text == "Analyzing code..."
    print("  PASS: Gemini normalize message → text")


def test_gemini_normalize_message_user():
    """Gemini: user message → empty text (skipped)."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "message",
        "role": "user",
        "content": "user input",
    })
    assert event.type == "text"
    assert event.text == ""
    print("  PASS: Gemini normalize user message (skip)")


def test_gemini_normalize_tool_use():
    """Gemini: tool_use event → tool_start."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "tool_use",
        "tool_name": "read_file",
        "parameters": {"path": "main.py"},
        "tool_id": "t-1",
    })
    assert event.type == "tool_start"
    assert event.tool_name == "read_file"
    assert event.tool_input == {"path": "main.py"}
    print("  PASS: Gemini normalize tool_use → tool_start")


def test_gemini_normalize_tool_result():
    """Gemini: tool_result event → tool_end."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "tool_result",
        "tool_id": "t-1",
        "output": "file contents here",
    })
    assert event.type == "tool_end"
    assert event.tool_result == "file contents here"
    print("  PASS: Gemini normalize tool_result → tool_end")


def test_gemini_normalize_result():
    """Gemini: result event → result."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "result",
        "session_id": "gem-2",
        "content": "All done",
        "stats": {"input_tokens": 500, "output_tokens": 200},
    })
    assert event.type == "result"
    assert event.session_id == "gem-2"
    assert event.result_text == "All done"
    print("  PASS: Gemini normalize result")


def test_gemini_normalize_error():
    """Gemini: error event → error."""
    p = _make_provider(GeminiCliProvider)
    event = p._normalize_event({
        "type": "error",
        "message": "Rate limit exceeded",
    })
    assert event.type == "error"
    assert event.text == "Rate limit exceeded"
    print("  PASS: Gemini normalize error")


def test_copilot_normalize_result():
    """Copilot: result JSON event → result."""
    p = _make_provider(CopilotCliProvider)
    event = p._normalize_event({
        "type": "result",
        "session_id": "cop-1",
        "result": "Task done",
    })
    assert event.type == "result"
    assert event.session_id == "cop-1"
    assert event.result_text == "Task done"
    print("  PASS: Copilot normalize result")


def test_copilot_normalize_system():
    """Copilot: system JSON event → init."""
    p = _make_provider(CopilotCliProvider)
    event = p._normalize_event({
        "type": "system",
        "session_id": "cop-init",
    })
    assert event.type == "init"
    assert event.session_id == "cop-init"
    print("  PASS: Copilot normalize system → init")


def test_copilot_normalize_unknown():
    """Copilot: unknown JSON → text with json dump."""
    p = _make_provider(CopilotCliProvider)
    event = p._normalize_event({"type": "progress", "percent": 50})
    assert event.type == "text"
    assert "progress" in event.text
    print("  PASS: Copilot normalize unknown → text JSON")


# ═══════════════════════════════════════════════════════════════════════════
# TOKEN USAGE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def test_claude_token_usage_standard():
    """Claude: extract from usage field."""
    p = _make_provider(ClaudeCodeProvider)
    usage = p.extract_token_usage({
        "usage": {"input_tokens": 1000, "output_tokens": 500},
        "total_cost_usd": 0.05,
    })
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.total_tokens == 1500
    assert usage.metadata.get("total_cost_usd") == 0.05
    print("  PASS: Claude token usage (standard)")


def test_claude_token_usage_model_usage():
    """Claude: extract from modelUsage field (alternative format)."""
    p = _make_provider(ClaudeCodeProvider)
    usage = p.extract_token_usage({
        "modelUsage": {
            "claude-sonnet-4": {"inputTokens": 2000, "outputTokens": 800},
        },
        "total_cost_usd": 0.10,
    })
    assert usage.input_tokens == 2000
    assert usage.output_tokens == 800
    assert usage.total_tokens == 2800
    print("  PASS: Claude token usage (modelUsage)")


def test_claude_token_usage_empty():
    """Claude: empty response → zero usage."""
    p = _make_provider(ClaudeCodeProvider)
    usage = p.extract_token_usage({})
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    print("  PASS: Claude token usage (empty)")


def test_claude_token_usage_non_dict():
    """Claude: non-dict response → zero usage."""
    p = _make_provider(ClaudeCodeProvider)
    usage = p.extract_token_usage("not a dict")
    assert usage.input_tokens == 0
    print("  PASS: Claude token usage (non-dict)")


def test_gemini_token_usage():
    """Gemini: extract from stats field."""
    p = _make_provider(GeminiCliProvider)
    usage = p.extract_token_usage({
        "stats": {"input_tokens": 300, "output_tokens": 150, "total_tokens": 450},
    })
    assert usage.input_tokens == 300
    assert usage.output_tokens == 150
    assert usage.total_tokens == 450
    print("  PASS: Gemini token usage")


def test_gemini_token_usage_fallback():
    """Gemini: fallback to usage field when stats missing."""
    p = _make_provider(GeminiCliProvider)
    usage = p.extract_token_usage({
        "usage": {"input_tokens": 100, "output_tokens": 50},
    })
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
    print("  PASS: Gemini token usage (fallback)")


def test_gemini_token_usage_empty():
    """Gemini: empty dict → zero usage."""
    p = _make_provider(GeminiCliProvider)
    usage = p.extract_token_usage({})
    assert usage.input_tokens == 0
    print("  PASS: Gemini token usage (empty)")


def test_copilot_token_usage():
    """Copilot: always returns empty usage (no token info in -p mode)."""
    p = _make_provider(CopilotCliProvider)
    usage = p.extract_token_usage({"result": "some output"})
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    print("  PASS: Copilot token usage (always empty)")


# ═══════════════════════════════════════════════════════════════════════════
# MCP CONFIG
# ═══════════════════════════════════════════════════════════════════════════

def test_mcp_config_dict_format():
    """All providers use mcpServers format."""
    for cls in (ClaudeCodeProvider, GeminiCliProvider, CopilotCliProvider):
        p = _make_provider(cls)
        result = p._build_mcp_config_dict({"server-1": {"command": "node"}})
        assert "mcpServers" in result
        assert "server-1" in result["mcpServers"]
    print("  PASS: MCP config dict format (all providers)")


def test_mcp_server_name_inference():
    """_infer_mcp_server_name extracts meaningful names."""
    test_cases = [
        (("npx", ["-y", "@modelcontextprotocol/server-filesystem"]),
         "server-filesystem"),
        (("python", ["mcp_servers/reporter.py"]), "python"),
        (("uvx", ["mcp-server-sqlite"]), "mcp-server-sqlite"),
        (("node", ["--experimental", "server.js"]), "server"),
    ]
    for (cmd, args), expected in test_cases:
        result = CliProviderBase._infer_mcp_server_name(cmd, args)
        assert result == expected, f"infer({cmd}, {args}): expected '{expected}', got '{result}'"
    print("  PASS: MCP server name inference")


# ═══════════════════════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLE RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def test_env_resolve_str():
    """_resolve_env_str replaces $ENV{VAR} placeholders."""
    env = {"HOME": "/home/user", "PORT": "8080"}

    result, ok = CliProviderBase._resolve_env_str("$ENV{HOME}/project", env)
    assert ok is True
    assert result == "/home/user/project"

    result, ok = CliProviderBase._resolve_env_str("http://localhost:$ENV{PORT}", env)
    assert ok is True
    assert result == "http://localhost:8080"

    print("  PASS: Env str resolution (success)")


def test_env_resolve_str_missing():
    """_resolve_env_str returns ok=False for missing vars."""
    env = {"HOME": "/home/user"}
    result, ok = CliProviderBase._resolve_env_str("$ENV{MISSING_VAR}/path", env)
    assert ok is False
    assert "$ENV{MISSING_VAR}" in result  # Unreplaced placeholder
    print("  PASS: Env str resolution (missing var)")


def test_env_resolve_str_no_placeholders():
    """_resolve_env_str with no placeholders passes through."""
    result, ok = CliProviderBase._resolve_env_str("plain text", {})
    assert ok is True
    assert result == "plain text"
    print("  PASS: Env str resolution (no placeholders)")


def test_env_resolve_dict():
    """_resolve_env_dict resolves all fields."""
    env = {"HOME": "/home/user", "KEY": "secret"}
    entry = {
        "command": "$ENV{HOME}/bin/server",
        "args": ["--key", "$ENV{KEY}"],
        "env": {"PATH": "$ENV{HOME}/bin"},
    }
    result = CliProviderBase._resolve_env_dict(entry, env)
    assert result is not None
    assert result["command"] == "/home/user/bin/server"
    assert result["args"] == ["--key", "secret"]
    assert result["env"]["PATH"] == "/home/user/bin"
    print("  PASS: Env dict resolution")


def test_env_resolve_dict_missing_returns_none():
    """_resolve_env_dict returns None if any var is missing."""
    env = {}
    entry = {"command": "$ENV{MISSING}/bin", "args": []}
    result = CliProviderBase._resolve_env_dict(entry, env)
    assert result is None
    print("  PASS: Env dict resolution (missing → None)")


# ═══════════════════════════════════════════════════════════════════════════
# PROMPT BUILDING
# ═══════════════════════════════════════════════════════════════════════════

def test_prompt_fresh_session():
    """Fresh session prompt includes system, user, working dir sections."""
    p = _make_provider(ClaudeCodeProvider)
    conversation = [
        Message(role=MessageRole.SYSTEM, content="You are a developer."),
        Message(role=MessageRole.USER, content="Write a hello world app."),
    ]
    prompt = p._build_prompt(conversation, tool_specs=None, workspace_root="/workspace")

    assert "[System Instructions]:" in prompt
    assert "You are a developer." in prompt
    assert "[User]:" in prompt
    assert "Write a hello world app." in prompt
    assert "[Working Directory]: /workspace" in prompt
    assert "[Turn Budget" in prompt
    assert "[Progress Reporting]" in prompt
    print("  PASS: Fresh session prompt building")


def test_prompt_continuation():
    """Continuation prompt only includes user/tool messages, no system."""
    p = _make_provider(ClaudeCodeProvider)
    conversation = [
        Message(role=MessageRole.SYSTEM, content="System prompt"),
        Message(role=MessageRole.USER, content="New instruction"),
    ]
    prompt = p._build_prompt(
        conversation, tool_specs=None,
        is_continuation=True, workspace_root="/workspace",
    )

    assert "[System Instructions]:" not in prompt  # Skipped for continuation
    assert "[User]:" in prompt
    assert "New instruction" in prompt
    assert "[Working Directory]" not in prompt  # Not added for continuation
    assert "[Turn Budget" not in prompt
    print("  PASS: Continuation prompt building")


def test_prompt_with_tool_specs():
    """Tool specs are formatted and included in fresh prompt."""
    from entity.tool_spec import ToolSpec

    p = _make_provider(ClaudeCodeProvider)
    conversation = [
        Message(role=MessageRole.USER, content="Create a file"),
    ]
    specs = [
        ToolSpec(name="save_file", description="Save a file to disk"),
        ToolSpec(name="run_command", description="Execute a shell command"),
    ]
    prompt = p._build_prompt(conversation, tool_specs=specs)

    assert "save_file" in prompt
    assert "run_command" in prompt
    assert "Write tool" in prompt  # save_file → mapped to Write
    assert "Bash tool" in prompt   # run_command → mapped to Bash
    print("  PASS: Prompt with tool specs")


# ═══════════════════════════════════════════════════════════════════════════
# WORKSPACE SNAPSHOT & DIFF
# ═══════════════════════════════════════════════════════════════════════════

def test_workspace_snapshot():
    """_snapshot_workspace captures file sizes and mtimes."""
    p = _make_provider(ClaudeCodeProvider)
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "main.py").write_text("print('hello')")
        (Path(tmpdir) / "readme.txt").write_text("README")

        snap = p._snapshot_workspace(tmpdir)
        assert "main.py" in snap
        assert "readme.txt" in snap
        assert len(snap) == 2
    print("  PASS: Workspace snapshot")


def test_workspace_snapshot_excludes():
    """_snapshot_workspace excludes __pycache__, .git, node_modules."""
    p = _make_provider(ClaudeCodeProvider)
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "main.py").write_text("code")
        (Path(tmpdir) / "__pycache__").mkdir()
        (Path(tmpdir) / "__pycache__" / "cached.pyc").write_text("cached")
        (Path(tmpdir) / ".git").mkdir()
        (Path(tmpdir) / ".git" / "config").write_text("git config")
        (Path(tmpdir) / "node_modules").mkdir()
        (Path(tmpdir) / "node_modules" / "pkg.js").write_text("module")

        snap = p._snapshot_workspace(tmpdir)
        assert "main.py" in snap
        assert len(snap) == 1  # Only main.py, rest excluded
    print("  PASS: Workspace snapshot excludes")


def test_workspace_snapshot_nonexistent():
    """_snapshot_workspace returns empty for nonexistent dir."""
    p = _make_provider(ClaudeCodeProvider)
    snap = p._snapshot_workspace("/nonexistent/path/xyz")
    assert snap == {}
    print("  PASS: Workspace snapshot nonexistent → empty")


def test_workspace_diff():
    """_diff_workspace detects created, modified, deleted files."""
    before = {
        "existing.py": (100, 1000),
        "deleted.py": (50, 900),
        "unchanged.py": (200, 800),
    }
    after = {
        "existing.py": (150, 1100),  # modified (different size/mtime)
        "unchanged.py": (200, 800),  # same
        "new_file.py": (75, 1200),   # created
    }

    changes = CliProviderBase._diff_workspace(before, after)
    change_map = {c["path"]: c["change"] for c in changes}

    assert change_map.get("existing.py") == "modified"
    assert change_map.get("new_file.py") == "created"
    assert change_map.get("deleted.py") == "deleted"
    assert "unchanged.py" not in change_map
    assert len(changes) == 3
    print("  PASS: Workspace diff (created, modified, deleted)")


# ═══════════════════════════════════════════════════════════════════════════
# STREAM PARSING
# ═══════════════════════════════════════════════════════════════════════════

def test_parse_stream_result_with_result_data():
    """_parse_stream_result uses result_data when available."""
    p = _make_provider(ClaudeCodeProvider)
    result = p._parse_stream_result(
        result_data={"type": "result", "result": "from result"},
        accumulated_text=["extra text"],
        session_id="s-1",
    )
    assert result["result"] == "from result"
    assert result["session_id"] == "s-1"
    print("  PASS: Parse stream result (with result_data)")


def test_parse_stream_result_no_result_data():
    """_parse_stream_result falls back to accumulated text."""
    p = _make_provider(ClaudeCodeProvider)
    result = p._parse_stream_result(
        result_data={},
        accumulated_text=["line 1", "line 2"],
        session_id="s-2",
    )
    assert result["result"] == "line 1\nline 2"
    assert result["session_id"] == "s-2"
    print("  PASS: Parse stream result (fallback to text)")


def test_parse_stream_result_empty():
    """_parse_stream_result with nothing → empty result."""
    p = _make_provider(ClaudeCodeProvider)
    result = p._parse_stream_result(
        result_data={},
        accumulated_text=[],
        session_id=None,
    )
    assert result["result"] == ""
    assert result["session_id"] is None
    print("  PASS: Parse stream result (empty)")


def test_parse_cli_output_json():
    """_parse_cli_output parses JSON stdout."""
    p = _make_provider(ClaudeCodeProvider)
    mock_result = MagicMock()
    mock_result.stdout = '{"type": "result", "result": "done"}'
    mock_result.stderr = ""
    mock_result.returncode = 0

    parsed = p._parse_cli_output(mock_result)
    assert parsed.get("type") == "result"
    assert parsed.get("result") == "done"
    print("  PASS: Parse CLI output (JSON)")


def test_parse_cli_output_ndjson_last_line():
    """_parse_cli_output finds result in last NDJSON line."""
    p = _make_provider(ClaudeCodeProvider)
    mock_result = MagicMock()
    mock_result.stdout = (
        '{"type": "system"}\n'
        '{"type": "assistant"}\n'
        '{"type": "result", "result": "final output"}\n'
    )
    mock_result.stderr = ""
    mock_result.returncode = 0

    parsed = p._parse_cli_output(mock_result)
    assert parsed.get("result") == "final output"
    print("  PASS: Parse CLI output (NDJSON last line)")


def test_parse_cli_output_plain_text():
    """_parse_cli_output handles plain text (non-JSON) output."""
    p = _make_provider(ClaudeCodeProvider)
    mock_result = MagicMock()
    mock_result.stdout = "This is plain text output\nWith multiple lines"
    mock_result.stderr = ""
    mock_result.returncode = 0

    parsed = p._parse_cli_output(mock_result)
    assert parsed.get("type") == "text_fallback"
    assert "plain text" in parsed.get("result", "")
    print("  PASS: Parse CLI output (plain text fallback)")


def test_parse_cli_output_empty():
    """_parse_cli_output handles empty stdout."""
    p = _make_provider(ClaudeCodeProvider)
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "some error"
    mock_result.returncode = 1

    parsed = p._parse_cli_output(mock_result)
    assert parsed.get("result") == ""
    assert "some error" in parsed.get("error", "")
    print("  PASS: Parse CLI output (empty stdout)")


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE BUILDING
# ═══════════════════════════════════════════════════════════════════════════

def test_build_stream_response_normal():
    """_build_stream_response builds ModelResponse from result."""
    p = _make_provider(ClaudeCodeProvider)
    resp = p._build_stream_response(
        raw_response={"result": "Task completed successfully"},
        stderr_text="",
    )
    assert resp.message.role == MessageRole.ASSISTANT
    assert resp.message.content == "Task completed successfully"
    assert resp.raw_response["result"] == "Task completed successfully"
    print("  PASS: Build stream response (normal)")


def test_build_stream_response_error():
    """_build_stream_response uses stderr when result is empty."""
    p = _make_provider(ClaudeCodeProvider)
    resp = p._build_stream_response(
        raw_response={"result": ""},
        stderr_text="Connection refused",
    )
    assert "Error" in resp.message.content
    assert "Connection refused" in resp.message.content
    print("  PASS: Build stream response (error fallback)")


# ═══════════════════════════════════════════════════════════════════════════
# STREAMING — NDJSON PARSING (base class)
# ═══════════════════════════════════════════════════════════════════════════

def test_streaming_full_ndjson():
    """_run_streaming parses complete NDJSON stream with callbacks."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "stream-1"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on it"}]}}'
        echo '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}, "id": "t-1"}]}}'
        echo '{"type": "user", "message": {"content": [{"type": "tool_result", "content": "file1.py file2.py"}]}}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Found files"}]}}'
        echo '{"type": "result", "session_id": "stream-1", "result": "All done"}'
    """))

    events = []

    def callback(event_type, data):
        events.append((event_type, data))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=callback, idle_timeout=10,
        )

        assert raw.get("error") is None
        assert raw.get("session_id") == "stream-1"
        assert "All done" in raw.get("result", "")

        event_types = [e[0] for e in events]
        assert "text_delta" in event_types
        assert "tool_start" in event_types
        assert "tool_end" in event_types
    finally:
        os.unlink(script)
    print("  PASS: Full NDJSON streaming with callbacks")


def test_streaming_skips_empty_lines():
    """_run_streaming skips empty and whitespace-only lines."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-empty"}'
        echo ''
        echo '   '
        echo '{"type": "result", "session_id": "s-empty", "result": "done"}'
    """))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )
        assert raw.get("error") is None
        assert raw.get("result") == "done"
    finally:
        os.unlink(script)
    print("  PASS: Streaming skips empty lines")


def test_streaming_skips_non_json():
    """_run_streaming skips non-JSON lines gracefully."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-nonjson"}'
        echo 'This is not JSON'
        echo 'Another plain line'
        echo '{"type": "result", "session_id": "s-nonjson", "result": "ok"}'
    """))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )
        assert raw.get("error") is None
        assert raw.get("result") == "ok"
    finally:
        os.unlink(script)
    print("  PASS: Streaming skips non-JSON lines")


def test_streaming_error_event():
    """_run_streaming captures error events."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-err"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Error: something failed"}]}}'
        echo '{"type": "result", "session_id": "s-err", "result": ""}'
    """))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )
        assert "Error: something failed" in raw.get("result", "")
    finally:
        os.unlink(script)
    print("  PASS: Streaming captures error text")


def test_streaming_process_exit_code():
    """_run_streaming captures process return code."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-rc"}'
        echo '{"type": "result", "result": "done"}'
        exit 0
    """))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )
        assert raw.get("_returncode") == 0
    finally:
        os.unlink(script)
    print("  PASS: Streaming captures return code")


def test_streaming_nonzero_exit():
    """_run_streaming handles non-zero exit code."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-fail"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "partial work"}]}}'
        exit 1
    """))

    try:
        p = _make_provider(ClaudeCodeProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )
        assert raw.get("_returncode") == 1
        assert "partial work" in raw.get("result", "")
    finally:
        os.unlink(script)
    print("  PASS: Streaming handles non-zero exit")


# ═══════════════════════════════════════════════════════════════════════════
# COPILOT PLAIN TEXT STREAMING
# ═══════════════════════════════════════════════════════════════════════════

def test_copilot_plain_text_streaming():
    """Copilot _run_streaming handles plain text output (not NDJSON)."""
    script = _create_mock_script(textwrap.dedent("""\
        echo "I'll start by reading the code..."
        echo "Now creating the file..."
        echo "Done! Here is the output."
    """))

    events = []

    def callback(event_type, data):
        events.append((event_type, data))

    try:
        p = _make_provider(CopilotCliProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=callback, idle_timeout=10,
        )

        assert raw.get("error") is None
        result = raw.get("result", "")
        assert "reading the code" in result
        assert "creating the file" in result
        assert "Done" in result

        text_events = [e for e in events if e[0] == "text_delta"]
        assert len(text_events) == 3
    finally:
        os.unlink(script)
    print("  PASS: Copilot plain text streaming")


def test_copilot_json_in_plain_mode():
    """Copilot _run_streaming handles JSON events if they appear."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "cop-json"}'
        echo "Some plain text output"
        echo '{"type": "result", "session_id": "cop-json", "result": "Final result"}'
    """))

    try:
        p = _make_provider(CopilotCliProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )

        assert raw.get("session_id") == "cop-json"
        result = raw.get("result", "")
        assert "Final result" in result
    finally:
        os.unlink(script)
    print("  PASS: Copilot handles JSON in plain text mode")


def test_copilot_empty_output():
    """Copilot _run_streaming handles zero output gracefully."""
    script = _create_mock_script(textwrap.dedent("""\
        # Exit immediately with no output
        exit 0
    """))

    try:
        p = _make_provider(CopilotCliProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=10,
        )

        assert raw.get("error") is None
        assert raw.get("result") == ""
        assert raw.get("_returncode") == 0
    finally:
        os.unlink(script)
    print("  PASS: Copilot empty output")


def test_copilot_stall_detection():
    """Copilot _run_streaming detects stalls in plain text mode."""
    script = _create_mock_script(textwrap.dedent("""\
        echo "Starting work..."
        sleep 30
    """))

    try:
        start = time.time()
        p = _make_provider(CopilotCliProvider)
        raw, stderr = p._run_streaming(
            cmd=[script], cwd=None, timeout=30,
            stream_callback=None, idle_timeout=3,
        )
        elapsed = time.time() - start

        assert raw.get("error") == "stall"
        assert elapsed < 10
    finally:
        os.unlink(script)
    print("  PASS: Copilot stall detection")


# ═══════════════════════════════════════════════════════════════════════════
# GEMINI MCP CONFIG OVERRIDE (settings.json)
# ═══════════════════════════════════════════════════════════════════════════

def test_gemini_mcp_creates_settings():
    """Gemini _create_mcp_config creates .gemini/settings.json."""
    p = _make_provider(GeminiCliProvider)
    p._gemini_settings_backup = None
    p._gemini_settings_path = None

    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock the base class to return a temp config file
        config_data = {"mcpServers": {"test-server": {"command": "node", "args": ["server.js"]}}}
        fd, temp_config = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f)

        with patch.object(CliProviderBase, '_create_mcp_config', return_value=temp_config):
            result = p._create_mcp_config(
                "node-1", "sess-1", 8000,
                workspace_root=tmpdir,
            )

        if result:
            settings_path = Path(tmpdir) / ".gemini" / "settings.json"
            assert settings_path.exists(), "settings.json should be created"
            data = json.loads(settings_path.read_text())
            assert "test-server" in data.get("mcpServers", {})

            # Cleanup
            p._cleanup_mcp_config(result)
            assert not settings_path.exists(), "settings.json should be removed on cleanup"

    print("  PASS: Gemini MCP creates/cleans settings.json")


def test_gemini_mcp_merges_existing():
    """Gemini _create_mcp_config merges with existing settings.json."""
    p = _make_provider(GeminiCliProvider)
    p._gemini_settings_backup = None
    p._gemini_settings_path = None

    with tempfile.TemporaryDirectory() as tmpdir:
        # Pre-create .gemini/settings.json with existing config
        gemini_dir = Path(tmpdir) / ".gemini"
        gemini_dir.mkdir()
        existing_settings = {
            "mcpServers": {"existing-server": {"command": "python", "args": ["existing.py"]}},
            "otherSetting": True,
        }
        (gemini_dir / "settings.json").write_text(json.dumps(existing_settings))

        # Mock the base class to return a temp config file
        config_data = {"mcpServers": {"new-server": {"command": "node", "args": ["new.js"]}}}
        fd, temp_config = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f)

        with patch.object(CliProviderBase, '_create_mcp_config', return_value=temp_config):
            result = p._create_mcp_config(
                "node-1", "sess-1", 8000,
                workspace_root=tmpdir,
            )

        if result:
            settings_path = Path(tmpdir) / ".gemini" / "settings.json"
            data = json.loads(settings_path.read_text())

            # Both servers should be present
            servers = data.get("mcpServers", {})
            assert "existing-server" in servers, "Existing server should be preserved"
            assert "new-server" in servers, "New server should be added"
            assert data.get("otherSetting") is True, "Other settings preserved"

            # Cleanup should restore original
            p._cleanup_mcp_config(result)
            restored = json.loads(settings_path.read_text())
            assert "existing-server" in restored.get("mcpServers", {})
            assert "new-server" not in restored.get("mcpServers", {})

    print("  PASS: Gemini MCP merges existing settings.json")


# ═══════════════════════════════════════════════════════════════════════════
# IS_CLI_PROVIDER TRAIT
# ═══════════════════════════════════════════════════════════════════════════

def test_is_cli_provider():
    """All CLI providers have is_cli_provider = True."""
    for cls in (ClaudeCodeProvider, GeminiCliProvider, CopilotCliProvider):
        p = _make_provider(cls)
        assert p.is_cli_provider is True
    print("  PASS: is_cli_provider trait")


# ═══════════════════════════════════════════════════════════════════════════
# PROVIDER NAME & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

def test_provider_constants():
    """Each provider has unique names and session files."""
    providers = {
        ClaudeCodeProvider: ("claude-code", "claude", ".claude_sessions.json"),
        GeminiCliProvider: ("gemini-cli", "gemini", ".gemini_sessions.json"),
        CopilotCliProvider: ("copilot-cli", "copilot", ".copilot_sessions.json"),
    }
    for cls, (name, binary, sessions_file) in providers.items():
        assert cls.PROVIDER_NAME == name, f"{cls.__name__}.PROVIDER_NAME"
        assert cls.CLI_BINARY_NAME == binary, f"{cls.__name__}.CLI_BINARY_NAME"
        assert cls.SESSIONS_FILE == sessions_file, f"{cls.__name__}.SESSIONS_FILE"
    print("  PASS: Provider constants")


# ═══════════════════════════════════════════════════════════════════════════
# BINARY DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def test_find_binary_in_path():
    """_find_binary finds binary via shutil.which."""
    p = object.__new__(ClaudeCodeProvider)
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        result = p._find_binary()
    assert result == "/usr/local/bin/claude"
    print("  PASS: Binary discovery via PATH")


def test_find_binary_fallback():
    """_find_binary uses fallback paths when not in PATH."""
    p = object.__new__(ClaudeCodeProvider)
    with patch("shutil.which", return_value=None), \
         patch("os.path.isfile") as mock_isfile:
        # First fallback doesn't exist, second does
        mock_isfile.side_effect = lambda x: x == "/opt/homebrew/bin/claude"
        result = p._find_binary()
    assert result == "/opt/homebrew/bin/claude"
    print("  PASS: Binary discovery via fallback paths")


def test_find_binary_not_found():
    """_find_binary raises FileNotFoundError when binary missing."""
    p = object.__new__(ClaudeCodeProvider)
    with patch("shutil.which", return_value=None), \
         patch("os.path.isfile", return_value=False):
        try:
            p._find_binary()
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError as e:
            assert "claude" in str(e).lower()
    print("  PASS: Binary not found raises error")


# ═══════════════════════════════════════════════════════════════════════════
# NORMALIZED EVENT DATACLASS
# ═══════════════════════════════════════════════════════════════════════════

def test_normalized_event_defaults():
    """NormalizedEvent has sensible defaults."""
    event = NormalizedEvent(type="text")
    assert event.session_id is None
    assert event.text is None
    assert event.tool_name is None
    assert event.tool_input is None
    assert event.raw == {}
    print("  PASS: NormalizedEvent defaults")


def test_normalized_event_full():
    """NormalizedEvent with all fields."""
    event = NormalizedEvent(
        type="tool_start",
        session_id="s-1",
        tool_name="Write",
        tool_input={"path": "main.py"},
        tool_id="t-1",
        raw={"type": "tool_use"},
    )
    assert event.type == "tool_start"
    assert event.tool_name == "Write"
    assert event.tool_id == "t-1"
    print("  PASS: NormalizedEvent full construction")


# ═══════════════════════════════════════════════════════════════════════════
# CALL_MODEL ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════

def test_call_model_timeout():
    """call_model returns timeout error when overall timeout fires."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "s-to"}'
        while true; do
            echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "working"}]}}'
            sleep 1
        done
    """))

    try:
        p = _make_provider(ClaudeCodeProvider, model_flag=None)
        p._binary_path = script
        p.config = _create_mock_config(node_id="test-to")
        p.config.workspace_root = None

        # Mock methods to avoid side effects
        p._create_mcp_config = lambda *a, **kw: None
        p._cleanup_mcp_config = lambda *a: None

        client = script
        conversation = [Message(role=MessageRole.USER, content="Test")]

        resp = p.call_model(
            client, conversation, [],
            timeout=3, idle_timeout=30,
        )

        assert "timed out" in resp.message.content.lower()
    finally:
        os.unlink(script)
    print("  PASS: call_model timeout handling")


def test_call_model_stall_no_session():
    """call_model handles stall when no session_id is available."""
    script = _create_mock_script(textwrap.dedent("""\
        # No system event (no session_id), then stall
        sleep 30
    """))

    try:
        p = _make_provider(ClaudeCodeProvider, model_flag=None)
        p._binary_path = script
        p.config = _create_mock_config(node_id="test-ns")
        p.config.workspace_root = None

        p._create_mcp_config = lambda *a, **kw: None
        p._cleanup_mcp_config = lambda *a: None

        ClaudeCodeProvider.clear_all_sessions()

        client = script
        conversation = [Message(role=MessageRole.USER, content="Test")]

        resp = p.call_model(
            client, conversation, [],
            timeout=30, idle_timeout=3,
        )

        assert "stalled" in resp.message.content.lower()
        assert "no session" in resp.message.content.lower()
    finally:
        os.unlink(script)
        ClaudeCodeProvider.clear_all_sessions()
    print("  PASS: call_model stall without session")


# ═══════════════════════════════════════════════════════════════════════════
# GITIGNORE-AWARE SCANNING
# ═══════════════════════════════════════════════════════════════════════════

def test_workspace_snapshot_gitignore():
    """_snapshot_workspace respects .gitignore patterns."""
    p = _make_provider(ClaudeCodeProvider)

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / ".gitignore").write_text("*.log\nbuild/\n")
        (Path(tmpdir) / "main.py").write_text("code")
        (Path(tmpdir) / "debug.log").write_text("log data")
        (Path(tmpdir) / "build").mkdir()
        (Path(tmpdir) / "build" / "output.js").write_text("built")

        snap = p._snapshot_workspace(tmpdir)

        assert "main.py" in snap
        # .gitignore is in root but starts with . → excluded by hidden dir rule
        # debug.log and build/ should be excluded by gitignore
        assert "debug.log" not in snap
        assert "build/output.js" not in snap
    print("  PASS: Workspace snapshot respects .gitignore")


# ═══════════════════════════════════════════════════════════════════════════
# RESUME HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def test_resume_for_completion():
    """_resume_for_completion uses correct prompt and session."""
    p = _make_provider(ClaudeCodeProvider, model_flag="sonnet")
    p.config = _create_mock_config(max_turns=20)

    calls = []

    def mock_build_resume(client, session_id, prompt, mcp_path, max_turns, **kw):
        calls.append({"session_id": session_id, "prompt": prompt, "max_turns": max_turns})
        return ["echo", "done"]

    def mock_run(cmd, cwd, timeout, callback, idle_timeout=900):
        return {"result": "completed output", "session_id": "s-comp"}, ""

    p._build_resume_command = mock_build_resume
    p._run_streaming = mock_run

    raw, stderr = p._resume_for_completion(
        client="claude",
        session_id="sess-incomplete",
        cwd=None,
        timeout=600,
        stream_callback=None,
        mcp_config_path=None,
    )

    assert len(calls) == 1
    assert calls[0]["session_id"] == "sess-incomplete"
    assert "incomplete" in calls[0]["prompt"].lower() or "complete" in calls[0]["prompt"].lower()
    assert raw.get("result") == "completed output"
    print("  PASS: _resume_for_completion")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  COMPREHENSIVE CLI PROVIDER TESTS")
    print("=" * 70)

    all_tests = [
        # Session Management
        ("Session Isolation", test_session_isolation),
        ("Session Save/Load", test_session_save_load),
        ("Session Get Nonexistent", test_session_get_nonexistent),
        ("Session Load Corrupt File", test_session_load_corrupt_file),

        # Model Flag Resolution
        ("Claude Model Flag", test_claude_model_flag),
        ("Gemini Model Flag", test_gemini_model_flag),
        ("Copilot Model Flag", test_copilot_model_flag),

        # Command Building
        ("Claude Build Command (fresh)", test_claude_build_command_fresh),
        ("Claude Build Command (resume+MCP)", test_claude_build_command_resume),
        ("Claude Build Resume Command", test_claude_build_resume_command),
        ("Gemini Build Command", test_gemini_build_command),
        ("Gemini Build Resume Command", test_gemini_build_resume_command),
        ("Copilot Build Command", test_copilot_build_command),
        ("Copilot Build Resume Command", test_copilot_build_resume_command),

        # Event Normalization — Claude
        ("Claude Normalize system→init", test_claude_normalize_system),
        ("Claude Normalize assistant text", test_claude_normalize_assistant_text),
        ("Claude Normalize tool_use→tool_start", test_claude_normalize_assistant_tool_use),
        ("Claude Normalize tool_result→tool_end", test_claude_normalize_user_tool_result),
        ("Claude Normalize result", test_claude_normalize_result),
        ("Claude Normalize empty assistant", test_claude_normalize_empty_assistant),
        ("Claude Normalize unknown type", test_claude_normalize_unknown_type),

        # Event Normalization — Gemini
        ("Gemini Normalize init", test_gemini_normalize_init),
        ("Gemini Normalize message→text", test_gemini_normalize_message),
        ("Gemini Normalize user message", test_gemini_normalize_message_user),
        ("Gemini Normalize tool_use→tool_start", test_gemini_normalize_tool_use),
        ("Gemini Normalize tool_result→tool_end", test_gemini_normalize_tool_result),
        ("Gemini Normalize result", test_gemini_normalize_result),
        ("Gemini Normalize error", test_gemini_normalize_error),

        # Event Normalization — Copilot
        ("Copilot Normalize result", test_copilot_normalize_result),
        ("Copilot Normalize system→init", test_copilot_normalize_system),
        ("Copilot Normalize unknown→text", test_copilot_normalize_unknown),

        # Token Usage
        ("Claude Token Usage (standard)", test_claude_token_usage_standard),
        ("Claude Token Usage (modelUsage)", test_claude_token_usage_model_usage),
        ("Claude Token Usage (empty)", test_claude_token_usage_empty),
        ("Claude Token Usage (non-dict)", test_claude_token_usage_non_dict),
        ("Gemini Token Usage", test_gemini_token_usage),
        ("Gemini Token Usage (fallback)", test_gemini_token_usage_fallback),
        ("Gemini Token Usage (empty)", test_gemini_token_usage_empty),
        ("Copilot Token Usage", test_copilot_token_usage),

        # MCP Config
        ("MCP Config Dict Format", test_mcp_config_dict_format),
        ("MCP Server Name Inference", test_mcp_server_name_inference),

        # Env Resolution
        ("Env Str Resolution", test_env_resolve_str),
        ("Env Str Missing Var", test_env_resolve_str_missing),
        ("Env Str No Placeholders", test_env_resolve_str_no_placeholders),
        ("Env Dict Resolution", test_env_resolve_dict),
        ("Env Dict Missing → None", test_env_resolve_dict_missing_returns_none),

        # Prompt Building
        ("Fresh Session Prompt", test_prompt_fresh_session),
        ("Continuation Prompt", test_prompt_continuation),
        ("Prompt with Tool Specs", test_prompt_with_tool_specs),

        # Workspace
        ("Workspace Snapshot", test_workspace_snapshot),
        ("Workspace Snapshot Excludes", test_workspace_snapshot_excludes),
        ("Workspace Snapshot Nonexistent", test_workspace_snapshot_nonexistent),
        ("Workspace Diff", test_workspace_diff),
        ("Workspace Snapshot Gitignore", test_workspace_snapshot_gitignore),

        # Stream Parsing
        ("Parse Stream Result (result_data)", test_parse_stream_result_with_result_data),
        ("Parse Stream Result (fallback)", test_parse_stream_result_no_result_data),
        ("Parse Stream Result (empty)", test_parse_stream_result_empty),
        ("Parse CLI Output (JSON)", test_parse_cli_output_json),
        ("Parse CLI Output (NDJSON)", test_parse_cli_output_ndjson_last_line),
        ("Parse CLI Output (plain text)", test_parse_cli_output_plain_text),
        ("Parse CLI Output (empty)", test_parse_cli_output_empty),

        # Response Building
        ("Build Response (normal)", test_build_stream_response_normal),
        ("Build Response (error)", test_build_stream_response_error),

        # Streaming Integration
        ("Full NDJSON Streaming", test_streaming_full_ndjson),
        ("Streaming Skips Empty Lines", test_streaming_skips_empty_lines),
        ("Streaming Skips Non-JSON", test_streaming_skips_non_json),
        ("Streaming Error Events", test_streaming_error_event),
        ("Streaming Exit Code 0", test_streaming_process_exit_code),
        ("Streaming Non-Zero Exit", test_streaming_nonzero_exit),

        # Copilot Plain Text
        ("Copilot Plain Text Streaming", test_copilot_plain_text_streaming),
        ("Copilot JSON in Plain Mode", test_copilot_json_in_plain_mode),
        ("Copilot Empty Output", test_copilot_empty_output),
        ("Copilot Stall Detection", test_copilot_stall_detection),

        # Gemini MCP Config
        ("Gemini MCP Settings.json", test_gemini_mcp_creates_settings),
        ("Gemini MCP Merge Existing", test_gemini_mcp_merges_existing),

        # Provider Traits
        ("is_cli_provider Trait", test_is_cli_provider),
        ("Provider Constants", test_provider_constants),

        # Binary Discovery
        ("Binary Discovery (PATH)", test_find_binary_in_path),
        ("Binary Discovery (fallback)", test_find_binary_fallback),
        ("Binary Not Found", test_find_binary_not_found),

        # NormalizedEvent
        ("NormalizedEvent Defaults", test_normalized_event_defaults),
        ("NormalizedEvent Full", test_normalized_event_full),

        # call_model
        ("call_model Timeout", test_call_model_timeout),
        ("call_model Stall No Session", test_call_model_stall_no_session),

        # Resume
        ("_resume_for_completion", test_resume_for_completion),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in all_tests:
        try:
            print(f"\n[TEST] {name}")
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            import traceback
            print(f"  FAIL: {e}")
            traceback.print_exc()

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(all_tests)} total")
    print(f"{'=' * 70}")

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")

    sys.exit(0 if failed == 0 else 1)
