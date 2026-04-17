"""
MCPClientManager — 統一 MCP server 連線管理

提供給三個 adapter 使用的共用層：
- 連接一或多個 stdio MCP server
- 收集 tool schemas
- 提供 async 和 sync (threadsafe) 的 call_tool 介面

lifecycle：
    manager = await MCPClientManager.create(config.mcp_servers)
    try:
        session = await adapter.create_session(..., mcp_manager=manager)
        ...
    finally:
        await manager.stop()
"""
import asyncio
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import MCPServerConfig


class MCPClientManager:

    def __init__(self):
        self._tool_info: Dict[str, dict] = {}  # tool_name → {description, schema, session}
        self._exit_stacks: List[Any] = []
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    @classmethod
    async def create(cls, server_configs: Dict[str, "MCPServerConfig"]) -> "MCPClientManager":
        """建立並連接所有啟用的 MCP server，回傳就緒的 manager。"""
        manager = cls()
        manager._main_loop = asyncio.get_event_loop()
        await manager._connect_all(server_configs)
        return manager

    async def _connect_all(self, server_configs: Dict[str, "MCPServerConfig"]) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for name, cfg in server_configs.items():
            if not cfg.enabled:
                continue
            try:
                server_params = StdioServerParameters(
                    command=cfg.command,
                    args=cfg.args,
                )
                cm = stdio_client(server_params)
                read, write = await cm.__aenter__()
                session_cm = ClientSession(read, write)
                await session_cm.__aenter__()
                await session_cm.initialize()

                tools_result = await session_cm.list_tools()
                for tool in tools_result.tools:
                    self._tool_info[tool.name] = {
                        "description": tool.description or tool.name,
                        "schema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                        "session": session_cm,
                    }
                self._exit_stacks.append((session_cm, cm))
                print(f"  🔌 MCP server '{name}': {len(tools_result.tools)} tools connected")
            except Exception as e:
                print(f"  ⚠️  MCP server '{name}' failed to connect: {e}")

    async def stop(self) -> None:
        """關閉所有 MCP server 連線。"""
        for session_cm, cm in reversed(self._exit_stacks):
            try:
                await session_cm.__aexit__(None, None, None)
                await cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._exit_stacks.clear()
        self._tool_info.clear()

    # ------------------------------------------------------------------
    # Tool 查詢
    # ------------------------------------------------------------------

    def is_mcp_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_info

    def get_tool_names(self) -> List[str]:
        return list(self._tool_info.keys())

    def get_tool_schema_for_claude(self, tool_name: str) -> Optional[dict]:
        """Anthropic format: {name, description, input_schema}"""
        info = self._tool_info.get(tool_name)
        if not info:
            return None
        return {
            "name": tool_name,
            "description": info["description"],
            "input_schema": info["schema"] or {"type": "object", "properties": {}},
        }

    def get_tool_schema_for_openai(self, tool_name: str) -> Optional[dict]:
        """OpenAI / generic JSON Schema format: {name, description, parameters}"""
        info = self._tool_info.get(tool_name)
        if not info:
            return None
        return {
            "name": tool_name,
            "description": info["description"],
            "parameters": info["schema"] or {"type": "object", "properties": {}},
        }

    def get_tool_description(self, tool_name: str) -> str:
        info = self._tool_info.get(tool_name)
        return info["description"] if info else tool_name

    def get_tool_input_schema(self, tool_name: str) -> dict:
        info = self._tool_info.get(tool_name)
        return info["schema"] if info else {"type": "object", "properties": {}}

    # ------------------------------------------------------------------
    # Tool 呼叫（async — Copilot / OpenAI adapter 用）
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, args: dict) -> str:
        info = self._tool_info.get(tool_name)
        if not info:
            return f"❌ MCP tool not found: {tool_name}"
        try:
            result = await info["session"].call_tool(tool_name, args)
            parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    parts.append(content.text)
                elif hasattr(content, "data"):
                    parts.append(f"[binary data: {len(content.data)} bytes]")
            return "\n".join(parts) if parts else "(empty response)"
        except Exception as e:
            return f"❌ MCP tool error ({tool_name}): {e}"

    # ------------------------------------------------------------------
    # Tool 呼叫（sync threadsafe — Claude adapter 的 sync thread 用）
    # ------------------------------------------------------------------

    def call_tool_sync(self, tool_name: str, args: dict, timeout: int = 30) -> str:
        """從 sync thread（executor）安全地呼叫 async MCP tool。"""
        if self._main_loop is None or self._main_loop.is_closed():
            return f"❌ MCPClientManager not started or loop closed"
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.call_tool(tool_name, args),
                self._main_loop,
            )
            return future.result(timeout=timeout)
        except TimeoutError:
            return f"❌ MCP tool timeout ({tool_name})"
        except Exception as e:
            return f"❌ MCP tool error ({tool_name}): {e}"
