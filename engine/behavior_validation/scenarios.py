"""測試場景定義 - AI 動態生成版本

此模組提供測試場景的資料模型和執行工具函式。
不再預定義場景，而是由 Tester Agent 根據 Issue 動態生成測試。
"""
from typing import Optional, Any, Literal, Dict
from pydantic import BaseModel


# ==========================================
# 資料模型定義
# ==========================================

class ActionStep(BaseModel):
    """Playwright 測試動作

    支援的動作類型：
    - goto: 導航到指定 URL
    - click: 點擊元素
    - wait_for: 等待元素出現
    - type: 在輸入框輸入文字
    - screenshot: 擷取螢幕截圖
    """
    type: Literal["goto", "click", "wait_for", "type", "screenshot"]
    selector: Optional[str] = None   # CSS selector
    value: Optional[str] = None      # 輸入值（用於 type / goto 動作）
    timeout: int = 10000             # 超時時間（毫秒）
    description: Optional[str] = None  # 動作描述（用於日誌）


class Assertion(BaseModel):
    """測試斷言

    支援的斷言類型：
    - visible: 檢查元素是否可見
    - text_content: 檢查元素文字內容
    - url: 檢查當前 URL
    - count: 檢查元素數量
    """
    type: Literal["visible", "text_content", "url", "count"]
    selector: Optional[str] = None      # CSS selector（visible, text_content, count 需要）
    expected: Any                       # 預期值
    expected_min: Optional[int] = None  # 最小數量（count 類型使用）
    description: Optional[str] = None   # 斷言描述


class TestScenario(BaseModel):
    """完整的測試場景

    由 Tester Agent 從 Issue 的 reproduction_steps 動態生成。
    """
    name: str                           # 場景名稱（通常是 issue_id）
    url_path: str                       # 測試起始 URL 路徑
    actions: list[ActionStep]           # 動作序列
    assertions: list[Assertion]         # 驗證規則列表
    description: Optional[str] = None  # 場景描述


# ==========================================
# 工具函式
# ==========================================

def create_scenario_from_dict(data: Dict) -> TestScenario:
    """從字典建立測試場景

    用於將 Tester Agent 生成的 JSON 轉換為 TestScenario 物件。

    Args:
        data: 包含 url_path, actions, assertions 的字典

    Returns:
        TestScenario 物件
    """
    return TestScenario(
        name=data.get("name", "dynamic_scenario"),
        url_path=data["url_path"],
        actions=[ActionStep(**action) for action in data["actions"]],
        assertions=[Assertion(**assertion) for assertion in data["assertions"]],
        description=data.get("description"),
    )


def validate_scenario(scenario: TestScenario) -> tuple[bool, Optional[str]]:
    """驗證測試場景的完整性

    Returns:
        (是否有效, 錯誤訊息)
    """
    if not scenario.actions:
        return False, "場景必須包含至少一個動作"

    if not scenario.assertions:
        return False, "場景必須包含至少一個斷言"

    for i, action in enumerate(scenario.actions):
        if action.type in ["click", "wait_for", "type"] and not action.selector:
            return False, f"動作 {i} ({action.type}) 缺少 selector"
        if action.type == "type" and not action.value:
            return False, f"動作 {i} (type) 缺少 value"

    for i, assertion in enumerate(scenario.assertions):
        if assertion.type in ["visible", "text_content", "count"] and not assertion.selector:
            return False, f"斷言 {i} ({assertion.type}) 缺少 selector"

    return True, None
