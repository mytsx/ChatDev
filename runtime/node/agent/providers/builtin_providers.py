"""Register built-in agent providers."""

from runtime.node.agent.providers.base import ProviderRegistry

from runtime.node.agent.providers.openai_provider import OpenAIProvider

ProviderRegistry.register(
    "openai",
    OpenAIProvider,
    label="OpenAI",
    summary="OpenAI models via the official OpenAI SDK (responses API)",
)

try:
    from runtime.node.agent.providers.claude_code_provider import ClaudeCodeProvider
except (ImportError, FileNotFoundError):
    ClaudeCodeProvider = None

if ClaudeCodeProvider is not None:
    ProviderRegistry.register(
        "claude-code",
        ClaudeCodeProvider,
        label="Claude Code",
        summary="Claude models via Claude Code CLI (uses Max subscription, no API key needed)",
    )
else:
    print("Claude Code provider not registered: claude CLI not found in PATH.")

try:
    from runtime.node.agent.providers.gemini_provider import GeminiProvider
except ImportError:
    GeminiProvider = None

if GeminiProvider is not None:
    ProviderRegistry.register(
        "gemini",
        GeminiProvider,
        label="Google Gemini",
        summary="Google Gemini models via google-genai",
    )
else:
    print("Gemini provider not registered: google-genai library not found.")

# --- Gemini CLI (agentic CLI, uses Google account) ---
try:
    from runtime.node.agent.providers.gemini_cli_provider import GeminiCliProvider
except (ImportError, FileNotFoundError):
    GeminiCliProvider = None

if GeminiCliProvider is not None:
    ProviderRegistry.register(
        "gemini-cli",
        GeminiCliProvider,
        label="Gemini CLI",
        summary="Google Gemini via Gemini CLI (uses Google account, no API key needed)",
    )

# --- Copilot CLI (agentic CLI, uses GitHub Copilot subscription) ---
try:
    from runtime.node.agent.providers.copilot_cli_provider import CopilotCliProvider
except (ImportError, FileNotFoundError):
    CopilotCliProvider = None

if CopilotCliProvider is not None:
    ProviderRegistry.register(
        "copilot-cli",
        CopilotCliProvider,
        label="GitHub Copilot CLI",
        summary="GitHub Copilot via Copilot CLI (uses Copilot subscription, no API key needed)",
    )
