"""Hook and sub-agent configuration dataclasses for CLI provider agents.

Defines a provider-agnostic hook schema and sub-agent definitions that
HookSkillManager translates into provider-specific formats
(Claude Code, Gemini CLI, Copilot CLI).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from entity.configs.base import (
    BaseConfig,
    ConfigError,
    ConfigFieldSpec,
    extend_path,
    optional_bool,
    optional_str,
    require_mapping,
)


@dataclass
class HookHandler(BaseConfig):
    """A single hook handler — either a shell command or a prompt-based check."""

    type: str = "command"  # command | prompt | agent (prompt/agent: Claude Code only)
    command: Optional[str] = None  # shell command (type=command)
    prompt: Optional[str] = None  # LLM prompt (type=prompt|agent, Claude Code only)
    timeout: Optional[int] = None  # seconds
    model: Optional[str] = None  # model override (type=prompt|agent)
    async_hook: bool = False  # Run hook in background (non-blocking, Claude Code)
    once: bool = False  # Run hook only once per session (Claude Code)
    status_message: Optional[str] = None  # Custom spinner message while hook runs (Claude Code)

    FIELD_SPECS = {
        "type": ConfigFieldSpec(
            name="type",
            display_name="Handler Type",
            type_hint="str",
            required=False,
            default="command",
            description="Hook handler type: command (shell), prompt (LLM check), agent (LLM agent)",
        ),
        "command": ConfigFieldSpec(
            name="command",
            display_name="Shell Command",
            type_hint="str",
            required=False,
            description="Shell command to execute (type=command)",
        ),
        "prompt": ConfigFieldSpec(
            name="prompt",
            display_name="Prompt",
            type_hint="text",
            required=False,
            description="LLM prompt for validation (type=prompt|agent, Claude Code only)",
        ),
        "timeout": ConfigFieldSpec(
            name="timeout",
            display_name="Timeout",
            type_hint="int",
            required=False,
            description="Execution timeout in seconds",
        ),
        "model": ConfigFieldSpec(
            name="model",
            display_name="Model Override",
            type_hint="str",
            required=False,
            description="Model override for prompt/agent hooks",
            advance=True,
        ),
        "async_hook": ConfigFieldSpec(
            name="async_hook",
            display_name="Async",
            type_hint="bool",
            required=False,
            default=False,
            description="Run hook in background (non-blocking). Useful for auto-lint/test after edits (Claude Code)",
            advance=True,
        ),
        "once": ConfigFieldSpec(
            name="once",
            display_name="Run Once",
            type_hint="bool",
            required=False,
            default=False,
            description="Run hook only once per session, not on every event (Claude Code)",
            advance=True,
        ),
        "status_message": ConfigFieldSpec(
            name="status_message",
            display_name="Status Message",
            type_hint="str",
            required=False,
            description="Custom spinner message displayed while hook runs (Claude Code)",
            advance=True,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "HookHandler":
        mapping = require_mapping(data, path)
        handler_type = optional_str(mapping, "type", path) or "command"
        if handler_type not in ("command", "prompt", "agent"):
            raise ConfigError(
                "hook handler type must be 'command', 'prompt', or 'agent'",
                extend_path(path, "type"),
            )
        command = optional_str(mapping, "command", path)
        prompt = optional_str(mapping, "prompt", path)
        model = optional_str(mapping, "model", path)

        timeout_raw = mapping.get("timeout")
        timeout: Optional[int] = None
        if timeout_raw is not None:
            if not isinstance(timeout_raw, int) or isinstance(timeout_raw, bool):
                raise ConfigError("timeout must be an integer", extend_path(path, "timeout"))
            timeout = timeout_raw

        async_hook = optional_bool(mapping, "async_hook", path, default=False)
        if async_hook is None:
            async_hook = False
        once = optional_bool(mapping, "once", path, default=False)
        if once is None:
            once = False
        status_message = optional_str(mapping, "status_message", path)

        if handler_type == "command" and not command:
            raise ConfigError("command is required for type=command hooks", path)
        if handler_type in ("prompt", "agent") and not prompt:
            raise ConfigError("prompt is required for type=prompt/agent hooks", path)

        return cls(
            type=handler_type,
            command=command,
            prompt=prompt,
            timeout=timeout,
            model=model,
            async_hook=async_hook,
            once=once,
            status_message=status_message,
            path=path,
        )


@dataclass
class HookMatcher(BaseConfig):
    """A matcher + handler list for a specific hook event."""

    matcher: str = ""  # regex pattern (e.g., "Edit|Write")
    hooks: List[HookHandler] = field(default_factory=list)

    FIELD_SPECS = {
        "matcher": ConfigFieldSpec(
            name="matcher",
            display_name="Tool Matcher",
            type_hint="str",
            required=False,
            default="",
            description="Regex pattern to match tool names (e.g., 'Edit|Write|Bash')",
        ),
        "hooks": ConfigFieldSpec(
            name="hooks",
            display_name="Hook Handlers",
            type_hint="list[HookHandler]",
            required=True,
            description="List of hook handlers to execute",
            child=HookHandler,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "HookMatcher":
        mapping = require_mapping(data, path)
        matcher = optional_str(mapping, "matcher", path) or ""

        hooks_raw = mapping.get("hooks")
        if not hooks_raw or not isinstance(hooks_raw, list):
            raise ConfigError("hooks must be a non-empty list", extend_path(path, "hooks"))

        hooks: List[HookHandler] = []
        for idx, item in enumerate(hooks_raw):
            hooks.append(HookHandler.from_dict(item, path=extend_path(path, f"hooks[{idx}]")))

        return cls(matcher=matcher, hooks=hooks, path=path)


# Valid event names for hooks (provider-agnostic)
HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "UserPromptSubmit",
    "Notification",
    "SubagentStart",
    "SubagentStop",
)


@dataclass
class AgentHooksConfig(BaseConfig):
    """Provider-agnostic hook definitions.

    HookSkillManager translates these into the appropriate format for
    each CLI provider (Claude Code, Gemini CLI, Copilot CLI).
    """

    PreToolUse: List[HookMatcher] = field(default_factory=list)
    PostToolUse: List[HookMatcher] = field(default_factory=list)
    PostToolUseFailure: List[HookMatcher] = field(default_factory=list)
    Stop: List[HookMatcher] = field(default_factory=list)
    SessionStart: List[HookMatcher] = field(default_factory=list)
    SessionEnd: List[HookMatcher] = field(default_factory=list)
    PreCompact: List[HookMatcher] = field(default_factory=list)
    UserPromptSubmit: List[HookMatcher] = field(default_factory=list)
    Notification: List[HookMatcher] = field(default_factory=list)
    SubagentStart: List[HookMatcher] = field(default_factory=list)
    SubagentStop: List[HookMatcher] = field(default_factory=list)

    FIELD_SPECS = {
        "PreToolUse": ConfigFieldSpec(
            name="PreToolUse",
            display_name="Pre Tool Use Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run before a tool is used (e.g., scope guards)",
            child=HookMatcher,
        ),
        "PostToolUse": ConfigFieldSpec(
            name="PostToolUse",
            display_name="Post Tool Use Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run after a tool is used (e.g., lint checks)",
            child=HookMatcher,
        ),
        "PostToolUseFailure": ConfigFieldSpec(
            name="PostToolUseFailure",
            display_name="Post Tool Use Failure Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run after a tool fails (e.g., auto-recovery)",
            child=HookMatcher,
            advance=True,
        ),
        "Stop": ConfigFieldSpec(
            name="Stop",
            display_name="Stop Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run when the agent finishes (e.g., verdict checks)",
            child=HookMatcher,
        ),
        "SessionStart": ConfigFieldSpec(
            name="SessionStart",
            display_name="Session Start Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run at session start",
            child=HookMatcher,
            advance=True,
        ),
        "SessionEnd": ConfigFieldSpec(
            name="SessionEnd",
            display_name="Session End Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run when session ends (e.g., cleanup, cost logging)",
            child=HookMatcher,
            advance=True,
        ),
        "PreCompact": ConfigFieldSpec(
            name="PreCompact",
            display_name="Pre Compact Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run before context compaction",
            child=HookMatcher,
            advance=True,
        ),
        "UserPromptSubmit": ConfigFieldSpec(
            name="UserPromptSubmit",
            display_name="User Prompt Submit Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run when user submits a prompt (e.g., input validation)",
            child=HookMatcher,
            advance=True,
        ),
        "Notification": ConfigFieldSpec(
            name="Notification",
            display_name="Notification Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run on agent notifications",
            child=HookMatcher,
            advance=True,
        ),
        "SubagentStart": ConfigFieldSpec(
            name="SubagentStart",
            display_name="Sub-Agent Start Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run when a sub-agent starts",
            child=HookMatcher,
            advance=True,
        ),
        "SubagentStop": ConfigFieldSpec(
            name="SubagentStop",
            display_name="Sub-Agent Stop Hooks",
            type_hint="list[HookMatcher]",
            required=False,
            description="Hooks that run when a sub-agent stops",
            child=HookMatcher,
            advance=True,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "AgentHooksConfig":
        mapping = require_mapping(data, path)
        kwargs: Dict[str, List[HookMatcher]] = {}

        for event_name in HOOK_EVENTS:
            raw = mapping.get(event_name)
            if raw is None:
                continue
            if not isinstance(raw, list):
                raise ConfigError(
                    f"{event_name} must be a list of hook matchers",
                    extend_path(path, event_name),
                )
            matchers: List[HookMatcher] = []
            for idx, item in enumerate(raw):
                matchers.append(
                    HookMatcher.from_dict(item, path=extend_path(path, f"{event_name}[{idx}]"))
                )
            kwargs[event_name] = matchers

        return cls(**kwargs, path=path)

    def has_hooks(self) -> bool:
        """Return True if any event has at least one matcher."""
        return any(
            getattr(self, event_name)
            for event_name in HOOK_EVENTS
        )


# ──────────────────────────────────────────────────────────────────
# Sub-Agent Configuration
# ──────────────────────────────────────────────────────────────────


@dataclass
class SubAgentConfig(BaseConfig):
    """Definition of a sub-agent that a CLI provider exposes as a tool.

    Each CLI provider discovers sub-agent MD files from specific directories:
    - Claude Code: ``.claude/agents/{name}.md``
    - Gemini CLI: ``.gemini/agents/{name}.md``
    - Copilot CLI: ``.github/agents/{name}.md``

    The ``source`` field points to a template MD file under
    ``.chatdev/workflows/`` that HookSkillManager copies to the right location.
    """

    name: str = ""  # "code-researcher" (lowercase, hyphens)
    description: str = ""  # Short description for the agent
    source: str = ""  # Path to template MD file (.chatdev/workflows/agile_dev/agents/code-researcher.md)
    tools: List[str] = field(default_factory=list)  # Tool whitelist (overrides source frontmatter)
    disallowed_tools: List[str] = field(default_factory=list)  # Tool blacklist
    model: Optional[str] = None  # Model override: haiku, sonnet, opus (None = inherit from source)
    max_turns: Optional[int] = None  # Max agentic turns (None = inherit from source)
    mcp_servers: Dict[str, Any] = field(default_factory=dict)  # MCP servers for the sub-agent (Claude Code only)

    FIELD_SPECS = {
        "name": ConfigFieldSpec(
            name="name",
            display_name="Sub-Agent Name",
            type_hint="str",
            required=True,
            description="Unique name for the sub-agent (lowercase, hyphens, e.g. 'code-researcher')",
        ),
        "description": ConfigFieldSpec(
            name="description",
            display_name="Description",
            type_hint="str",
            required=True,
            description="Short description of the sub-agent's purpose",
        ),
        "source": ConfigFieldSpec(
            name="source",
            display_name="Source File",
            type_hint="str",
            required=True,
            description="Path to the template MD file (relative to project root)",
        ),
        "tools": ConfigFieldSpec(
            name="tools",
            display_name="Allowed Tools",
            type_hint="list[str]",
            required=False,
            description="Tool whitelist for the sub-agent (overrides source frontmatter if set)",
            advance=True,
        ),
        "disallowed_tools": ConfigFieldSpec(
            name="disallowed_tools",
            display_name="Disallowed Tools",
            type_hint="list[str]",
            required=False,
            description="Tool blacklist — these tools will be blocked for the sub-agent",
            advance=True,
        ),
        "model": ConfigFieldSpec(
            name="model",
            display_name="Model",
            type_hint="str",
            required=False,
            description="Model for the sub-agent: haiku, sonnet, opus, or inherit from source",
            advance=True,
        ),
        "max_turns": ConfigFieldSpec(
            name="max_turns",
            display_name="Max Turns",
            type_hint="int",
            required=False,
            description="Maximum agentic turns for the sub-agent",
            advance=True,
        ),
        "mcp_servers": ConfigFieldSpec(
            name="mcp_servers",
            display_name="MCP Servers",
            type_hint="dict[str, Any]",
            required=False,
            description="MCP server definitions for the sub-agent (Claude Code frontmatter format). Keys are server names, values are {command, args, env} dicts.",
            advance=True,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "SubAgentConfig":
        mapping = require_mapping(data, path)

        name = optional_str(mapping, "name", path) or ""
        if not name:
            raise ConfigError("sub-agent name is required", extend_path(path, "name"))

        description = optional_str(mapping, "description", path) or ""
        if not description:
            raise ConfigError("sub-agent description is required", extend_path(path, "description"))

        source = optional_str(mapping, "source", path) or ""
        if not source:
            raise ConfigError("sub-agent source file is required", extend_path(path, "source"))

        # Optional tool lists
        tools: List[str] = []
        raw_tools = mapping.get("tools")
        if raw_tools is not None:
            if not isinstance(raw_tools, list):
                raise ConfigError("tools must be a list of strings", extend_path(path, "tools"))
            for idx, t in enumerate(raw_tools):
                if not isinstance(t, str):
                    raise ConfigError("each tool must be a string", extend_path(path, f"tools[{idx}]"))
                tools.append(t.strip())

        disallowed_tools: List[str] = []
        raw_disallowed = mapping.get("disallowed_tools")
        if raw_disallowed is not None:
            if not isinstance(raw_disallowed, list):
                raise ConfigError("disallowed_tools must be a list of strings", extend_path(path, "disallowed_tools"))
            for idx, t in enumerate(raw_disallowed):
                if not isinstance(t, str):
                    raise ConfigError("each tool must be a string", extend_path(path, f"disallowed_tools[{idx}]"))
                disallowed_tools.append(t.strip())

        model = optional_str(mapping, "model", path)
        max_turns: Optional[int] = None
        raw_mt = mapping.get("max_turns")
        if raw_mt is not None:
            if not isinstance(raw_mt, int) or isinstance(raw_mt, bool):
                raise ConfigError("max_turns must be an integer", extend_path(path, "max_turns"))
            if raw_mt < 1:
                raise ConfigError("max_turns must be >= 1", extend_path(path, "max_turns"))
            max_turns = raw_mt

        mcp_servers: Dict[str, Any] = {}
        raw_mcp = mapping.get("mcp_servers")
        if raw_mcp is not None:
            if not isinstance(raw_mcp, Mapping):
                raise ConfigError("mcp_servers must be a mapping", extend_path(path, "mcp_servers"))
            mcp_servers = dict(raw_mcp)

        return cls(
            name=name,
            description=description,
            source=source,
            tools=tools,
            disallowed_tools=disallowed_tools,
            model=model,
            max_turns=max_turns,
            mcp_servers=mcp_servers,
            path=path,
        )
