"""
OpenAI Agents SDK Adapter

使用 OpenAI Agents SDK 實作 AgentAdapter 介面。

OpenAI Agents SDK 特性：
- Agent 物件定義指令與工具，Runner 執行
- Runner.run() 處理完整 agentic loop（tool call → result → 繼續）
- 透過 result.to_input_list() 維護多輪對話（shared session）
- 工具以 @function_tool 或 FunctionTool 定義

安裝：pip install openai-agents
文件：https://openai.github.io/openai-agents-python/
"""
import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, List

from .base import AgentAdapter, AgentEvent, AgentSession
from ..tools import TOOL_MAP


@dataclass
class OpenAINativeSession:
    """
    OpenAI Agents SDK 的 'session'。

    OpenAI Agents SDK 以 Agent + input_list 維護對話狀態：
    - agent: Agent 物件（含指令與工具定義）
    - input_list: 累積的對話 input list（每輪 result.to_input_list() 附加）
    - pending_system_msg: 待注入的系統提醒（工具上限警告）
    """
    agent: Any                              # openai_agents.Agent
    input_list: List[Any] = field(default_factory=list)


class OpenAIAdapter(AgentAdapter):
    """
    OpenAI Agents SDK adapter。

    環境變數：
        OPENAI_API_KEY — OpenAI API key（必填）

    預設模型：gpt-4o
    工具格式：FunctionTool（由 @function_tool 或手動建立）
    """

    DEFAULT_MODEL = "gpt-4o"

    def __init__(self):
        self._initialized = False

    async def start(self) -> None:
        self._initialized = True

    async def create_session(
        self,
        tool_names: List[str],
        model: str,
        mcp_manager: Any = None,
    ) -> AgentSession:
        from agents import Agent

        openai_tools = self._build_openai_tools(tool_names)
        if mcp_manager:
            openai_tools.extend(self._build_openai_mcp_tools(mcp_manager))

        agent = Agent(
            name="bugfix-agent",
            instructions=(
                "You are a skilled software engineer specializing in bug fixing. "
                "Follow the instructions provided in each message precisely."
            ),
            tools=openai_tools,
            model=model,
        )

        native = OpenAINativeSession(agent=agent)
        return AgentSession(adapter=self, native=native)

    async def send(
        self,
        native_session: OpenAINativeSession,
        message: str,
        session: AgentSession,
        images: List[dict] | None = None,
    ) -> None:
        """
        執行 OpenAI Agents Runner。

        1. 注入 pending 警告訊息
        2. 用 Runner.run() 執行完整 agentic loop（含工具呼叫）
        3. 透過 result.to_input_list() 維護多輪對話
        4. 解析 result，emit 標準化事件
        """
        from agents import Runner, ItemHelpers

        # 注入 pending 警告訊息
        full_message = message
        if session.pending_messages:
            warnings = "\n".join(session.pending_messages)
            full_message = f"{message}\n\n---\n{warnings}"
            session.pending_messages.clear()

        # 建立本輪 input：把新訊息附加到歷史 input_list
        if images:
            content: Any = [{"type": "input_text", "text": full_message}]
            for img in images:
                content.append({
                    "type": "input_image",
                    "image_url": f"data:{img['mime_type']};base64,{img['data']}",
                })
            user_msg: Any = {"role": "user", "content": content}
        else:
            user_msg = {"role": "user", "content": full_message}

        current_input = native_session.input_list + [user_msg]

        result = await Runner.run(native_session.agent, input=current_input)

        # 更新對話歷史，供下一輪使用（shared session 的關鍵）
        native_session.input_list = result.to_input_list()

        # 解析輸出，emit 標準化事件
        final_text = ItemHelpers.text_message_outputs(result.new_items)
        if final_text:
            session.emit(AgentEvent(type="message", content=final_text))

        # 記錄工具呼叫（OpenAI Agents SDK 已由 Runner 處理，這裡只 emit 統計用事件）
        for item in result.new_items:
            item_type = getattr(item, "type", None) or type(item).__name__
            if "tool" in str(item_type).lower() and "call" in str(item_type).lower():
                tool_name = getattr(item, "name", None) or getattr(getattr(item, "raw_item", None), "name", "Unknown")
                session.emit(AgentEvent(type="tool_start", tool_name=str(tool_name)))

        session.emit(AgentEvent(type="idle"))

    # ==========================================
    # 工具建立（FunctionTool 格式）
    # ==========================================

    def _build_openai_tools(self, tool_names: List[str]) -> list:
        from agents import FunctionTool

        tools = []
        for name in tool_names:
            if name not in TOOL_MAP:
                print(f"  ⚠️  工具不存在於 TOOL_MAP，略過: {name}")
                continue
            func = TOOL_MAP[name]
            schema = self._extract_input_schema(func)
            tools.append(FunctionTool(
                name=name,
                description=(func.__doc__ or "").strip().split('\n')[0] or name,
                params_json_schema=schema,
                on_invoke_tool=self._make_invoke_handler(name),
            ))
        return tools

    def _build_openai_mcp_tools(self, mcp_manager: Any) -> list:
        from agents import FunctionTool

        tools = []
        for name in mcp_manager.get_tool_names():
            schema = mcp_manager.get_tool_input_schema(name)
            tools.append(FunctionTool(
                name=name,
                description=mcp_manager.get_tool_description(name),
                params_json_schema=schema or {"type": "object", "properties": {}},
                on_invoke_tool=self._make_mcp_invoke_handler(name, mcp_manager),
            ))
        return tools

    def _make_mcp_invoke_handler(self, tool_name: str, mcp_manager: Any):
        async def invoke(ctx, input_json: str) -> str:
            import json
            args = json.loads(input_json) if isinstance(input_json, str) else input_json
            return await mcp_manager.call_tool(tool_name, args)
        return invoke

    def _make_invoke_handler(self, tool_name: str):
        func = TOOL_MAP[tool_name]

        async def invoke(ctx, input_json: str) -> str:
            import json
            print(f"  🔧 執行工具: {tool_name}")
            try:
                args = json.loads(input_json) if isinstance(input_json, str) else input_json
                return str(func(**args))
            except Exception as e:
                return f"❌ Tool error ({tool_name}): {e}"

        return invoke

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
