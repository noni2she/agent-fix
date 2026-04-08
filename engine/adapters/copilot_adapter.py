"""
GitHub Copilot SDK Adapter

將現有的 Copilot SDK 邏輯封裝為 AgentAdapter 介面。

Copilot SDK 特性：
- 事件驅動（SDK 管理 agentic loop）
- session.on(handler) 訂閱原始事件
- session.send({"prompt": ...}) 發送訊息
- 工具 handler 格式: async def handler(invocation) -> {"textResultForLlm": ..., "resultType": ...}
"""
import inspect
import asyncio
from typing import Any, Callable, List

from .base import AgentAdapter, AgentEvent, AgentSession
from ..tools import TOOL_MAP


class CopilotAdapter(AgentAdapter):
    """
    GitHub Copilot SDK adapter。

    安裝：pip install github-copilot-sdk
    文件：https://github.com/github/copilot-sdk
    """

    def __init__(self):
        self._client = None

    async def start(self) -> None:
        from copilot import CopilotClient
        self._client = CopilotClient()
        await self._client.start()

    async def create_session(
        self,
        tool_names: List[str],
        model: str,
    ) -> AgentSession:
        if self._client is None:
            await self.start()

        copilot_tools = self._build_copilot_tools(tool_names)

        config: dict[str, Any] = {"model": model}
        if copilot_tools:
            config["tools"] = copilot_tools

        native = await self._client.create_session(config)  # type: ignore
        session = AgentSession(adapter=self, native=native)

        # 訂閱 Copilot 原始事件，轉換為標準化 AgentEvent
        native.on(lambda event: self._normalize_event(event, session))

        return session

    async def send(
        self,
        native_session: Any,
        message: str,
        session: AgentSession,
    ) -> None:
        """
        發送訊息給 Copilot session。

        Copilot SDK 的 agentic loop 由 SDK 自行管理，
        send() 只需把訊息傳進去，事件會透過 native.on() 的
        handler 自動觸發。
        """
        await native_session.send({"prompt": message})

    # ==========================================
    # 工具建立
    # ==========================================

    def _build_copilot_tools(self, tool_names: List[str]) -> list:
        from copilot import Tool

        tools = []
        for name in tool_names:
            if name not in TOOL_MAP:
                print(f"  ⚠️  工具不存在於 TOOL_MAP，略過: {name}")
                continue

            func = TOOL_MAP[name]
            tools.append(Tool(
                name=name,
                description=(func.__doc__ or "").strip().split('\n')[0] or name,
                handler=self._make_handler(name),
                parameters=self._extract_parameters(func),
            ))

        return tools

    def _make_handler(self, tool_name: str):
        func = TOOL_MAP[tool_name]

        async def handler(invocation):
            print(f"  🔧 執行工具: {tool_name}")
            try:
                args = invocation.get("arguments", {}) if isinstance(invocation, dict) else {}
                result = func(**args)
                return {"textResultForLlm": str(result), "resultType": "success"}
            except Exception as e:
                error_msg = f"{tool_name} 執行錯誤: {str(e)}"
                print(f"  ❌ {error_msg}")
                return {"textResultForLlm": error_msg, "resultType": "error"}

        return handler

    # ==========================================
    # 事件標準化
    # ==========================================

    def _normalize_event(self, event: Any, session: AgentSession) -> None:
        """將 Copilot SDK 原始事件轉換為 AgentEvent"""
        try:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

            if event_type == "assistant.message":
                content = getattr(event.data, "content", None) if hasattr(event, "data") else None
                if content:
                    session.emit(AgentEvent(type="message", content=content))

            elif event_type == "tool.execution_start":
                tool_name = self._extract_tool_name(event)
                session.emit(AgentEvent(type="tool_start", tool_name=tool_name))

            elif event_type == "session.idle":
                session.emit(AgentEvent(type="idle"))

        except Exception:
            pass

    def _extract_tool_name(self, event: Any) -> str:
        try:
            if hasattr(event, "data"):
                d = event.data
                if hasattr(d, "tool_name") and d.tool_name:
                    return d.tool_name
                if hasattr(d, "tool_requests") and d.tool_requests:
                    req = d.tool_requests[0]
                    return getattr(req, "name", None) or (req.get("name") if isinstance(req, dict) else None) or "Unknown"
                if hasattr(d, "name") and d.name:
                    return d.name
        except Exception:
            pass
        return "Unknown"

    @staticmethod
    def _extract_parameters(func) -> dict:
        try:
            sig = inspect.signature(func)
            properties, required = {}, []
            for name, param in sig.parameters.items():
                info: dict[str, Any] = {"type": "string", "description": f"Parameter: {name}"}
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
                if param.default == inspect.Parameter.empty:
                    required.append(name)
                else:
                    info["description"] = f"Default: {param.default}"
                properties[name] = info
            return {"type": "object", "properties": properties, "required": required}
        except Exception:
            return {"type": "object", "properties": {}, "required": []}
