"""
SDK Adapter 基礎介面

定義所有 SDK adapter 共用的抽象層：
- AgentEvent: 標準化事件格式（跨 SDK 統一）
- AgentSession: Session 封裝（提供統一的 .on() 與 .send() 介面）
- AgentAdapter: 所有 adapter 必須實作的 ABC
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


# ==========================================
# 標準化事件格式
# ==========================================

@dataclass
class AgentEvent:
    """
    跨 SDK 統一的事件格式。

    各 SDK 的原始事件會被 adapter 轉換為此格式，
    讓 agent_runner.py 不需要感知底層 SDK。

    type:
        "message"    — agent 輸出文字片段（content 有值）
        "tool_start" — agent 開始呼叫工具（tool_name 有值）
        "idle"       — agent 本輪執行結束，等待下一條訊息
    """
    type: str
    content: Optional[str] = None
    tool_name: Optional[str] = None


# ==========================================
# Session 封裝（統一介面）
# ==========================================

class AgentSession:
    """
    Adapter-agnostic session handle。

    所有 SDK 的 session 都被包裝成此物件，
    讓 agent_runner.py 只需操作統一介面：

        session.on(handler)     # 訂閱事件
        await session.send(msg) # 發送訊息

    pending_messages: 用於「在 agentic loop 執行中途注入訊息」
    （例如工具上限警告）。Claude/OpenAI adapter 會在下一輪 LLM
    呼叫前，把 pending 訊息附加到 user message 中。
    """

    def __init__(self, adapter: "AgentAdapter", native: Any):
        self._adapter = adapter
        self._native = native
        self._handlers: List[Callable[[AgentEvent], None]] = []
        self.pending_messages: List[str] = []

    def on(self, handler: Callable[[AgentEvent], None]) -> None:
        """訂閱標準化事件"""
        self._handlers.append(handler)

    async def send(self, message: str) -> None:
        """發送訊息給 agent（觸發 agentic loop）"""
        await self._adapter.send(self._native, message, self)

    def emit(self, event: AgentEvent) -> None:
        """觸發所有已訂閱的 handler"""
        for handler in self._handlers:
            try:
                handler(event)
            except Exception:
                pass


# ==========================================
# Adapter 抽象基底類別
# ==========================================

class AgentAdapter(ABC):
    """
    所有 SDK adapter 必須實作的抽象介面。

    實作子類別：
        CopilotAdapter  — engine/adapters/copilot_adapter.py
        ClaudeAdapter   — engine/adapters/claude_adapter.py
        OpenAIAdapter   — engine/adapters/openai_adapter.py
    """

    @abstractmethod
    async def start(self) -> None:
        """初始化 SDK client（僅需呼叫一次）"""

    @abstractmethod
    async def create_session(
        self,
        tool_names: List[str],
        model: str,
        mcp_manager: Optional[Any] = None,
    ) -> AgentSession:
        """
        建立新的 agent session。

        Args:
            tool_names:  要啟用的自訂工具名稱列表（來自 TOOL_MAP）
            model:       要使用的模型 ID（各 SDK 格式不同）
            mcp_manager: MCPClientManager 實例（可選）。
                         傳入時，MCP tools 會注入給 LLM；None 表示不使用 MCP。

        Returns:
            AgentSession 封裝物件
        """

    @abstractmethod
    async def send(
        self,
        native_session: Any,
        message: str,
        session: AgentSession,
    ) -> None:
        """
        發送訊息並執行 agentic loop。

        loop 執行期間透過 session.emit() 觸發：
            AgentEvent("message", content=...)   → agent 輸出片段
            AgentEvent("tool_start", tool_name=...) → 工具呼叫
            AgentEvent("idle")                   → 本輪結束

        Args:
            native_session: create_session() 回傳的原始 SDK session
            message:        使用者訊息字串
            session:        AgentSession 封裝（用於 emit + pending_messages）
        """
