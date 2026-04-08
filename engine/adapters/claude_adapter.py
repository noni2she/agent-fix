"""
Claude (Anthropic) SDK Adapter

使用 Anthropic Messages API 實作 AgentAdapter 介面。

Claude SDK 特性：
- 無狀態 API（每次呼叫需傳入完整 message history）
- 本 adapter 在 session 內維護 messages list 模擬持久化 session
- agentic loop 由 adapter 自行管理（tool_use → execute → tool_result → 繼續）
- pending_messages 機制：工具上限警告會在下一輪 LLM 呼叫前附加

安裝：pip install anthropic
文件：https://docs.anthropic.com/en/api/messages
"""
import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, List

from .base import AgentAdapter, AgentEvent, AgentSession
from ..tools import TOOL_MAP


@dataclass
class ClaudeNativeSession:
    """Anthropic 的 'session' 以 message history 模擬"""
    model: str
    tools: List[dict]                   # Anthropic tool schema 格式
    messages: List[dict] = field(default_factory=list)


class ClaudeAdapter(AgentAdapter):
    """
    Anthropic Claude adapter。

    環境變數：
        ANTHROPIC_API_KEY — Anthropic API key（必填）

    預設模型：claude-opus-4-5
    工具格式：{"name", "description", "input_schema": JSON Schema}
    """

    DEFAULT_MODEL = "claude-opus-4-5"

    def __init__(self):
        self._client = None

    async def start(self) -> None:
        import anthropic
        self._client = anthropic.Anthropic()

    async def create_session(
        self,
        tool_names: List[str],
        model: str,
    ) -> AgentSession:
        if self._client is None:
            await self.start()

        claude_tools = self._build_claude_tools(tool_names)
        native = ClaudeNativeSession(model=model, tools=claude_tools)
        return AgentSession(adapter=self, native=native)

    async def send(
        self,
        native_session: ClaudeNativeSession,
        message: str,
        session: AgentSession,
    ) -> None:
        """
        執行完整 agentic loop。

        1. 把 message（含 pending warnings）加入 messages
        2. 呼叫 Anthropic API
        3. 處理 tool_use → 執行工具 → tool_result → 繼續
        4. 結束時 emit AgentEvent("idle")
        """
        # 注入 pending 警告訊息（工具上限提醒）
        full_message = message
        if session.pending_messages:
            warnings = "\n".join(session.pending_messages)
            full_message = f"{message}\n\n---\n{warnings}"
            session.pending_messages.clear()

        native_session.messages.append({"role": "user", "content": full_message})

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._agentic_loop(native_session, session)
        )

    # ==========================================
    # Agentic Loop（tool_use ↔ tool_result 循環）
    # ==========================================

    def _agentic_loop(
        self,
        native: ClaudeNativeSession,
        session: AgentSession,
    ) -> None:
        """同步 agentic loop，在 executor 中執行（避免阻塞 event loop）"""
        max_iterations = 50

        for _ in range(max_iterations):
            # 注入 pending 警告（send() 之後才到達的 pending 訊息）
            if session.pending_messages:
                warnings = "\n".join(session.pending_messages)
                session.pending_messages.clear()
                native.messages.append({
                    "role": "user",
                    "content": f"[系統提醒] {warnings}"
                })

            response = self._client.messages.create(
                model=native.model,
                max_tokens=8096,
                tools=native.tools if native.tools else [],
                messages=native.messages,
            )

            # 收集文字輸出
            for block in response.content:
                if block.type == "text" and block.text:
                    session.emit(AgentEvent(type="message", content=block.text))

            native.messages.append({"role": "assistant", "content": response.content})

            # 結束條件
            if response.stop_reason == "end_turn":
                break

            # 處理工具呼叫
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        session.emit(AgentEvent(type="tool_start", tool_name=block.name))
                        result = self._execute_tool(block.name, dict(block.input))
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                native.messages.append({"role": "user", "content": tool_results})

        session.emit(AgentEvent(type="idle"))

    def _execute_tool(self, tool_name: str, args: dict) -> str:
        if tool_name not in TOOL_MAP:
            return f"❌ Unknown tool: {tool_name}"
        try:
            return str(TOOL_MAP[tool_name](**args))
        except Exception as e:
            return f"❌ Tool error ({tool_name}): {e}"

    # ==========================================
    # 工具建立（Anthropic input_schema 格式）
    # ==========================================

    def _build_claude_tools(self, tool_names: List[str]) -> List[dict]:
        tools = []
        for name in tool_names:
            if name not in TOOL_MAP:
                print(f"  ⚠️  工具不存在於 TOOL_MAP，略過: {name}")
                continue
            func = TOOL_MAP[name]
            tools.append({
                "name": name,
                "description": (func.__doc__ or "").strip().split('\n')[0] or name,
                "input_schema": self._extract_input_schema(func),
            })
        return tools

    @staticmethod
    def _extract_input_schema(func) -> dict:
        try:
            sig = inspect.signature(func)
            properties, required = {}, []
            for name, param in sig.parameters.items():
                info: dict = {"type": "string"}
                ann = param.annotation
                if ann != inspect.Parameter.empty:
                    if ann == int:
                        info["type"] = "integer"
                    elif ann == bool:
                        info["type"] = "boolean"
                    elif ann == float:
                        info["type"] = "number"
                    elif getattr(ann, "__origin__", None) is list:
                        info["type"] = "array"
                        info["items"] = {"type": "string"}
                if param.default != inspect.Parameter.empty:
                    info["description"] = f"Default: {param.default}"
                else:
                    required.append(name)
                properties[name] = info
            return {"type": "object", "properties": properties, "required": required}
        except Exception:
            return {"type": "object", "properties": {}, "required": []}
