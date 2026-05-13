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
