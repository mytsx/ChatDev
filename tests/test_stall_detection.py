"""Stall detection & auto-recovery integration tests.

Tests the idle timer mechanism in CliProviderBase._run_streaming() by
using mock subprocesses that simulate real NDJSON streams with stalls.

Run:
    uv run python tests/test_stall_detection.py
"""

import json
import os
import sys
import stat
import tempfile
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.node.agent.providers.claude_code_provider import ClaudeCodeProvider
from runtime.node.agent.providers.gemini_cli_provider import GeminiCliProvider
from runtime.node.agent.providers.cli_provider_base import NormalizedEvent


# ─── Helper: Create mock CLI scripts ───────────────────────────────────────

def _create_mock_script(script_body: str) -> str:
    """Create a temporary executable script that simulates a CLI tool."""
    fd, path = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write("#!/bin/bash\n")
        f.write(script_body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def _create_mock_config():
    """Create a minimal AgentConfig-like mock."""
    config = MagicMock()
    config.node_id = "test-node"
    config.workspace_root = None
    config.max_turns = 5
    config.tooling = []
    return config


# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Normal completion — no stall
# ═══════════════════════════════════════════════════════════════════════════

def test_normal_completion():
    """Process outputs NDJSON and exits normally → no stall, no timeout."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_normal"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello world"}]}}'
        echo '{"type": "result", "session_id": "sess_normal", "result": "All done"}'
    """))

    try:
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=5,
        )

        assert raw.get("error") is None, f"Unexpected error: {raw.get('error')}"
        assert raw.get("session_id") == "sess_normal"
        assert "All done" in raw.get("result", "")
        print("  PASS: Normal completion — no stall detected")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Idle stall — process goes silent
# ═══════════════════════════════════════════════════════════════════════════

def test_idle_stall():
    """Process outputs some events, then goes silent → stall detected."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_stall"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Starting work..."}]}}'
        # Now go silent — sleep longer than idle_timeout
        sleep 30
        echo '{"type": "result", "session_id": "sess_stall", "result": "This should never appear"}'
    """))

    try:
        start = time.time()
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=3,  # 3 seconds idle → stall
        )
        elapsed = time.time() - start

        assert raw.get("error") == "stall", f"Expected 'stall' error, got: {raw.get('error')}"
        assert raw.get("session_id") == "sess_stall", f"Session ID should be preserved: {raw.get('session_id')}"
        assert elapsed < 10, f"Should detect stall in ~3s, took {elapsed:.1f}s"
        print(f"  PASS: Idle stall detected in {elapsed:.1f}s (idle_timeout=3s)")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 3: Activity resets idle timer
# ═══════════════════════════════════════════════════════════════════════════

def test_activity_resets_timer():
    """Process outputs events every 2s with idle_timeout=4s → no stall."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_active"}'
        sleep 2
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 1"}]}}'
        sleep 2
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 2"}]}}'
        sleep 2
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Step 3"}]}}'
        echo '{"type": "result", "session_id": "sess_active", "result": "Done after slow work"}'
    """))

    try:
        start = time.time()
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=4,  # 4s idle, but events come every 2s → should NOT stall
        )
        elapsed = time.time() - start

        assert raw.get("error") is None, f"Should NOT stall (activity every 2s), got: {raw.get('error')}"
        assert "Done after slow work" in raw.get("result", "")
        print(f"  PASS: Activity resets timer — completed in {elapsed:.1f}s without stall")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 4: Overall timeout fires before idle stall
# ═══════════════════════════════════════════════════════════════════════════

def test_overall_timeout_priority():
    """Overall timeout (4s) fires before idle timeout (10s) → timeout error."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_timeout"}'
        # Keep producing output every 2s so idle timer resets, but exceed overall timeout
        while true; do
            echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "working..."}]}}'
            sleep 2
        done
    """))

    try:
        start = time.time()
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=4,         # overall: 4s
            stream_callback=None,
            idle_timeout=10,   # idle: 10s — should NOT fire first
        )
        elapsed = time.time() - start

        assert raw.get("error") == "timeout", f"Expected 'timeout' (overall), got: {raw.get('error')}"
        assert elapsed < 8, f"Should timeout at ~4s, took {elapsed:.1f}s"
        print(f"  PASS: Overall timeout ({elapsed:.1f}s) fires before idle stall")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 5: Stall with stream_callback — stall_detected event fires
# ═══════════════════════════════════════════════════════════════════════════

def test_stall_callback():
    """Stall triggers stream_callback('stall_detected', ...) in call_model flow."""
    # This tests the call_model stall handler indirectly by checking
    # that _run_streaming returns the right error for callback handling.
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_cb"}'
        sleep 30
    """))

    callback_events = []

    def mock_callback(event_type, data):
        callback_events.append((event_type, data))

    try:
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=mock_callback,
            idle_timeout=3,
        )

        assert raw.get("error") == "stall"
        assert raw.get("session_id") == "sess_cb"
        # Note: stall_detected callback is fired in call_model(), not _run_streaming()
        # So here we just verify the error propagation is correct.
        print("  PASS: Stall error propagated correctly for callback handling")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 6: Gemini CLI stall detection
# ═══════════════════════════════════════════════════════════════════════════

def test_gemini_stall():
    """Gemini CLI also uses _run_streaming from base → stall detection works."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "init", "session_id": "gem_stall"}'
        echo '{"type": "message", "role": "assistant", "content": "Analyzing..."}'
        # Stall here
        sleep 30
    """))

    try:
        start = time.time()
        provider = object.__new__(GeminiCliProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=3,
        )
        elapsed = time.time() - start

        assert raw.get("error") == "stall", f"Gemini: expected 'stall', got: {raw.get('error')}"
        assert raw.get("session_id") == "gem_stall"
        assert elapsed < 10
        print(f"  PASS: Gemini CLI stall detected in {elapsed:.1f}s")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 7: Tool-call timeout — single tool blocks too long
# ═══════════════════════════════════════════════════════════════════════════

def test_tool_call_timeout():
    """A tool_start without tool_end for too long → stall via tool_call_timeout.

    Note: tool_call_timeout checks happen when the NEXT line arrives.
    So the process must output a line after the tool has been pending too long.
    If it goes fully silent, the idle timer catches it instead.
    """
    # Emit tool_start, then wait, then emit another line → tool timeout check triggers
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_tool"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "sleep 999"}, "id": "tool-1"}]}}'
        # Sleep longer than tool_call_timeout (3s), then emit something
        sleep 5
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "still here"}]}}'
    """))

    try:
        start = time.time()
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=3,  # tool_call_timeout = idle_timeout = 3s
        )
        elapsed = time.time() - start

        # Either idle timer or tool_call_timeout should catch this
        assert raw.get("error") == "stall", f"Expected stall, got: {raw.get('error')}"
        print(f"  PASS: Tool-call timeout/stall detected in {elapsed:.1f}s")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 8: Session preserved on stall (resume flow)
# ═══════════════════════════════════════════════════════════════════════════

def test_session_preserved_on_stall():
    """Session ID is returned in stall error → call_model can resume."""
    script = _create_mock_script(textwrap.dedent("""\
        echo '{"type": "system", "session_id": "sess_12345_resume_me"}'
        echo '{"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on task..."}]}}'
        sleep 30
    """))

    try:
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=3,
        )

        assert raw.get("error") == "stall"
        assert raw.get("session_id") == "sess_12345_resume_me", \
            f"Session must be preserved for resume! Got: {raw.get('session_id')}"
        print("  PASS: Session ID preserved on stall for auto-resume")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 9: Immediate stall — no output at all
# ═══════════════════════════════════════════════════════════════════════════

def test_immediate_stall():
    """Process starts but produces zero output → stall after idle_timeout."""
    script = _create_mock_script(textwrap.dedent("""\
        # Complete silence from start
        sleep 30
    """))

    try:
        start = time.time()
        provider = object.__new__(ClaudeCodeProvider)
        raw, stderr = provider._run_streaming(
            cmd=[script],
            cwd=None,
            timeout=30,
            stream_callback=None,
            idle_timeout=3,
        )
        elapsed = time.time() - start

        assert raw.get("error") == "stall", f"Expected stall on silence, got: {raw.get('error')}"
        assert raw.get("session_id") is None  # No session was ever sent
        assert elapsed < 8
        print(f"  PASS: Immediate stall (zero output) detected in {elapsed:.1f}s")
    finally:
        os.unlink(script)


# ═══════════════════════════════════════════════════════════════════════════
# Test 10: _resume_after_stall builds correct command
# ═══════════════════════════════════════════════════════════════════════════

def test_resume_after_stall_command():
    """_resume_after_stall calls _build_resume_command and _run_streaming."""
    # Just verify it constructs the right command without actually running it
    provider = object.__new__(ClaudeCodeProvider)
    provider.config = _create_mock_config()
    provider._model_flag = "sonnet"

    calls = []

    def mock_build_resume(client, session_id, prompt, mcp_path, max_turns, **kw):
        calls.append({
            "client": client, "session_id": session_id,
            "prompt": prompt, "max_turns": max_turns,
        })
        return ["echo", '{"type": "result", "result": "resumed"}']

    def mock_run_streaming(cmd, cwd, timeout, callback, idle_timeout=900):
        return {"result": "resumed", "session_id": "sess_resumed"}, ""

    provider._build_resume_command = mock_build_resume
    provider._run_streaming = mock_run_streaming

    raw, stderr = provider._resume_after_stall(
        client="claude",
        session_id="sess_stalled_123",
        cwd="/tmp/workspace",
        timeout=600,
        stream_callback=None,
        mcp_config_path=None,
        idle_timeout=300,
    )

    assert len(calls) == 1
    assert calls[0]["session_id"] == "sess_stalled_123"
    assert "interrupted" in calls[0]["prompt"].lower() or "inactivity" in calls[0]["prompt"].lower()
    assert raw.get("result") == "resumed"
    print("  PASS: _resume_after_stall builds correct resume command")


# ═══════════════════════════════════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  STALL DETECTION & AUTO-RECOVERY TESTS")
    print("=" * 60 + "\n")

    tests = [
        ("1. Normal completion", test_normal_completion),
        ("2. Idle stall detection", test_idle_stall),
        ("3. Activity resets idle timer", test_activity_resets_timer),
        ("4. Overall timeout priority", test_overall_timeout_priority),
        ("5. Stall callback propagation", test_stall_callback),
        ("6. Gemini CLI stall", test_gemini_stall),
        ("7. Tool-call timeout", test_tool_call_timeout),
        ("8. Session preserved on stall", test_session_preserved_on_stall),
        ("9. Immediate stall (zero output)", test_immediate_stall),
        ("10. Resume command construction", test_resume_after_stall_command),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            print(f"[TEST] {name}")
            test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAIL: {e}")

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {len(tests)} total")
    print(f"{'=' * 60}")

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")

    sys.exit(0 if failed == 0 else 1)
