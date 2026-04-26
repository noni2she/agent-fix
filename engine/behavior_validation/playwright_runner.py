"""Playwright 瀏覽器自動化"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright, Page, Error as PlaywrightError
from .scenarios import ActionStep, Assertion


# ==========================================
# Chromium 自動安裝（process 內只跑一次）
# ==========================================

_chromium_install_checked = False


def _ensure_chromium_installed() -> None:
    """
    確保 Playwright 自帶的 Chromium binary 已安裝。
    冪等：已裝則秒過，未裝才下載（約 100MB）。
    process 內只執行一次。
    """
    global _chromium_install_checked
    if _chromium_install_checked:
        return

    print("  🔍 檢查 Playwright Chromium binary...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    _chromium_install_checked = True

    if result.returncode == 0:
        # 已安裝時輸出通常是空的；安裝時會有進度訊息
        if result.stdout.strip():
            print(f"  ✅ Chromium 安裝完成")
        else:
            print(f"  ✅ Chromium 已就緒")
    else:
        print(f"  ⚠️  playwright install chromium 失敗: {result.stderr.strip()}")
        print(f"     請手動執行: playwright install chromium")


class PlaywrightRunner:
    """Playwright 執行器（async context manager）"""

    def __init__(
        self,
        base_url: str,
        headless: bool = True,
        screenshot_dir: Path = None,
        channel: Optional[str] = None,
    ):
        self.base_url = base_url
        self.headless = headless
        self.screenshot_dir = screenshot_dir or Path("./screenshots")
        self.channel = channel  # e.g. "chrome" → 使用系統 Chrome；None → 使用 Playwright Chromium
        self.playwright = None
        self.browser = None
        self.page: Page = None
        self.console_logs: list[dict] = []   # 收集整個 session 的 console 輸出

    async def __aenter__(self):
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # 使用系統 Chrome 時跳過安裝檢查；使用 Playwright Chromium 時自動確保已安裝
        if not self.channel:
            _ensure_chromium_installed()

        self.playwright = await async_playwright().start()
        launch_kwargs = {"headless": self.headless}
        if self.channel:
            launch_kwargs["channel"] = self.channel
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)
        context = await self.browser.new_context(viewport={"width": 1280, "height": 720})
        self.page = await context.new_page()
        self.page.set_default_timeout(30000)

        # 監聽 console 輸出與未捕捉例外
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_pageerror)

        return self

    def _on_console(self, msg) -> None:
        """收集 console 訊息（log / warn / error / info）"""
        self.console_logs.append({
            "type": msg.type,
            "text": msg.text,
        })

    def _on_pageerror(self, err) -> None:
        """收集未捕捉的 JS 例外"""
        self.console_logs.append({
            "type": "uncaught_error",
            "text": str(err),
        })

    def get_console_errors(self) -> list[dict]:
        """只回傳 error / uncaught_error 層級的訊息"""
        return [
            log for log in self.console_logs
            if log["type"] in ("error", "uncaught_error")
        ]

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def execute_action(self, action: ActionStep) -> dict:
        """執行單一動作"""
        try:
            if action.type == "goto":
                await self.page.goto(
                    f"{self.base_url}{action.value or '/'}",
                    wait_until="networkidle",
                    timeout=action.timeout,
                )
            elif action.type == "wait_for":
                await self.page.wait_for_selector(action.selector, timeout=action.timeout)
            elif action.type == "click":
                await self.page.click(action.selector, timeout=action.timeout)
            elif action.type == "type":
                await self.page.fill(action.selector, action.value, timeout=action.timeout)
            elif action.type == "screenshot":
                path = await self._screenshot(action.description or "action")
                return {"success": True, "screenshot": str(path)}
            return {"success": True}
        except PlaywrightError as e:
            return {"success": False, "error": str(e)}

    async def check_assertion(self, assertion: Assertion) -> dict:
        """檢查單一斷言"""
        try:
            if assertion.type == "visible":
                actual = await self.page.is_visible(assertion.selector)
                return {"passed": actual == assertion.expected, "actual": actual}
            elif assertion.type == "text_content":
                el = await self.page.query_selector(assertion.selector)
                actual = await el.text_content() if el else ""
                return {"passed": assertion.expected in actual, "actual": actual}
            elif assertion.type == "url":
                actual = self.page.url
                return {"passed": assertion.expected in actual, "actual": actual}
            elif assertion.type == "count":
                elements = await self.page.query_selector_all(assertion.selector)
                actual = len(elements)
                if assertion.expected_min is not None:
                    return {"passed": actual >= assertion.expected_min, "actual": actual}
                return {"passed": actual == assertion.expected, "actual": actual}
        except PlaywrightError as e:
            return {"passed": False, "error": str(e)}
        return {"passed": False, "error": f"Unknown assertion type: {assertion.type}"}

    async def _screenshot(self, name: str) -> Path:
        """截圖並回傳檔案路徑"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.screenshot_dir / f"{timestamp}_{name}.png"
        await self.page.screenshot(path=str(path))
        return path
