"""行為驗證主執行器

入口點：BehaviorValidator
- 由 engine/tools.py 的 run_behavior_validation() 呼叫
- 接收 dynamic_scenario（LLM 生成的 JSON）
- 管理 dev server 生命週期、執行 Playwright 測試
- 回傳 ValidationReport
"""
import os
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
        auth_config: 登入認證設定（選填）
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
        auth_config=None,  # Optional[AuthConfig]，避免 circular import 不強型別
    ):
        self.project_root = project_root
        self.port = port
        self.workspace = workspace
        self.headless = headless
        self.dev_command = dev_command
        self.channel = channel  # "chrome" → 系統 Chrome；None → Playwright Chromium（自動安裝）
        self.auth_config = auth_config
        self.base_url = f"http://localhost:{port}"
        self.screenshot_dir = screenshot_dir or (_AGENT_ROOT / "issues" / "screenshots")

    @staticmethod
    async def _detect_login_form(page) -> Optional[dict]:
        """
        自動偵測登入表單的 selector。

        偵測邏輯（由特徵明確到模糊）：
          password → input[type=password]（HTML 標準，幾乎 100% 通用）
          username → 同 form 內最近的 input[type=email]，
                     或 password 前面的 input[type=text]
          submit   → 同 form 的 button[type=submit]，
                     或 input[type=submit]，
                     或最後一個 button

        Returns:
            {'username': sel, 'password': sel, 'submit': sel} 或 None（偵測失敗）
        """
        detected = await page.evaluate("""() => {
            const pwInput = document.querySelector('input[type=password]');
            if (!pwInput) return null;

            // 找 form 容器（往上找 <form>，找不到就用 document.body）
            const form = pwInput.closest('form') || document.body;

            // username：email input 優先，否則找 password 前面的 text input
            let usernameEl =
                form.querySelector('input[type=email]') ||
                form.querySelector('input[name*=email i]') ||
                form.querySelector('input[name*=user i]') ||
                form.querySelector('input[name*=account i]') ||
                form.querySelector('input[name*=login i]') ||
                form.querySelector('input[name*=phone i]');

            if (!usernameEl) {
                // 找所有 text inputs，取 password 前面那一個
                const inputs = [...form.querySelectorAll('input[type=text], input:not([type])')];
                const pwIdx = [...form.querySelectorAll('input')].indexOf(pwInput);
                usernameEl = inputs.filter(el => {
                    const idx = [...form.querySelectorAll('input')].indexOf(el);
                    return idx < pwIdx;
                }).pop() || null;
            }

            // submit：type=submit 優先，否則取 form 最後一個 button
            const submitEl =
                form.querySelector('button[type=submit]') ||
                form.querySelector('input[type=submit]') ||
                [...form.querySelectorAll('button')].pop();

            if (!usernameEl || !submitEl) return null;

            // 產生最穩定的 selector（有 id 用 id；有 name 用 name；fallback type）
            const toSel = el => {
                if (el.id)   return '#' + CSS.escape(el.id);
                if (el.name) return `[name="${el.name}"]`;
                if (el.type) return `input[type="${el.type}"]`;
                return el.tagName.toLowerCase();
            };

            return {
                username: toSel(usernameEl),
                password: toSel(pwInput),
                submit:   submitEl.id
                            ? '#' + CSS.escape(submitEl.id)
                            : submitEl.type === 'submit'
                              ? 'button[type=submit]'
                              : submitEl.tagName.toLowerCase(),
            };
        }""")
        return detected

    async def _ensure_authenticated(self) -> Optional[Path]:
        """
        確保 storageState 存在且未過期，回傳可用的 state 檔案路徑。

        流程：
          1. 若 storageState 存在且未超過 TTL → 直接重用
          2. 否則 → 讀取 env 帳密 → 導向 login_url → 自動偵測或使用指定 selector
             → 填入帳密送出 → 確認成功 → 儲存 state

        Returns:
            storageState 檔案的 Path，若無 auth_config 或帳密缺失則回傳 None
        """
        auth = self.auth_config
        if not auth:
            return None

        state_path = _AGENT_ROOT / auth.storage_state_path

        # 檢查快取是否有效
        if state_path.exists():
            age_hours = (datetime.now().timestamp() - state_path.stat().st_mtime) / 3600
            if age_hours < auth.state_ttl_hours:
                print(f"  🔐 使用已快取的 auth state（{age_hours:.1f}h 前建立，TTL={auth.state_ttl_hours}h）")
                return state_path
            print(f"  🔐 Auth state 已過期（{age_hours:.1f}h > TTL {auth.state_ttl_hours}h），重新登入")
        else:
            print(f"  🔐 未找到 auth state，執行初次登入流程")

        # 從環境變數讀取帳密
        username = os.getenv(auth.username_env)
        password = os.getenv(auth.password_env)

        if not username or not password:
            print(f"  ⚠️  缺少環境變數 {auth.username_env} / {auth.password_env}，跳過 auth（測試可能因未登入而失敗）")
            return None

        # 執行 login flow
        auth_screenshot_dir = self.screenshot_dir / "_auth_setup"
        async with PlaywrightRunner(
            base_url=self.base_url,
            headless=self.headless,
            screenshot_dir=auth_screenshot_dir,
            channel=self.channel,
        ) as runner:
            try:
                print(f"  🔐 導向：{auth.login_url}")
                await runner.page.goto(
                    f"{self.base_url}{auth.login_url}",
                    wait_until="networkidle",
                    timeout=15000,
                )

                # Modal-based login：點擊 trigger 讓表單出現
                if auth.login_trigger:
                    print(f"  🔐 觸發登入表單：{auth.login_trigger}")
                    await runner.page.click(auth.login_trigger, timeout=10000)
                    # 等待 password input 出現（表示 modal/表單已 render）
                    await runner.page.wait_for_selector(
                        "input[type=password]", timeout=10000
                    )

                # selector：優先使用 config 指定值，否則自動偵測
                if auth.username_selector and auth.password_selector and auth.submit_selector:
                    u_sel = auth.username_selector
                    p_sel = auth.password_selector
                    s_sel = auth.submit_selector
                    print(f"  🔐 使用 config 指定的 selector")
                else:
                    print(f"  🔍 自動偵測登入表單 selector...")
                    detected = await self._detect_login_form(runner.page)
                    if not detected:
                        print(f"  ❌ 無法自動偵測登入表單（建議手動在 config 指定 selector）")
                        return None
                    u_sel = auth.username_selector or detected["username"]
                    p_sel = auth.password_selector or detected["password"]
                    s_sel = auth.submit_selector or detected["submit"]
                    print(f"  ✅ 偵測到表單：username={u_sel}, password={p_sel}, submit={s_sel}")

                url_before = runner.page.url
                await runner.page.fill(u_sel, username)
                await runner.page.fill(p_sel, password)
                await runner.page.click(s_sel)

                # 確認登入成功：優先用指定 selector，否則等待 URL 變化
                if auth.success_indicator:
                    await runner.page.wait_for_selector(auth.success_indicator, timeout=15000)
                else:
                    await runner.page.wait_for_function(
                        f"() => window.location.href !== {repr(url_before)}",
                        timeout=15000,
                    )
                print(f"  ✅ 登入成功（→ {runner.page.url}）")

                # 儲存 storageState
                await runner.save_storage_state(state_path)
                print(f"  💾 Auth state 已儲存：{state_path}")
                return state_path

            except Exception as e:
                print(f"  ❌ 登入失敗：{e}（測試將以未登入狀態繼續）")
                try:
                    await runner._screenshot("auth-failed")
                except Exception:
                    pass
                return None

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

        # 處理 auth：取得 storageState（只在 server 就緒後才能走 login flow）
        storage_state = await self._ensure_authenticated()

        # 執行 Playwright 場景
        screenshot_dir = self.screenshot_dir / issue_id
        try:
            async with PlaywrightRunner(
                base_url=self.base_url,
                headless=self.headless,
                screenshot_dir=screenshot_dir,
                channel=self.channel,
                storage_state=storage_state,
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
