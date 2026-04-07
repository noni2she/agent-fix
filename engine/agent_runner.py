"""
Agent 執行器模組 v3.0 (Skill-Based)
1 Agent + Skill Loader，取代 3-Agent StateGraph

與 ai-bugfix-workflow 的差異：
  - 工具路徑、skills 路徑由 ProjectConfig 配置，無硬編碼
  - 保留 init_agent_runner() 供 main.py 初始化使用
"""
import asyncio
import time
from typing import Dict, Any, List
from pathlib import Path

from .tools import TOOL_MAP
from .project_spec import ProjectSpec
from .config import ProjectConfig


# ==========================================
# 全域配置（由 init_agent_runner 設定）
# ==========================================

_project_config: ProjectConfig = None
_project_spec: ProjectSpec = None


def init_agent_runner(config: ProjectConfig, spec: ProjectSpec):
    """
    初始化 Agent Runner（必須在執行 Agent 前呼叫）

    Args:
        config: 專案配置
        spec: 專案規格
    """
    global _project_config, _project_spec
    _project_config = config
    _project_spec = spec
    print(f"  🤖 Agent runner initialized for {config.project_name}")


# ==========================================
# Tool 配置（按 phase 分組）
# ==========================================

# analyze + implement 共用 session 所需工具
ANALYZE_IMPLEMENT_TOOLS = [
    # 讀取 / 搜尋
    "list_files",
    "grep_search",
    "read_file",
    # 寫入（用於寫 report 和修改檔案）
    "write_file",
    # 技術債
    "record_tech_debt",
    # Shell（用於 tsc / eslint / agent-browser 等）
    "run_command",
    # Git workflow
    "git_status",
    "git_current_branch",
    "git_create_branch",
    "git_diff",
    "git_commit",
]

# test session 工具（獨立 session）
TEST_TOOLS = [
    "list_files",
    "read_file",
    "grep_search",
    "write_file",
    "run_typescript_check",
    "run_eslint",
    # Shell（用於 agent-browser CLI 行為驗證）
    "run_command",
]


# ==========================================
# SDK 錯誤靜默
# ==========================================

def setup_sdk_error_silencing(loop) -> callable:
    """
    設置 asyncio exception handler 以靜默 Copilot SDK 內部錯誤。
    回傳一個 restore 函式，呼叫後還原原始 handler。
    """
    original_handler = loop.get_exception_handler()

    def silent_sdk_errors(loop, context_dict):
        exception = context_dict.get('exception')
        if exception:
            error_msg = str(exception)
            sdk_patterns = [
                'session.usage_info',
                'is not a valid SessionEventType',
                'assert False',
                'from_union',
                'AssertionError',
            ]
            if any(p in error_msg or p in type(exception).__name__ for p in sdk_patterns):
                return
        if original_handler:
            original_handler(loop, context_dict)
        else:
            loop.default_exception_handler(context_dict)

    loop.set_exception_handler(silent_sdk_errors)

    def restore():
        loop.set_exception_handler(original_handler)

    return restore


# ==========================================
# Session 管理
# ==========================================

async def create_copilot_session(
    tool_names: List[str],
    skill_dirs: List[str] = None,
) -> tuple:
    """
    建立 Copilot session。

    Args:
        tool_names: 要啟用的工具名稱列表
        skill_dirs: SDK 知識庫技能路徑列表（可選）

    Returns:
        (copilot, session) 元組
    """
    from copilot import CopilotClient

    copilot = CopilotClient()
    await copilot.start()

    copilot_tools = prepare_tools(tool_names)

    session_config: Dict[str, Any] = {
        "model": "claude-sonnet-4.5",
    }
    if copilot_tools:
        session_config["tools"] = copilot_tools
    if skill_dirs:
        session_config["skill_directories"] = skill_dirs

    session = await copilot.create_session(session_config)  # type: ignore
    return copilot, session


async def run_in_session(
    session,
    phase_name: str,
    user_message: str,
    max_tool_calls: int,
) -> str:
    """
    在指定 session 執行一個 skill phase。

    Args:
        session: 已建立的 Copilot session（可跨 phase 共用）
        phase_name: Phase 名稱（用於 log）
        user_message: 完整使用者訊息（skill body + context）
        max_tool_calls: 最大工具呼叫次數

    Returns:
        Agent 的最終回應文字
    """
    print(f"\n{'='*60}")
    print(f"🤖 [{phase_name.upper()}] 執行中...")
    print(f"{'='*60}")
    print(f"  📏 訊息長度: {len(user_message)} 字元")

    return await execute_agent_session(
        session=session,
        context=user_message,
        agent_name=phase_name,
        max_tool_calls=max_tool_calls,
    )


# ==========================================
# 工具準備
# ==========================================

def prepare_tools(tool_names: List[str]) -> List:
    """準備 Copilot 工具列表（從 TOOL_MAP 查詢）"""
    from copilot import Tool

    copilot_tools = []
    for tool_name in tool_names:
        if tool_name not in TOOL_MAP:
            print(f"  ⚠️  工具不存在於 TOOL_MAP，略過: {tool_name}")
            continue

        tool_func = TOOL_MAP[tool_name]
        description = (tool_func.__doc__ or "").strip().split('\n')[0] or f"Tool: {tool_name}"
        parameters = extract_tool_parameters(tool_func)
        handler = create_tool_handler(tool_name)

        copilot_tools.append(Tool(
            name=tool_name,
            description=description,
            handler=handler,  # type: ignore
            parameters=parameters,
        ))

    return copilot_tools


def extract_tool_parameters(tool_func) -> Dict[str, Any]:
    """從函式簽名提取參數 schema"""
    import inspect

    try:
        sig = inspect.signature(tool_func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            param_info: Dict[str, Any] = {"type": "string"}
            ann = param.annotation
            if ann != inspect.Parameter.empty:
                if ann == int:
                    param_info["type"] = "integer"
                elif ann == bool:
                    param_info["type"] = "boolean"
                elif ann == float:
                    param_info["type"] = "number"
                elif hasattr(ann, '__origin__') and ann.__origin__ == list:
                    param_info["type"] = "array"
                    param_info["items"] = {"type": "string"}

            if param.default != inspect.Parameter.empty:
                param_info["description"] = f"Default: {param.default}"
            else:
                param_info["description"] = f"Parameter: {param_name}"
                required.append(param_name)

            properties[param_name] = param_info

        return {"type": "object", "properties": properties, "required": required}
    except Exception as e:
        print(f"  ⚠️  無法提取工具參數: {e}")
        return {"type": "object", "properties": {}, "required": []}


def create_tool_handler(tool_name: str):
    """建立工具處理器"""
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
# Tool limit 設定
# ==========================================

def get_tool_limit(agent_name: str) -> int:
    limits = {
        "analyze": 50,
        "implement": 30,
        "test": 40,
    }
    if agent_name.startswith("implement"):
        return limits["implement"]
    return limits.get(agent_name, 30)


def get_warning_points(agent_name: str) -> List[int]:
    warning_points = {
        "analyze": [25, 35, 45],
        "implement": [15, 22, 27],
        "test": [20, 30, 35],
    }
    if agent_name.startswith("implement"):
        return warning_points["implement"]
    return warning_points.get(agent_name, [15, 22, 27])


# ==========================================
# Agent 會話執行（含 active flag 防止 ghost handler）
# ==========================================

async def execute_agent_session(
    session,
    context: str,
    agent_name: str,
    max_tool_calls: int,
) -> str:
    """
    在 session 中執行一個 turn，等待 idle 後回傳回應。

    active flag 設計：
    - 共用 session 會有多個 on_event handler 並存
    - active=False 後，舊 handler 忽略新事件，不干擾下一個 phase
    """
    response_parts = []
    done = asyncio.Event()
    tool_call_count = 0
    force_output_requested = False
    tool_usage_stats = {}
    start_time = time.time()
    active = True  # 防止 ghost handler 干擾共用 session

    warning_points = get_warning_points(agent_name)

    def on_event(event):
        nonlocal tool_call_count, force_output_requested

        if not active:
            return  # 此 phase 已結束，忽略後續事件

        try:
            event_type = event.type.value if hasattr(event.type, 'value') else str(event.type)

            if event_type == "assistant.message":
                if event.data.content:
                    response_parts.append(event.data.content)
                    print(f"  📝 收集回應: {len(event.data.content)} 字元")

            elif event_type == "tool.execution_start":
                tool_call_count += 1
                tool_name = extract_tool_name(event)
                tool_usage_stats[tool_name] = tool_usage_stats.get(tool_name, 0) + 1
                print(f"  🔧 工具呼叫 #{tool_call_count}/{max_tool_calls}: {tool_name}")

                handle_tool_limit_warning(
                    tool_call_count=tool_call_count,
                    max_tool_calls=max_tool_calls,
                    warning_points=warning_points,
                    force_output_requested=force_output_requested,
                    session=session,
                    phase_name=agent_name,
                )

                if tool_call_count >= max_tool_calls:
                    force_output_requested = True

            elif event_type == "session.idle":
                print(f"  ✅ Phase 完成，共 {tool_call_count} 次工具呼叫")
                done.set()

        except Exception:
            pass

    session.on(on_event)

    print(f"  📤 發送訊息...")
    asyncio.create_task(session.send({"prompt": context}))

    try:
        await asyncio.wait_for(done.wait(), timeout=300)
    except asyncio.TimeoutError:
        print(f"  ⏱️  警告：執行超時")

    if not "".join(response_parts).strip():
        print(f"  ⚠️  未收到回應，強制要求輸出...")
        done.clear()
        asyncio.create_task(session.send({
            "prompt": (
                "Please complete your current task. "
                "Stop using tools and provide your output now. "
                "Write any required report files and summarize what you did."
            )
        }))
        try:
            await asyncio.wait_for(done.wait(), timeout=60)
        except asyncio.TimeoutError:
            print(f"  ⏱️  強制輸出也超時")

    final_response = "".join(response_parts)

    # 停用此 phase 的 handler（共用 session 的關鍵保護）
    active = False  # noqa: F841

    print_execution_stats(agent_name, time.time() - start_time, tool_call_count, max_tool_calls, tool_usage_stats)
    print_response_preview(final_response)

    return final_response


def extract_tool_name(event) -> str:
    """從事件中提取工具名稱"""
    try:
        if hasattr(event, 'data'):
            if hasattr(event.data, 'tool_name') and event.data.tool_name:
                return event.data.tool_name
            if hasattr(event.data, 'tool_requests') and event.data.tool_requests:
                req = event.data.tool_requests[0]
                if hasattr(req, 'name'):
                    return req.name
                if isinstance(req, dict) and 'name' in req:
                    return req['name']
            if hasattr(event.data, 'name') and event.data.name:
                return event.data.name
            if isinstance(event.data, dict):
                name = event.data.get('tool_name') or event.data.get('name')
                if name:
                    return name
        if hasattr(event, 'tool_name') and event.tool_name:
            return event.tool_name
        if hasattr(event, 'name') and event.name:
            return event.name
    except Exception:
        pass
    return "Unknown"


def handle_tool_limit_warning(
    tool_call_count: int,
    max_tool_calls: int,
    warning_points: List[int],
    force_output_requested: bool,
    session,
    phase_name: str,
):
    """分段警告機制：提醒 agent 接近工具上限"""
    if force_output_requested:
        return

    if tool_call_count == warning_points[0]:
        print(f"  🟡 已使用 {tool_call_count}/{max_tool_calls} 次工具")
        asyncio.create_task(session.send({
            "prompt": f"⏰ 提醒：已使用 {tool_call_count}/{max_tool_calls} 次工具。如果已有足夠資訊，請完成任務並寫入報告檔案。"
        }))

    elif tool_call_count == warning_points[1]:
        remaining = max_tool_calls - tool_call_count
        print(f"  🟠 警告：已使用 {tool_call_count}/{max_tool_calls} 次工具！")
        asyncio.create_task(session.send({
            "prompt": (
                f"⚠️ 工具使用接近上限 ({tool_call_count}/{max_tool_calls})！\n"
                f"剩餘 {remaining} 次。請儘快完成任務並寫入所有報告檔案。"
            )
        }))

    elif tool_call_count == warning_points[2]:
        print(f"  🔴 嚴重警告：接近上限 ({tool_call_count}/{max_tool_calls})！")
        asyncio.create_task(session.send({
            "prompt": (
                f"🛑 工具呼叫次數接近上限 ({tool_call_count}/{max_tool_calls})！\n"
                f"立即完成任務，寫入報告檔案，不要再呼叫工具。"
            )
        }))

    elif tool_call_count >= max_tool_calls:
        print(f"  🚨 已達工具上限！強制要求完成...")
        asyncio.create_task(session.send({
            "prompt": (
                "🚨 STOP ALL TOOL CALLS IMMEDIATELY!\n\n"
                "You have reached the tool usage limit.\n"
                "1. DO NOT use any more tools\n"
                "2. Complete your current task with what you have\n"
                "3. Write any required report files NOW\n"
                "4. Provide a summary of what you did"
            )
        }))


def print_execution_stats(
    agent_name: str,
    elapsed_time: float,
    tool_call_count: int,
    max_tool_calls: int,
    tool_usage_stats: dict,
):
    """印出執行統計"""
    print(f"\n  📊 [{agent_name.upper()}] 執行統計")
    print(f"     ⏱️  時間: {elapsed_time:.1f}s")
    print(f"     🔧 工具: {tool_call_count}/{max_tool_calls}")

    usage_rate = tool_call_count / max_tool_calls * 100 if max_tool_calls > 0 else 0

    if tool_usage_stats:
        print(f"     📋 分布:")
        for name, count in sorted(tool_usage_stats.items(), key=lambda x: -x[1]):
            pct = count / tool_call_count * 100 if tool_call_count > 0 else 0
            print(f"        • {name}: {count} ({pct:.0f}%)")

    status = (
        "🔴 達上限" if tool_call_count >= max_tool_calls else
        "🟡 接近上限" if usage_rate >= 80 else
        "🟢 正常" if usage_rate >= 30 else
        "⚪ 偏低"
    )
    print(f"     📈 使用率: {usage_rate:.0f}% ({status})")


def print_response_preview(response: str):
    """印出回應預覽"""
    print(f"\n  📄 回應長度: {len(response)} 字元")
    if response.strip():
        preview = response[:300] + ("..." if len(response) > 300 else "")
        print(f"  📄 預覽: {preview}")
    print(f"{'='*60}")
