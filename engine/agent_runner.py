"""
Agent 執行器模組 v3.1 (SDK Adapter)

透過 adapters/ 層操作 SDK，不直接 import 任何 AI SDK。

抽換 SDK 只需設定環境變數：
    export SDK_ADAPTER=copilot   # 預設
    export SDK_ADAPTER=claude
    export SDK_ADAPTER=openai

init_agent_runner() 由 main.py 傳入 ProjectConfig + ProjectSpec，
工具路徑、命令由 ProjectConfig 配置，無硬編碼。
"""
import asyncio
import time
from typing import List

from .adapters import get_adapter, get_default_model, AgentSession, AgentEvent
from .project_spec import ProjectSpec
from .config import ProjectConfig


# ==========================================
# 全域配置（由 init_agent_runner 設定）
# ==========================================

_project_config: ProjectConfig = None
_project_spec: ProjectSpec = None


def init_agent_runner(config: ProjectConfig, spec: ProjectSpec):
    """初始化 Agent Runner（必須在執行前呼叫）"""
    global _project_config, _project_spec
    _project_config = config
    _project_spec = spec
    print(f"  🤖 Agent runner initialized for {config.project_name}")


# ==========================================
# Tool 配置（按 phase 分組）
# ==========================================

ANALYZE_IMPLEMENT_TOOLS = [
    "record_tech_debt",
]

TEST_TOOLS = [
    "run_typescript_check",
    "run_eslint",
    "run_behavior_validation",
]

# init phase：探索目標專案、生成 config.yaml
# Copilot adapter 已內建同等工具，這裡供 Claude/OpenAI 使用
INIT_TOOLS = [
    "read_file",
    "list_directory",
    "search_files",
    "write_file",
]


# ==========================================
# SDK 錯誤靜默（Copilot SDK 特有，其他 SDK 無影響）
# ==========================================

def setup_sdk_error_silencing(loop) -> callable:
    """靜默 Copilot SDK 內部錯誤。回傳 restore 函式。"""
    original_handler = loop.get_exception_handler()

    def silent_sdk_errors(loop, context_dict):
        exception = context_dict.get("exception")
        if exception:
            error_msg = str(exception)
            sdk_patterns = [
                "session.usage_info", "is not a valid SessionEventType",
                "assert False", "from_union", "AssertionError",
            ]
            if any(p in error_msg or p in type(exception).__name__ for p in sdk_patterns):
                return
        if original_handler:
            original_handler(loop, context_dict)
        else:
            loop.default_exception_handler(context_dict)

    loop.set_exception_handler(silent_sdk_errors)
    return lambda: loop.set_exception_handler(original_handler)


# ==========================================
# Session 管理
# ==========================================

async def create_session(
    tool_names: List[str],
    sdk: str | None = None,
    mcp_manager=None,
) -> tuple:
    """
    建立 agent session（透過 adapter）。

    Args:
        tool_names:  自訂工具名稱列表
        sdk:         "copilot" | "claude" | "openai"（None 讀 SDK_ADAPTER env）
        mcp_manager: MCPClientManager 實例（None = 不使用 MCP）

    Returns:
        (adapter, session) 元組
    """
    adapter = get_adapter(sdk)
    model = get_default_model(sdk)
    await adapter.start()
    session = await adapter.create_session(
        tool_names=tool_names,
        model=model,
        mcp_manager=mcp_manager,
    )
    return adapter, session


# 向後相容別名
create_copilot_session = create_session


async def run_in_session(
    session: AgentSession,
    phase_name: str,
    user_message: str,
    max_tool_calls: int,
    images: list[dict] | None = None,
) -> str:
    """在指定 session 執行一個 skill phase"""
    print(f"\n{'='*60}")
    print(f"🤖 [{phase_name.upper()}] 執行中...")
    print(f"{'='*60}")

    # 只顯示 --- 之後的任務段（略過 project context 與 skill body）
    parts = user_message.split("---", 1)
    task_preview = parts[-1].strip() if len(parts) > 1 else user_message.strip()
    if len(task_preview) > 800:
        task_preview = task_preview[:800] + "\n  ...(截斷)"
    print(f"  📤 發送訊息:\n")
    for line in task_preview.splitlines():
        print(f"    {line}")

    return await execute_agent_session(
        session=session,
        context=user_message,
        agent_name=phase_name,
        max_tool_calls=max_tool_calls,
        images=images,
    )


# ==========================================
# Tool limit 設定
# ==========================================

def get_tool_limit(agent_name: str) -> int:
    limits = {"analyze": 50, "implement": 30, "test": 40}
    if agent_name.startswith("implement"):
        return 30
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
# Agent 會話執行（SDK 無關）
# ==========================================

IDLE_TIMEOUT = 90  # 連續無事件超過此秒數視為卡死


async def execute_agent_session(
    session: AgentSession,
    context: str,
    agent_name: str,
    max_tool_calls: int,
    images: list[dict] | None = None,
) -> str:
    """
    在 session 中執行一個 turn，等待 idle 後回傳回應。

    使用標準化 AgentEvent 格式，不依賴任何特定 SDK 的事件結構。

    active flag 設計：
    - 共用 session（analyze + implement）會有多個 on_event handler 並存
    - active=False 後，舊 handler 忽略新事件，不干擾下一個 phase

    timeout 設計（idle timeout，類 debounce）：
    - 每次有事件（message / tool_start / idle）重置 last_activity
    - 連續 IDLE_TIMEOUT 秒無任何事件才視為卡死並中止
    - 不限制總執行時間，LLM 健康工作時不會被誤殺
    """
    response_parts = []
    done = asyncio.Event()
    tool_call_count = 0
    force_output_requested = False
    tool_usage_stats = {}
    start_time = time.time()
    active = True
    in_message_stream = False
    after_tool_call = False
    last_activity = time.time()

    warning_points = get_warning_points(agent_name)

    def on_event(event: AgentEvent):
        nonlocal tool_call_count, force_output_requested, in_message_stream, after_tool_call, last_activity
        last_activity = time.time()

        if not active:
            return

        try:
            if event.type == "message":
                if event.content:
                    response_parts.append(event.content)
                    if not in_message_stream:
                        # Phase 第一段回應：印 header
                        print(f"\n  📝 AI 回應:")
                        print(f"  {'─'*50}")
                        in_message_stream = True
                    elif after_tool_call:
                        # 工具呼叫後繼續回應：空一行再接
                        print()
                    after_tool_call = False

                    # 格式化：冒號（半形 : 或全形 ：）後插入段落換行
                    # 兩種場景：
                    #   1. mid-chunk：「中文句子：下一句」在同一個 chunk → regex 替換
                    #   2. end-of-chunk：冒號剛好在 chunk 尾端 → endswith 補換行
                    import re
                    content = event.content

                    # 場景 1：全形 ：前後都是 CJK 字元（AI 步驟說明分隔）
                    # lookahead + lookbehind 雙重保護，避免誤觸 時間：10:30 / URL / JSON
                    content = re.sub(
                        r'(?<=[一-鿿぀-ヿ＀-￯])：(?=[一-鿿぀-ヿ＀-￯])',
                        '.\n\n',
                        content,
                    )

                    # 場景 2：行尾半形或全形冒號（場景 1 已處理全形，此處補半形）
                    stripped = content.rstrip()
                    if stripped.endswith((":", "：")):
                        content = stripped[:-1] + ".\n\n"

                    print(content, end="", flush=True)

            elif event.type == "tool_start":
                tool_call_count += 1
                tool_name = event.tool_name or "Unknown"
                tool_usage_stats[tool_name] = tool_usage_stats.get(tool_name, 0) + 1
                # 工具呼叫前後各空一行，與 AI 回應文字分開
                print(f"\n\n  🔧 工具呼叫 #{tool_call_count}/{max_tool_calls}: {tool_name}\n")
                after_tool_call = True

                _handle_tool_limit_warning(
                    tool_call_count=tool_call_count,
                    max_tool_calls=max_tool_calls,
                    warning_points=warning_points,
                    force_output_requested=force_output_requested,
                    session=session,
                    phase_name=agent_name,
                )

                if tool_call_count >= max_tool_calls:
                    force_output_requested = True

            elif event.type == "usage" and event.usage:
                session.token_usage["input"] += event.usage.get("input", 0)
                session.token_usage["output"] += event.usage.get("output", 0)

            elif event.type == "idle":
                if in_message_stream:
                    print()  # 確保最後一行有換行
                    in_message_stream = False
                print(f"  {'─'*50}")
                print(f"  ✅ Phase 完成，共 {tool_call_count} 次工具呼叫")
                done.set()

        except Exception:
            pass

    session.on(on_event)
    asyncio.create_task(session.send(context, images=images))

    # Idle timeout（類 debounce）：
    # 每次有事件 last_activity 被重置，只有連續無事件超過 IDLE_TIMEOUT 秒才中止。
    while not done.is_set():
        remaining = IDLE_TIMEOUT - (time.time() - last_activity)
        if remaining <= 0:
            print(f"  ⏱️  警告：{IDLE_TIMEOUT}s 無任何事件，視為卡死")
            break
        try:
            await asyncio.wait_for(done.wait(), timeout=remaining)
        except asyncio.TimeoutError:
            continue  # 再檢查一次 last_activity（可能剛好有事件進來）

    if not "".join(response_parts).strip():
        print(f"  ⚠️  未收到回應，強制要求輸出...")
        done.clear()
        last_activity = time.time()
        asyncio.create_task(session.send(
            "Please complete your current task. "
            "Stop using tools and provide your output now. "
            "Write any required report files and summarize what you did."
        ))
        while not done.is_set():
            remaining = 60 - (time.time() - last_activity)
            if remaining <= 0:
                print(f"  ⏱️  強制輸出也超時")
                break
            try:
                await asyncio.wait_for(done.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                continue

    final_response = "".join(response_parts)
    active = False  # noqa: F841

    _print_execution_stats(agent_name, time.time() - start_time, tool_call_count, max_tool_calls, tool_usage_stats)
    _print_response_preview(final_response)

    return final_response


# ==========================================
# 工具上限警告機制
# ==========================================

def _handle_tool_limit_warning(
    tool_call_count: int,
    max_tool_calls: int,
    warning_points: List[int],
    force_output_requested: bool,
    session: AgentSession,
    phase_name: str,
):
    if force_output_requested:
        return

    warning_msg = None

    if tool_call_count == warning_points[0]:
        print(f"  🟡 已使用 {tool_call_count}/{max_tool_calls} 次工具")
        warning_msg = f"⏰ 已使用 {tool_call_count}/{max_tool_calls} 次工具。如果已有足夠資訊，請完成任務並寫入報告。"

    elif tool_call_count == warning_points[1]:
        remaining = max_tool_calls - tool_call_count
        print(f"  🟠 警告：已使用 {tool_call_count}/{max_tool_calls} 次工具！")
        warning_msg = (
            f"⚠️ 工具使用接近上限 ({tool_call_count}/{max_tool_calls})！"
            f"剩餘 {remaining} 次。請儘快完成任務並寫入所有報告。"
        )

    elif tool_call_count == warning_points[2]:
        print(f"  🔴 嚴重警告：接近上限 ({tool_call_count}/{max_tool_calls})！")
        warning_msg = (
            f"🛑 工具呼叫次數接近上限 ({tool_call_count}/{max_tool_calls})！"
            f"立即完成任務，寫入報告，不要再呼叫工具。"
        )

    elif tool_call_count >= max_tool_calls:
        print(f"  🚨 已達工具上限！強制要求完成...")
        warning_msg = (
            "🚨 STOP ALL TOOL CALLS IMMEDIATELY! "
            "You have reached the tool usage limit. "
            "Complete your task with what you have, write required report files NOW."
        )

    if warning_msg:
        session.pending_messages.append(warning_msg)


# ==========================================
# 統計與 log 輸出
# ==========================================

def _print_execution_stats(
    agent_name: str,
    elapsed: float,
    tool_call_count: int,
    max_tool_calls: int,
    tool_usage_stats: dict,
):
    print(f"\n  📊 [{agent_name.upper()}] 執行統計")
    print(f"     ⏱️  時間: {elapsed:.1f}s")
    print(f"     🔧 工具: {tool_call_count}/{max_tool_calls}")

    if tool_usage_stats:
        print(f"     📋 分布:")
        for name, count in sorted(tool_usage_stats.items(), key=lambda x: -x[1]):
            pct = count / tool_call_count * 100 if tool_call_count > 0 else 0
            print(f"        • {name}: {count} ({pct:.0f}%)")

    usage_rate = tool_call_count / max_tool_calls * 100 if max_tool_calls > 0 else 0
    status = (
        "🔴 達上限" if tool_call_count >= max_tool_calls else
        "🟡 接近上限" if usage_rate >= 80 else
        "🟢 正常" if usage_rate >= 30 else
        "⚪ 偏低"
    )
    print(f"     📈 使用率: {usage_rate:.0f}% ({status})")


def _print_response_preview(response: str):
    print(f"\n  📄 回應長度: {len(response)} 字元")
    if response.strip():
        preview = response[:300] + ("..." if len(response) > 300 else "")
        print(f"  📄 預覽: {preview}")
    print(f"{'='*60}")
