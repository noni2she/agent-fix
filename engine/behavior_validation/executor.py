"""行為驗證主執行器

入口點：BehaviorValidator
- 由 engine/tools.py 的 run_behavior_validation() 呼叫
- 接收 dynamic_scenario（LLM 生成的 JSON）
- 管理 dev server 生命週期、執行 Playwright 測試
- 回傳 ValidationReport
"""
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# agent 根目錄（相對於此檔案：behavior_validation/ → engine/ → agent-root/）
_AGENT_ROOT = Path(__file__).parent.parent.parent.resolve()

from pydantic import BaseModel

from .dev_server import DevServerManager
from .playwright_runner import PlaywrightRunner
from .scenarios import create_scenario_from_dict, TestScenario


class ScenarioResult(BaseModel):
    """單一場景執行結果"""
    name: str
    passed: bool
    duration_seconds: float
    screenshots: list[str] = []
    error: Optional[str] = None
    console_errors: list[dict] = []   # 失敗時附上 browser console errors


class ValidationReport(BaseModel):
    """完整驗證報告"""
    issue_id: str
    test_date: datetime
    scenarios_run: int = 0
    scenarios_passed: int = 0
    results: list[ScenarioResult] = []

    @property
    def verdict(self) -> str:
        if self.scenarios_run == 0:
            return "SKIPPED"
        return "PASS" if self.scenarios_passed == self.scenarios_run else "FAIL"


class BehaviorValidator:
    """行為驗證器

    Args:
        project_root: 被測專案根目錄（用於啟動 dev server）
        port: dev server port
        workspace: monorepo workspace 名稱（fallback dev server 啟動方式）
        headless: Playwright 是否無頭模式（agent/CI 環境設 True）
        dev_command: 完整 dev server 啟動命令（list 形式，優先於 workspace）
        screenshot_dir: 截圖儲存目錄（預設 issues/screenshots/）
    """

    def __init__(
        self,
        project_root: Path,
        port: int = 3000,
        workspace: Optional[str] = None,
        headless: bool = True,
        dev_command: Optional[list[str]] = None,
        screenshot_dir: Optional[Path] = None,
        channel: Optional[str] = None,
    ):
        self.project_root = project_root
        self.port = port
        self.workspace = workspace
        self.headless = headless
        self.dev_command = dev_command
        self.channel = channel  # "chrome" → 系統 Chrome；None → Playwright Chromium（自動安裝）
        self.base_url = f"http://localhost:{port}"
        self.screenshot_dir = screenshot_dir or (_AGENT_ROOT / "issues" / "screenshots")

    async def validate(
        self,
        issue_id: str,
        dynamic_scenario: Optional[Dict[str, Any]] = None,
    ) -> ValidationReport:
        """執行行為驗證

        Args:
            issue_id: Issue ID（用於命名報告）
            dynamic_scenario: LLM 生成的測試場景 dict（url_path + actions + assertions）

        Returns:
            ValidationReport
        """
        print(f"\n{'='*60}")
        print(f"  🧪 行為驗證 — Issue {issue_id}")
        print(f"{'='*60}")

        report = ValidationReport(issue_id=issue_id, test_date=datetime.now())

        if not dynamic_scenario:
            print("  ⚠️  未提供動態場景，跳過行為驗證")
            return report

        print("  📋 使用 LLM 動態生成的測試場景")
        scenario = create_scenario_from_dict({
            "name": issue_id,
            **dynamic_scenario,
        })

        # 啟動 dev server
        server = DevServerManager(
            port=self.port,
            project_root=self.project_root,
            dev_command=self.dev_command,
            workspace=self.workspace,
        )
        server_started = await server.start()
        if not server_started:
            print("  ❌ Dev server 未就緒，跳過行為驗證")
            return report

        # 執行 Playwright 場景
        screenshot_dir = self.screenshot_dir / issue_id
        try:
            async with PlaywrightRunner(
                base_url=self.base_url,
                headless=self.headless,
                screenshot_dir=screenshot_dir,
                channel=self.channel,
            ) as runner:
                result = await self._run_scenario(runner, scenario)
                report.results.append(result)
                report.scenarios_run += 1
                if result.passed:
                    report.scenarios_passed += 1
        finally:
            await server.stop()

        print(f"\n{'='*60}")
        print(f"  判決: {report.verdict}")
        print(f"  通過: {report.scenarios_passed}/{report.scenarios_run}")
        print(f"{'='*60}\n")

        return report

    async def _run_scenario(
        self, runner: PlaywrightRunner, scenario: TestScenario
    ) -> ScenarioResult:
        """執行單一場景，回傳結果"""
        print(f"\n  🎬 場景: {scenario.name}")
        start = datetime.now()
        screenshots = []

        try:
            # 導航到起始頁面
            await runner.page.goto(
                f"{self.base_url}{scenario.url_path}",
                wait_until="networkidle",
            )

            # 執行動作序列
            for i, action in enumerate(scenario.actions):
                desc = action.description or f"{action.type}"
                print(f"     [{i+1}] {desc}")
                result = await runner.execute_action(action)
                if not result.get("success"):
                    raise RuntimeError(f"動作失敗 [{desc}]: {result.get('error')}")
                if "screenshot" in result:
                    screenshots.append(result["screenshot"])

            # 驗證斷言
            for i, assertion in enumerate(scenario.assertions):
                desc = assertion.description or f"{assertion.type} {assertion.selector or ''}"
                result = await runner.check_assertion(assertion)
                if not result.get("passed"):
                    raise AssertionError(
                        f"斷言失敗 [{desc}]: "
                        f"expected={assertion.expected}, actual={result.get('actual')}"
                    )
                print(f"     ✅ {desc}")

            duration = (datetime.now() - start).total_seconds()
            print(f"  ✅ 場景通過 ({duration:.1f}s)")
            return ScenarioResult(
                name=scenario.name,
                passed=True,
                duration_seconds=duration,
                screenshots=screenshots,
            )

        except Exception as e:
            duration = (datetime.now() - start).total_seconds()
            console_errors = runner.get_console_errors()
            print(f"  ❌ 場景失敗: {e}")
            if console_errors:
                print(f"  🔴 Console errors ({len(console_errors)}):")
                for ce in console_errors[:5]:   # 最多印 5 條，避免洗版
                    print(f"     [{ce['type']}] {ce['text'][:120]}")
            # 自動截圖留存錯誤現場
            try:
                error_shot = await runner._screenshot("fail")
                screenshots.append(str(error_shot))
            except Exception:
                pass
            return ScenarioResult(
                name=scenario.name,
                passed=False,
                duration_seconds=duration,
                screenshots=screenshots,
                error=str(e),
                console_errors=console_errors,
            )
