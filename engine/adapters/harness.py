"""
Harness enforcement utilities — phase-aware tool constraints.
Called by all three adapters (claude, openai, copilot) at tool dispatch time.
Keeping logic here means new constraints are added once and apply everywhere.
"""

_SCREENSHOT_TOOL = "take_screenshot"
_SCREENSHOT_REPRODUCE_LIMIT = 1  # 1 allowed (the final reproduction.png save)

_EVALUATE_SCRIPT_TOOL = "evaluate_script"
_EVALUATE_SCRIPT_LIMIT = 5
_EVALUATE_SCRIPT_PPI = (
    "🚨 evaluate_script 已達 5 次上限。立即停止所有工具呼叫，輸出 Evidence Package：\n"
    "observed: <觀察到的實際行為>\n"
    "objective_signals: <console 錯誤 / network 4xx-5xx 等客觀訊號>\n"
    "instability_flags: <若有不穩定跡象列出，否則填 none>\n"
    "reproduce_confidence: <0.0–1.0>"
)

_BEHAVIOR_VALIDATION_TOOL = "run_behavior_validation"
_BEHAVIOR_VALIDATION_LIMIT = 3

_READ_FILE_TOOLS = {"read_file"}
_READ_FILE_MAX_CHARS = 200_000
_TRUNCATION_SUFFIX = (
    "\n\n[TRUNCATED: response exceeded 200K chars. "
    "Use a more specific query or read a subsection.]"
)


def check_tool_blocked(tool_name: str, session) -> str | None:
    """Returns an error string if the tool should be blocked; None if execution is allowed."""
    if session is None:
        return None

    # take_screenshot: max 1 call in REPRODUCE phase (reserve for reproduction.png)
    if (
        tool_name == _SCREENSHOT_TOOL
        and "reproduce" in getattr(session, "harness_phase", "").lower()
    ):
        count = getattr(session, "_screenshot_count", 0)
        session._screenshot_count = count + 1
        if count >= _SCREENSHOT_REPRODUCE_LIMIT:
            return (
                "❌ REPRODUCE 階段 take_screenshot 已達上限（1次）。"
                "請改用 take_snapshot（accessibility tree，無 base64 消耗）"
            )

    # evaluate_script: max 5 calls in REPRODUCE phase (enforced at handler level for all adapters)
    if (
        tool_name == _EVALUATE_SCRIPT_TOOL
        and "reproduce" in getattr(session, "harness_phase", "").lower()
    ):
        count = getattr(session, "_evaluate_script_count", 0)
        session._evaluate_script_count = count + 1
        if count >= _EVALUATE_SCRIPT_LIMIT:
            return _EVALUATE_SCRIPT_PPI

    # run_behavior_validation: max 3 calls in TEST phase
    # Prevents using the tool as an exploratory REPL; agent must use view/bash first
    if (
        tool_name == _BEHAVIOR_VALIDATION_TOOL
        and "test" in getattr(session, "harness_phase", "").lower()
    ):
        count = getattr(session, "_behavior_validation_count", 0)
        session._behavior_validation_count = count + 1
        if count >= _BEHAVIOR_VALIDATION_LIMIT:
            return (
                "❌ run_behavior_validation 已達 3 次上限。"
                "請先用 view/bash 確認頁面結構與 selector，"
                "整理好完整的 scenario 之後才能繼續呼叫。"
                "若確認環境限制無法自動化，請直接撰寫報告並標記 SKIPPED。"
            )

    return None


def apply_tool_result_limits(tool_name: str, result: str, session) -> str:
    """Post-processes a tool result; applies size limits and phase-specific constraints."""
    if session is None:
        return result

    # read_file: truncate at 200K chars in RCA phase (prevents node_modules scan timeouts)
    if (
        tool_name in _READ_FILE_TOOLS
        and "rca" in getattr(session, "harness_phase", "").lower()
        and len(result) > _READ_FILE_MAX_CHARS
    ):
        return result[:_READ_FILE_MAX_CHARS] + _TRUNCATION_SUFFIX

    return result
