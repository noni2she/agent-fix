"""
SDK Adapter 工廠

透過環境變數 SDK_ADAPTER 選擇底層 SDK：

    export SDK_ADAPTER=copilot   # GitHub Copilot SDK（預設）
    export SDK_ADAPTER=claude    # Anthropic Claude SDK
    export SDK_ADAPTER=openai    # OpenAI Agents SDK

各 SDK 所需安裝：
    copilot: pip install github-copilot-sdk
    claude:  pip install anthropic
    openai:  pip install openai-agents

各 SDK 所需環境變數：
    copilot: 無（使用 gh auth，需已登入 GitHub Copilot）
    claude:  ANTHROPIC_API_KEY
    openai:  OPENAI_API_KEY

預設模型（可在 .env 中覆寫 DEFAULT_MODEL）：
    copilot: claude-sonnet-4.5
    claude:  claude-opus-4-5
    openai:  gpt-4o
"""
import os
from .base import AgentAdapter, AgentSession, AgentEvent

SUPPORTED_ADAPTERS = ("copilot", "claude", "openai")

# 各 adapter 的預設模型
DEFAULT_MODELS = {
    "copilot": "claude-sonnet-4.5",
    "claude": "claude-opus-4-5",
    "openai": "gpt-4o",
}


def get_adapter(sdk: str | None = None) -> AgentAdapter:
    """
    根據 sdk 名稱（或 SDK_ADAPTER 環境變數）回傳對應的 adapter 實例。

    Args:
        sdk: "copilot" | "claude" | "openai"（None 時讀 SDK_ADAPTER env）

    Returns:
        AgentAdapter 實例（尚未 start()）

    Raises:
        ValueError: 不支援的 sdk 名稱
    """
    sdk = sdk or os.getenv("SDK_ADAPTER", "copilot")

    if sdk == "copilot":
        from .copilot_adapter import CopilotAdapter
        return CopilotAdapter()
    elif sdk == "claude":
        from .claude_adapter import ClaudeAdapter
        return ClaudeAdapter()
    elif sdk == "openai":
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter()
    else:
        raise ValueError(
            f"Unknown SDK adapter: '{sdk}'. "
            f"Supported: {SUPPORTED_ADAPTERS}. "
            f"Set SDK_ADAPTER env var or pass sdk= to get_adapter()."
        )


def get_default_model(sdk: str | None = None) -> str:
    """回傳指定 adapter 的預設模型 ID"""
    sdk = sdk or os.getenv("SDK_ADAPTER", "copilot")
    return os.getenv("DEFAULT_MODEL", DEFAULT_MODELS.get(sdk, ""))


__all__ = [
    "AgentAdapter",
    "AgentSession",
    "AgentEvent",
    "get_adapter",
    "get_default_model",
    "SUPPORTED_ADAPTERS",
]
