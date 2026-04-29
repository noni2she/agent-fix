"""
GitHub Copilot SDK Adapter (v0.2.x)

Copilot SDK 特性：
- 事件驅動（SDK 管理 agentic loop）
- session.on(handler) 訂閱原始事件
- session.send(prompt) 發送訊息（v0.2+ 直接傳字串）
- 工具 handler 格式: async def handler(invocation: ToolInvocation) -> ToolResult
"""
import inspect
import asyncio
from typing import Any, List

from .base import AgentAdapter, AgentEvent, AgentSession
from ..tools import TOOL_MAP


class CopilotAdapter(AgentAdapter):
    """
    GitHub Copilot SDK adapter（相容 v0.2.x）。

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
        mcp_manager: Any = None,
    ) -> AgentSession:
        from copilot.session import PermissionHandler

        if self._client is None:
            await self.start()

        copilot_tools = self._build_copilot_tools(tool_names)
        if mcp_manager:
            copilot_tools.extend(self._build_copilot_mcp_tools(mcp_manager))

        native = await self._client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=model,
            tools=copilot_tools if copilot_tools else None,
        )
        session = AgentSession(adapter=self, native=native)

        # 訂閱 Copilot 原始事件，轉換為標準化 AgentEvent
        native.on(lambda event: self._normalize_event(event, session))

        return session

    async def send(
        self,
        native_session: Any,
        message: str,
        session: AgentSession,
        images: list[dict] | None = None,
    ) -> None:
        """
        發送訊息給 Copilot session。

        v0.2+ send() 直接接受字串 prompt，不再需要包成 dict。
        images: [{"data": base64, "mime_type": "image/png", "name": "x.png"}]
        """
        attachments = None
        if images:
            attachments = [
                {
                    "type": "blob",
                    "data": img["data"],
                    "mimeType": img["mime_type"],
                    "displayName": img.get("name", "attachment"),
                }
                for img in images
            ]
        await native_session.send(message, attachments=attachments)

    # ==========================================
    # 工具建立
    # ==========================================

    def _build_copilot_mcp_tools(self, mcp_manager: Any) -> list:
        from copilot.tools import Tool, ToolResult

        tools = []
        for name in mcp_manager.get_tool_names():
            tools.append(Tool(
                name=name,
                description=mcp_manager.get_tool_description(name),
                handler=self._make_mcp_handler(name, mcp_manager),
                parameters=mcp_manager.get_tool_input_schema(name),
            ))
        return tools

    def _make_mcp_handler(self, tool_name: str, mcp_manager: Any):
        from copilot.tools import ToolResult

        async def handler(invocation):
            args = invocation.arguments or {} if hasattr(invocation, "arguments") else {}
            result = await mcp_manager.call_tool(tool_name, args)
            return ToolResult(text_result_for_llm=str(result), result_type="success")
        return handler

    def _build_copilot_tools(self, tool_names: List[str]) -> list:
        from copilot.tools import Tool

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
        from copilot.tools import ToolResult

        func = TOOL_MAP[tool_name]

        async def handler(invocation):
            print(f"  🔧 執行工具: {tool_name}")
            try:
                args = invocation.arguments or {} if hasattr(invocation, "arguments") else {}
                result = func(**args)
                return ToolResult(text_result_for_llm=str(result), result_type="success")
            except Exception as e:
                error_msg = f"{tool_name} 執行錯誤: {str(e)}"
                print(f"  ❌ {error_msg}")
                return ToolResult(text_result_for_llm=error_msg, result_type="failure")

        return handler

    # ==========================================
    # 事件標準化
    # ==========================================

    def _normalize_event(self, event: Any, session: AgentSession) -> None:
        """將 Copilot SDK 原始事件轉換為 AgentEvent"""
        try:
            from copilot.generated.session_events import SessionEventType

            event_type = event.type
            data = getattr(event, "data", None)

            if event_type == SessionEventType.ASSISTANT_MESSAGE:
                content = getattr(data, "content", None) if data is not None else None
                if content and isinstance(content, str):
                    session.emit(AgentEvent(type="message", content=content))

                # Best-effort token usage（Copilot SDK 不保證一定有）
                usage = getattr(data, "usage_info", None) or getattr(data, "usage", None)
                if usage:
                    input_tokens = (
                        getattr(usage, "prompt_tokens", None)
                        or getattr(usage, "input_tokens", None)
                        or 0
                    )
                    output_tokens = (
                        getattr(usage, "completion_tokens", None)
                        or getattr(usage, "output_tokens", None)
                        or 0
                    )
                    if input_tokens or output_tokens:
                        session.emit(AgentEvent(type="usage", usage={
                            "input": input_tokens,
                            "output": output_tokens,
                        }))

            elif event_type == SessionEventType.EXTERNAL_TOOL_REQUESTED:
                tool_name = getattr(data, "tool_name", None) or "Unknown"
                session.emit(AgentEvent(type="tool_start", tool_name=tool_name))

            elif event_type == SessionEventType.SESSION_IDLE:
                session.emit(AgentEvent(type="idle"))

        except Exception:
            pass

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
