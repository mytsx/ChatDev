"""Tests for HookSkillManager — hook config generation and cleanup."""

import json
import os
import tempfile
import shutil

import pytest

from entity.configs.node.hooks import AgentHooksConfig, HookHandler, HookMatcher, SubAgentConfig
from runtime.node.agent.providers.hook_skill_manager import (
    GeneratedFiles,
    HookSkillManager,
    _resolve_env_in_mcp_servers,
)


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    return str(tmp_path)


@pytest.fixture
def manager():
    return HookSkillManager()


@pytest.fixture
def sample_hooks_config():
    """A sample AgentHooksConfig with PreToolUse and Stop hooks."""
    return AgentHooksConfig(
        PreToolUse=[
            HookMatcher(
                matcher="Edit|Write|Bash",
                hooks=[
                    HookHandler(type="command", command="bash read-only-guard.sh", path="test"),
                ],
                path="test",
            )
        ],
        Stop=[
            HookMatcher(
                matcher="",
                hooks=[
                    HookHandler(
                        type="prompt",
                        prompt="Check if output contains REVIEW_PASS or REVIEW_FAIL.",
                        path="test",
                    ),
                ],
                path="test",
            )
        ],
        path="test",
    )


@pytest.fixture
def instruction_file(tmp_path):
    """Create a temporary instruction MD file."""
    md_file = tmp_path / "instructions" / "test.md"
    md_file.parent.mkdir(parents=True, exist_ok=True)
    md_file.write_text("# Test Instructions\n\nFollow these rules.")
    return str(md_file)


# ──────────────────────────────────────────────────────────────────
# Hook Schema Tests
# ──────────────────────────────────────────────────────────────────


class TestAgentHooksConfig:
    def test_from_dict_basic(self):
        data = {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write",
                    "hooks": [{"type": "command", "command": "echo test"}],
                }
            ],
        }
        config = AgentHooksConfig.from_dict(data, path="test")
        assert len(config.PreToolUse) == 1
        assert config.PreToolUse[0].matcher == "Edit|Write"
        assert config.PreToolUse[0].hooks[0].command == "echo test"
        assert config.has_hooks() is True

    def test_from_dict_empty(self):
        config = AgentHooksConfig.from_dict({}, path="test")
        assert config.has_hooks() is False

    def test_from_dict_prompt_hook(self):
        data = {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "prompt",
                            "prompt": "Check for REVIEW_PASS or REVIEW_FAIL",
                        }
                    ],
                }
            ],
        }
        config = AgentHooksConfig.from_dict(data, path="test")
        assert len(config.Stop) == 1
        assert config.Stop[0].hooks[0].type == "prompt"
        assert "REVIEW_PASS" in config.Stop[0].hooks[0].prompt

    def test_from_dict_invalid_handler_type(self):
        data = {
            "PreToolUse": [
                {
                    "hooks": [{"type": "invalid", "command": "echo"}],
                }
            ],
        }
        with pytest.raises(Exception):
            AgentHooksConfig.from_dict(data, path="test")

    def test_command_handler_requires_command(self):
        data = {
            "PreToolUse": [
                {"hooks": [{"type": "command"}]},
            ],
        }
        with pytest.raises(Exception):
            AgentHooksConfig.from_dict(data, path="test")

    def test_prompt_handler_requires_prompt(self):
        data = {
            "Stop": [
                {"hooks": [{"type": "prompt"}]},
            ],
        }
        with pytest.raises(Exception):
            AgentHooksConfig.from_dict(data, path="test")

    def test_handler_async_once_status_message(self):
        data = {
            "PostToolUse": [
                {
                    "matcher": "Write|Edit",
                    "hooks": [{
                        "type": "command",
                        "command": "eslint --fix",
                        "async_hook": True,
                        "once": False,
                        "status_message": "Auto-linting...",
                    }],
                }
            ],
        }
        config = AgentHooksConfig.from_dict(data, path="test")
        handler = config.PostToolUse[0].hooks[0]
        assert handler.async_hook is True
        assert handler.once is False
        assert handler.status_message == "Auto-linting..."

    def test_new_event_types(self):
        data = {
            "PostToolUseFailure": [
                {"hooks": [{"type": "command", "command": "echo failed"}]},
            ],
            "SessionEnd": [
                {"hooks": [{"type": "command", "command": "echo bye"}]},
            ],
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo prompt"}]},
            ],
            "SubagentStart": [
                {"hooks": [{"type": "command", "command": "echo sub-start"}]},
            ],
        }
        config = AgentHooksConfig.from_dict(data, path="test")
        assert len(config.PostToolUseFailure) == 1
        assert len(config.SessionEnd) == 1
        assert len(config.UserPromptSubmit) == 1
        assert len(config.SubagentStart) == 1
        assert config.has_hooks() is True


# ──────────────────────────────────────────────────────────────────
# Claude Code Hook Generation
# ──────────────────────────────────────────────────────────────────


class TestClaudeCodeHooks:
    def test_generates_settings_local_json(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )
        assert result.hook_config_path is not None
        assert result.hook_config_path.endswith("settings.local.json")

        with open(result.hook_config_path) as f:
            data = json.load(f)

        assert "hooks" in data
        assert "PreToolUse" in data["hooks"]
        assert "Stop" in data["hooks"]

        pre_tool = data["hooks"]["PreToolUse"][0]
        assert pre_tool["matcher"] == "Edit|Write|Bash"
        assert pre_tool["hooks"][0]["type"] == "command"

        stop = data["hooks"]["Stop"][0]
        assert stop["hooks"][0]["type"] == "prompt"

    def test_merges_with_existing_settings(self, manager, workspace, sample_hooks_config):
        # Pre-create settings with existing content
        claude_dir = os.path.join(workspace, ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        settings_path = os.path.join(claude_dir, "settings.local.json")
        with open(settings_path, "w") as f:
            json.dump({"allowedTools": ["Read", "Write"]}, f)

        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )

        # Should have created backup
        assert result.hook_config_backup is not None
        assert os.path.exists(result.hook_config_backup)

        # Should merge, not overwrite
        with open(result.hook_config_path) as f:
            data = json.load(f)
        assert "allowedTools" in data
        assert "hooks" in data

    def test_cleanup_restores_backup(self, manager, workspace, sample_hooks_config):
        # Pre-create settings
        claude_dir = os.path.join(workspace, ".claude")
        os.makedirs(claude_dir, exist_ok=True)
        settings_path = os.path.join(claude_dir, "settings.local.json")
        original = {"allowedTools": ["Read"]}
        with open(settings_path, "w") as f:
            json.dump(original, f)

        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )
        manager.cleanup(result)

        # Should restore original
        with open(settings_path) as f:
            data = json.load(f)
        assert data == original
        assert not os.path.exists(settings_path + ".chatdev_backup")

    def test_cleanup_removes_when_no_backup(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )
        assert os.path.exists(result.hook_config_path)
        manager.cleanup(result)
        assert not os.path.exists(result.hook_config_path)

    def test_async_once_status_in_generated_json(self, manager, workspace):
        config = AgentHooksConfig(
            PostToolUse=[
                HookMatcher(
                    matcher="Write|Edit",
                    hooks=[
                        HookHandler(
                            type="command",
                            command="eslint --fix",
                            async_hook=True,
                            once=False,
                            status_message="Linting...",
                            path="t",
                        ),
                    ],
                    path="t",
                )
            ],
            path="t",
        )
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        with open(result.hook_config_path) as f:
            data = json.load(f)

        hook = data["hooks"]["PostToolUse"][0]["hooks"][0]
        assert hook["async"] is True
        assert hook["statusMessage"] == "Linting..."
        # once=False should NOT appear in output
        assert "once" not in hook

    def test_new_events_in_generated_json(self, manager, workspace):
        config = AgentHooksConfig(
            PostToolUseFailure=[
                HookMatcher(
                    hooks=[HookHandler(type="command", command="echo retry", path="t")],
                    path="t",
                )
            ],
            SessionEnd=[
                HookMatcher(
                    hooks=[HookHandler(type="command", command="echo cleanup", path="t")],
                    path="t",
                )
            ],
            path="t",
        )
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        with open(result.hook_config_path) as f:
            data = json.load(f)

        assert "PostToolUseFailure" in data["hooks"]
        assert "SessionEnd" in data["hooks"]


# ──────────────────────────────────────────────────────────────────
# Gemini CLI Hook Generation
# ──────────────────────────────────────────────────────────────────


class TestGeminiCliHooks:
    def test_generates_gemini_settings(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )
        assert result.hook_config_path is not None
        assert result.hook_config_path.endswith("settings.json")

        with open(result.hook_config_path) as f:
            data = json.load(f)

        assert "hooks" in data
        hooks = data["hooks"]
        # Should have mapped events to Gemini equivalents
        events = [h["event"] for h in hooks]
        assert "BeforeTool" in events  # PreToolUse → BeforeTool

    def test_event_name_mapping(self, manager, workspace):
        config = AgentHooksConfig(
            PreToolUse=[
                HookMatcher(hooks=[HookHandler(type="command", command="echo pre", path="t")], path="t")
            ],
            PostToolUse=[
                HookMatcher(hooks=[HookHandler(type="command", command="echo post", path="t")], path="t")
            ],
            Stop=[
                HookMatcher(hooks=[HookHandler(type="command", command="echo stop", path="t")], path="t")
            ],
            path="t",
        )
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        with open(result.hook_config_path) as f:
            data = json.load(f)

        events = {h["event"] for h in data["hooks"]}
        assert "BeforeTool" in events
        assert "AfterTool" in events
        assert "AfterAgent" in events

    def test_merges_with_existing_gemini_settings(self, manager, workspace, sample_hooks_config):
        gemini_dir = os.path.join(workspace, ".gemini")
        os.makedirs(gemini_dir, exist_ok=True)
        settings_path = os.path.join(gemini_dir, "settings.json")
        with open(settings_path, "w") as f:
            json.dump({"mcpServers": {"test": {}}}, f)

        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )

        with open(result.hook_config_path) as f:
            data = json.load(f)
        assert "mcpServers" in data  # Existing content preserved
        assert "hooks" in data


# ──────────────────────────────────────────────────────────────────
# Copilot CLI Hook Generation
# ──────────────────────────────────────────────────────────────────


class TestCopilotCliHooks:
    def test_generates_separate_hook_files(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test-node",
        )
        assert len(result.copilot_hook_files) > 0
        for path in result.copilot_hook_files:
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert "event" in data

    def test_event_name_mapping(self, manager, workspace):
        config = AgentHooksConfig(
            PreToolUse=[
                HookMatcher(hooks=[HookHandler(type="command", command="echo pre", path="t")], path="t")
            ],
            Stop=[
                HookMatcher(hooks=[HookHandler(type="command", command="echo stop", path="t")], path="t")
            ],
            path="t",
        )
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        events = set()
        for path in result.copilot_hook_files:
            with open(path) as f:
                events.add(json.load(f)["event"])
        assert "preToolUse" in events
        assert "sessionEnd" in events

    def test_cleanup_removes_hook_files(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=sample_hooks_config,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        assert all(os.path.exists(p) for p in result.copilot_hook_files)
        manager.cleanup(result)
        assert all(not os.path.exists(p) for p in result.copilot_hook_files)


# ──────────────────────────────────────────────────────────────────
# Instruction File Tests
# ──────────────────────────────────────────────────────────────────


class TestInstructionFiles:
    def test_creates_claude_skill_file(self, manager, workspace, instruction_file):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Reviewer",
        )
        assert result.instruction_was_created is True
        assert result.instruction_path is not None
        assert "SKILL.md" in result.instruction_path
        assert os.path.exists(result.instruction_path)

        content = open(result.instruction_path).read()
        assert "Test Instructions" in content

    def test_creates_gemini_md(self, manager, workspace, instruction_file):
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Reviewer",
        )
        assert result.instruction_was_created is True
        assert result.instruction_path.endswith("GEMINI.md")

    def test_creates_copilot_instructions(self, manager, workspace, instruction_file):
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Reviewer",
        )
        assert result.instruction_was_created is True
        assert "copilot-instructions.md" in result.instruction_path

    def test_preserves_existing_instruction_file(self, manager, workspace, instruction_file):
        # Pre-create the target instruction file
        target = os.path.join(workspace, "GEMINI.md")
        with open(target, "w") as f:
            f.write("# My Custom Instructions")

        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Reviewer",
        )
        # Should NOT overwrite
        assert result.instruction_was_created is False
        assert result.instruction_path is None

        # Original content preserved
        with open(target) as f:
            assert "My Custom Instructions" in f.read()

    def test_cleanup_removes_created_instruction(self, manager, workspace, instruction_file):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="TestNode",
        )
        assert os.path.exists(result.instruction_path)
        manager.cleanup(result)
        assert not os.path.exists(result.instruction_path)

    def test_cleanup_does_not_remove_preserved_instruction(self, manager, workspace, instruction_file):
        # Pre-create target
        target = os.path.join(workspace, "GEMINI.md")
        with open(target, "w") as f:
            f.write("# Custom")

        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Test",
        )
        manager.cleanup(result)
        # Should still exist (was not created by us)
        assert os.path.exists(target)


# ──────────────────────────────────────────────────────────────────
# Keyword Extraction
# ──────────────────────────────────────────────────────────────────


class TestKeywordExtraction:
    def test_extracts_review_keywords(self, manager):
        prompt = "Check if the output contains REVIEW_PASS or REVIEW_FAIL."
        keywords = manager._extract_keywords_from_prompt(prompt)
        assert "REVIEW_PASS" in keywords
        assert "REVIEW_FAIL" in keywords

    def test_extracts_qa_keywords(self, manager):
        prompt = "Output must contain QA_PASS or QA_FAIL verdict."
        keywords = manager._extract_keywords_from_prompt(prompt)
        assert "QA_PASS" in keywords
        assert "QA_FAIL" in keywords

    def test_ignores_non_verdict_keywords(self, manager):
        prompt = "Check for REVIEW_PASS. Also verify CODE_QUALITY and ERROR_HANDLING."
        keywords = manager._extract_keywords_from_prompt(prompt)
        assert "REVIEW_PASS" in keywords
        assert "CODE_QUALITY" not in keywords
        assert "ERROR_HANDLING" not in keywords

    def test_empty_prompt(self, manager):
        assert manager._extract_keywords_from_prompt("") == []

    def test_deduplicates(self, manager):
        prompt = "REVIEW_PASS or REVIEW_FAIL. Must have REVIEW_PASS or REVIEW_FAIL."
        keywords = manager._extract_keywords_from_prompt(prompt)
        assert keywords.count("REVIEW_PASS") == 1
        assert keywords.count("REVIEW_FAIL") == 1


# ──────────────────────────────────────────────────────────────────
# Integration: Combined hooks + instructions
# ──────────────────────────────────────────────────────────────────


class TestCombined:
    def test_hooks_and_instructions_together(
        self, manager, workspace, sample_hooks_config, instruction_file
    ):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="Reviewer",
        )
        # Both should be created
        assert result.hook_config_path is not None
        assert result.instruction_was_created is True
        assert os.path.exists(result.hook_config_path)
        assert os.path.exists(result.instruction_path)

        # Cleanup should remove both
        manager.cleanup(result)
        assert not os.path.exists(result.hook_config_path)
        assert not os.path.exists(result.instruction_path)

    def test_no_hooks_no_instructions(self, manager, workspace):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="test",
        )
        assert result.hook_config_path is None
        assert result.instruction_path is None
        assert result.instruction_was_created is False
        # Cleanup should be safe
        manager.cleanup(result)

    def test_nonexistent_instruction_file(self, manager, workspace, sample_hooks_config):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file="/nonexistent/path.md",
            workspace_dir=workspace,
            node_id="test",
        )
        # Hooks should still work
        assert result.hook_config_path is not None
        # Instructions should be skipped
        assert result.instruction_was_created is False


# ──────────────────────────────────────────────────────────────────
# Sub-Agent Configuration Schema
# ──────────────────────────────────────────────────────────────────


class TestSubAgentConfig:
    def test_from_dict_valid(self):
        data = {
            "name": "code-researcher",
            "description": "Research API docs",
            "source": ".chatdev/workflows/agile_dev/agents/code-researcher.md",
        }
        cfg = SubAgentConfig.from_dict(data, path="test")
        assert cfg.name == "code-researcher"
        assert cfg.description == "Research API docs"
        assert cfg.source.endswith("code-researcher.md")

    def test_from_dict_missing_name(self):
        data = {"description": "Test", "source": "test.md"}
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")

    def test_from_dict_missing_description(self):
        data = {"name": "test", "source": "test.md"}
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")

    def test_from_dict_missing_source(self):
        data = {"name": "test", "description": "Test"}
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")

    def test_from_dict_with_tools_and_model(self):
        data = {
            "name": "code-researcher",
            "description": "Research API docs",
            "source": "agents/code-researcher.md",
            "tools": ["Read", "Grep", "Glob"],
            "model": "haiku",
            "max_turns": 10,
        }
        cfg = SubAgentConfig.from_dict(data, path="test")
        assert cfg.tools == ["Read", "Grep", "Glob"]
        assert cfg.model == "haiku"
        assert cfg.max_turns == 10

    def test_from_dict_with_disallowed_tools(self):
        data = {
            "name": "researcher",
            "description": "Safe researcher",
            "source": "agents/researcher.md",
            "disallowed_tools": ["Write", "Edit", "Bash"],
        }
        cfg = SubAgentConfig.from_dict(data, path="test")
        assert cfg.disallowed_tools == ["Write", "Edit", "Bash"]

    def test_from_dict_invalid_max_turns(self):
        data = {
            "name": "test",
            "description": "Test",
            "source": "test.md",
            "max_turns": 0,
        }
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")

    def test_from_dict_invalid_tools_type(self):
        data = {
            "name": "test",
            "description": "Test",
            "source": "test.md",
            "tools": "Read,Grep",  # Should be list
        }
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")


# ──────────────────────────────────────────────────────────────────
# Sub-Agent File Generation — Fixtures
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def sub_agent_source(tmp_path):
    """Create a sub-agent source MD file with YAML frontmatter."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    md_file = agents_dir / "code-researcher.md"
    md_file.write_text(
        "---\n"
        "name: code-researcher\n"
        "description: Research API docs\n"
        "tools:\n"
        "  - Read\n"
        "  - Grep\n"
        "  - Glob\n"
        "model: haiku\n"
        "maxTurns: 10\n"
        "---\n\n"
        "# Code Researcher\n\n"
        "You are a research-only assistant.\n"
    )
    return str(md_file)


@pytest.fixture
def sample_sub_agents(sub_agent_source):
    """A list of SubAgentConfig pointing to the temp source file."""
    return [
        SubAgentConfig(
            name="code-researcher",
            description="Research API docs",
            source=sub_agent_source,
            path="test",
        ),
    ]


@pytest.fixture
def sub_agents_with_overrides(sub_agent_source):
    """SubAgentConfig with model/tools/max_turns overrides."""
    return [
        SubAgentConfig(
            name="code-researcher",
            description="Research API docs",
            source=sub_agent_source,
            tools=["Read", "WebSearch"],
            disallowed_tools=["Bash"],
            model="sonnet",
            max_turns=20,
            path="test",
        ),
    ]


# ──────────────────────────────────────────────────────────────────
# Sub-Agent File Generation — Claude Code
# ──────────────────────────────────────────────────────────────────


class TestSubAgentClaude:
    def test_generates_claude_agent_file(self, manager, workspace, sample_sub_agents):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert len(result.sub_agent_files) == 1
        path = result.sub_agent_files[0]
        assert ".claude/agents/code-researcher.md" in path
        assert os.path.exists(path)

        content = open(path).read()
        assert "name: code-researcher" in content
        assert "tools: Read, Grep, Glob" in content
        assert "# Code Researcher" in content

    def test_preserves_existing_agent_file(self, manager, workspace, sample_sub_agents):
        # Pre-create the target file
        target_dir = os.path.join(workspace, ".claude", "agents")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, "code-researcher.md")
        with open(target, "w") as f:
            f.write("# My Custom Agent\n")

        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        # Should NOT create (file existed)
        assert len(result.sub_agent_files) == 0

        # Original preserved
        with open(target) as f:
            assert "My Custom Agent" in f.read()

    def test_cleanup_removes_created_agent(self, manager, workspace, sample_sub_agents):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert os.path.exists(result.sub_agent_files[0])
        manager.cleanup(result)
        assert not os.path.exists(result.sub_agent_files[0])

    def test_model_and_max_turns_from_source(self, manager, workspace, sample_sub_agents):
        """Source frontmatter model/maxTurns should appear in output when no override."""
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        content = open(result.sub_agent_files[0]).read()
        assert "model: haiku" in content
        assert "maxTurns: 10" in content

    def test_config_overrides_source_frontmatter(self, manager, workspace, sub_agents_with_overrides):
        """SubAgentConfig fields should override source frontmatter values."""
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sub_agents_with_overrides,
        )
        content = open(result.sub_agent_files[0]).read()
        # Config overrides source frontmatter
        assert "tools: Read, WebSearch" in content
        assert "disallowedTools: Bash" in content
        assert "model: sonnet" in content
        assert "maxTurns: 20" in content


# ──────────────────────────────────────────────────────────────────
# Sub-Agent File Generation — Gemini CLI
# ──────────────────────────────────────────────────────────────────


class TestSubAgentGemini:
    def test_generates_gemini_agent_file(self, manager, workspace, sample_sub_agents):
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert len(result.sub_agent_files) == 1
        path = result.sub_agent_files[0]
        assert ".gemini/agents/code-researcher.md" in path
        assert os.path.exists(path)

        content = open(path).read()
        assert "name: code-researcher" in content
        # Gemini uses different tool names
        assert "read_file" in content
        assert "grep_search" in content

    def test_cleanup_removes_gemini_agent(self, manager, workspace, sample_sub_agents):
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert os.path.exists(result.sub_agent_files[0])
        manager.cleanup(result)
        assert not os.path.exists(result.sub_agent_files[0])

    def test_gemini_model_mapping(self, manager, workspace, sub_agents_with_overrides):
        """Gemini should map 'sonnet' → 'gemini-2.5-pro'."""
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sub_agents_with_overrides,
        )
        content = open(result.sub_agent_files[0]).read()
        assert "model: gemini-2.5-pro" in content
        assert "max_turns: 20" in content
        # Tools should be remapped
        assert "read_file" in content
        assert "web_search" in content


# ──────────────────────────────────────────────────────────────────
# Sub-Agent File Generation — Copilot CLI
# ──────────────────────────────────────────────────────────────────


class TestSubAgentCopilot:
    def test_generates_copilot_agent_file(self, manager, workspace, sample_sub_agents):
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert len(result.sub_agent_files) == 1
        path = result.sub_agent_files[0]
        assert ".github/agents/code-researcher.md" in path
        assert os.path.exists(path)

        content = open(path).read()
        assert "name: code-researcher" in content
        assert "# Code Researcher" in content

    def test_preserves_existing_copilot_agent(self, manager, workspace, sample_sub_agents):
        target_dir = os.path.join(workspace, ".github", "agents")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, "code-researcher.md")
        with open(target, "w") as f:
            f.write("# Existing Copilot Agent\n")

        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        assert len(result.sub_agent_files) == 0
        with open(target) as f:
            assert "Existing Copilot Agent" in f.read()

    def test_copilot_model_mapping(self, manager, workspace, sub_agents_with_overrides):
        """Copilot should map 'sonnet' → 'claude-sonnet-4-5'."""
        result = manager.generate(
            provider_type="copilot-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sub_agents_with_overrides,
        )
        content = open(result.sub_agent_files[0]).read()
        assert "model: claude-sonnet-4-5" in content


# ──────────────────────────────────────────────────────────────────
# Sub-Agent + Hooks Combined
# ──────────────────────────────────────────────────────────────────


class TestSubAgentCombined:
    def test_sub_agents_with_hooks_and_instructions(
        self, manager, workspace, sample_hooks_config, instruction_file, sample_sub_agents
    ):
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=sample_hooks_config,
            instructions_file=instruction_file,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=sample_sub_agents,
        )
        # All three should work together
        assert result.hook_config_path is not None
        assert result.instruction_was_created is True
        assert len(result.sub_agent_files) == 1

        # Cleanup all
        manager.cleanup(result)
        assert not os.path.exists(result.hook_config_path)
        assert not os.path.exists(result.instruction_path)
        assert not os.path.exists(result.sub_agent_files[0])

    def test_nonexistent_source_skipped(self, manager, workspace):
        bad_agents = [
            SubAgentConfig(
                name="ghost-agent",
                description="This source does not exist",
                source="/nonexistent/ghost.md",
                path="test",
            ),
        ]
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=bad_agents,
        )
        assert len(result.sub_agent_files) == 0


# ──────────────────────────────────────────────────────────────────
# MCP Server Resolution
# ──────────────────────────────────────────────────────────────────


class TestMcpServerResolution:
    def test_resolve_env_placeholders(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "secret-123")
        servers = {
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp", "--api-key", "$ENV{MY_API_KEY}"],
            }
        }
        resolved = _resolve_env_in_mcp_servers(servers)
        assert resolved["context7"]["args"][-1] == "secret-123"
        # Original should not be mutated
        assert servers["context7"]["args"][-1] == "$ENV{MY_API_KEY}"

    def test_resolve_env_in_nested_dict(self, monkeypatch):
        monkeypatch.setenv("DB_PASS", "hunter2")
        servers = {
            "oracle": {
                "command": "python",
                "args": ["server.py"],
                "env": {"PASSWORD": "$ENV{DB_PASS}", "HOST": "localhost"},
            }
        }
        resolved = _resolve_env_in_mcp_servers(servers)
        assert resolved["oracle"]["env"]["PASSWORD"] == "hunter2"
        assert resolved["oracle"]["env"]["HOST"] == "localhost"

    def test_unresolved_placeholder_left_as_is(self):
        servers = {
            "test": {
                "command": "npx",
                "args": ["--key", "$ENV{NONEXISTENT_VAR}"],
            }
        }
        resolved = _resolve_env_in_mcp_servers(servers)
        assert resolved["test"]["args"][-1] == "$ENV{NONEXISTENT_VAR}"

    def test_empty_servers_dict(self):
        assert _resolve_env_in_mcp_servers({}) == {}

    def test_non_dict_server_value_skipped(self):
        servers = {"bad": "not_a_dict", "good": {"command": "echo"}}
        resolved = _resolve_env_in_mcp_servers(servers)
        assert resolved["bad"] == "not_a_dict"
        assert resolved["good"]["command"] == "echo"


class TestSubAgentMcpInClaude:
    @pytest.fixture
    def sub_agent_source_with_mcp(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        md_file = agents_dir / "researcher.md"
        md_file.write_text(
            "---\n"
            "name: researcher\n"
            "description: Research with MCP\n"
            "tools:\n"
            "  - Read\n"
            "  - Grep\n"
            "model: haiku\n"
            "maxTurns: 10\n"
            "---\n\n"
            "# Researcher\n\nUse Context7 for research.\n"
        )
        return str(md_file)

    def test_mcp_servers_in_claude_frontmatter(self, manager, workspace, sub_agent_source_with_mcp, monkeypatch):
        monkeypatch.setenv("CONTEXT7_API_KEY", "test-key-abc")
        agents = [
            SubAgentConfig(
                name="researcher",
                description="Research with MCP",
                source=sub_agent_source_with_mcp,
                mcp_servers={
                    "context7": {
                        "command": "npx",
                        "args": ["-y", "@upstash/context7-mcp", "--api-key", "$ENV{CONTEXT7_API_KEY}"],
                    }
                },
                path="test",
            ),
        ]
        result = manager.generate(
            provider_type="claude-code",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=agents,
        )
        assert len(result.sub_agent_files) == 1
        content = open(result.sub_agent_files[0]).read()
        assert "mcpServers:" in content
        assert "context7:" in content
        assert "test-key-abc" in content
        # $ENV{} should be resolved
        assert "$ENV{CONTEXT7_API_KEY}" not in content

    def test_mcp_servers_not_in_gemini(self, manager, workspace, sub_agent_source_with_mcp):
        """Gemini sub-agents should NOT include mcpServers (they inherit from workspace)."""
        agents = [
            SubAgentConfig(
                name="researcher",
                description="Research with MCP",
                source=sub_agent_source_with_mcp,
                mcp_servers={
                    "context7": {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]},
                },
                path="test",
            ),
        ]
        result = manager.generate(
            provider_type="gemini-cli",
            hooks_config=None,
            instructions_file=None,
            workspace_dir=workspace,
            node_id="dev",
            sub_agents=agents,
        )
        content = open(result.sub_agent_files[0]).read()
        assert "mcpServers" not in content

    def test_mcp_servers_from_dict_parsing(self):
        data = {
            "name": "test-agent",
            "description": "Test MCP",
            "source": "test.md",
            "mcp_servers": {
                "myserver": {"command": "npx", "args": ["-y", "my-mcp"]},
            },
        }
        cfg = SubAgentConfig.from_dict(data, path="test")
        assert cfg.mcp_servers == {"myserver": {"command": "npx", "args": ["-y", "my-mcp"]}}

    def test_mcp_servers_invalid_type_raises(self):
        data = {
            "name": "test",
            "description": "Test",
            "source": "test.md",
            "mcp_servers": "not-a-dict",
        }
        with pytest.raises(Exception):
            SubAgentConfig.from_dict(data, path="test")
