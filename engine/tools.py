"""
自訂工具函式庫（僅保留 SDK 未內建的業務邏輯工具）

Copilot SDK 已內建以下工具，不需要自訂：
- execute (shell/Bash): 任意 shell 指令（含 git 操作）
- read (Read): 讀取檔案
- edit (Edit/Write): 編輯/寫入檔案
- search (Grep/Glob): 文字搜尋 + 檔案搜尋

本檔案僅保留有封裝價值的業務邏輯工具。
"""
import asyncio
import json
import subprocess
import datetime
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .config import ProjectConfig


# ==========================================
# 全域配置（由 main.py 初始化）
# ==========================================

_project_config: Optional[ProjectConfig] = None


def init_tools(config: ProjectConfig):
    """
    初始化工具系統（必須在使用工具前呼叫）

    Args:
        config: 專案配置物件
    """
    global _project_config
    _project_config = config
    print(f"  🔧 Tools initialized for project: {config.project_name}")


def _get_config() -> ProjectConfig:
    """取得配置（內部使用）"""
    if _project_config is None:
        raise RuntimeError(
            "Tools not initialized. Call init_tools(config) first in main.py"
        )
    return _project_config


# ==========================================
# 品質檢查工具（封裝 config + timeout + 錯誤摘要）
# ==========================================

def run_typescript_check() -> str:
    """
    執行 TypeScript 編譯檢查

    封裝價值：從 config 讀取命令、自動 timeout、錯誤摘要（只顯示前 10 個錯誤）
    """
    config = _get_config()
    project_root = config.get_project_root()

    try:
        ts_config = config.quality_checks.typescript
        if not ts_config.enabled:
            return "ℹ️  TypeScript check is disabled in config"

        cmd = ts_config.command.split()

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120
        )

        output = result.stdout + result.stderr

        if result.returncode == 0:
            return "✅ TypeScript check PASSED"
        else:
            error_lines = [line for line in output.split('\n') if 'error TS' in line]
            error_summary = '\n'.join(error_lines[:10])
            return f"❌ TypeScript check FAILED:\n{error_summary}"

    except subprocess.TimeoutExpired:
        return "❌ TIMEOUT: TypeScript check took too long (>120s)"
    except FileNotFoundError as e:
        return f"❌ ERROR: Command not found. Check your config: {e}"
    except Exception as e:
        return f"❌ ERROR: {str(e)}"


def run_eslint() -> str:
    """
    執行 ESLint 檢查

    封裝價值：從 config 讀取命令、自動 timeout、warning vs error 判斷
    """
    config = _get_config()
    project_root = config.get_project_root()

    try:
        eslint_config = config.quality_checks.eslint
        if not eslint_config.enabled:
            return "ℹ️  ESLint check is disabled in config"

        cmd = eslint_config.command.split()

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120
        )

        output = result.stdout + result.stderr

        if "error" not in output.lower() or result.returncode == 0:
            warning_count = output.lower().count('warning')
            return f"✅ ESLint check PASSED ({warning_count} warnings)"
        else:
            error_lines = [line for line in output.split('\n') if 'error' in line.lower()]
            error_summary = '\n'.join(error_lines[:10])
            return f"❌ ESLint check FAILED:\n{error_summary}"

    except subprocess.TimeoutExpired:
        return "❌ TIMEOUT: ESLint check took too long (>120s)"
    except Exception as e:
        return f"❌ ERROR: {str(e)}"


# ==========================================
# 行為驗證工具（Playwright）
# ==========================================

def run_behavior_validation(scenario_json: str) -> str:
    """
    執行 Playwright 行為驗證

    由 bugfix-test LLM 呼叫：LLM 設計測試場景（JSON），
    Python 端使用 Playwright 實際執行並回傳結果。

    Args:
        scenario_json: JSON 字串，格式：
            {
              "url_path": "/path",
              "actions": [...],
              "assertions": [...]
            }

    Returns:
        驗證結果摘要字串（PASS / FAIL / SKIPPED + 場景細節）

    封裝價值：
    - 從 config 取得 port / workspace / headless / dev_command
    - 在獨立執行緒開新 event loop 跑 async Playwright（避免干擾主 loop）
    - 格式化回傳結果給 LLM 繼續使用
    """
    config = _get_config()
    bv_config = config.behavior_validation

    if not bv_config.enabled:
        return "⏭️  行為驗證已停用（behavior_validation.enabled: false）"

    # 解析 scenario JSON
    try:
        scenario_data = json.loads(scenario_json)
    except json.JSONDecodeError as e:
        return f"❌ 無效的 scenario JSON: {e}"

    issue_id = scenario_data.get("name", "unknown")
    project_root = config.get_project_root()

    # 從 config.dev_server 取得啟動命令
    dev_command = None
    if config.dev_server and config.dev_server.get("command"):
        raw_cmd = config.dev_server["command"]
        dev_command = raw_cmd.split() if isinstance(raw_cmd, str) else raw_cmd

    # 在新執行緒開獨立 event loop 跑 async Playwright
    # （不能在現有 loop 中呼叫 asyncio.run()，因此用 thread 隔離）
    result_holder: dict = {}

    def _run_in_thread():
        from .behavior_validation import BehaviorValidator
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            validator = BehaviorValidator(
                project_root=project_root,
                port=bv_config.port,
                workspace=bv_config.workspace,
                headless=bv_config.headless,
                dev_command=dev_command,
                channel=bv_config.channel,
            )
            report = loop.run_until_complete(
                validator.validate(issue_id, dynamic_scenario=scenario_data)
            )
            result_holder["report"] = report
        except Exception as e:
            result_holder["error"] = str(e)
        finally:
            loop.close()

    thread = threading.Thread(target=_run_in_thread)
    thread.start()
    thread.join(timeout=300)

    if not thread.is_alive() is False:
        return "❌ 行為驗證執行超時（>300s）"

    if "error" in result_holder:
        return f"❌ 行為驗證發生錯誤: {result_holder['error']}"

    report = result_holder.get("report")
    if not report:
        return "❌ 行為驗證未回傳結果"

    # 格式化輸出給 LLM
    verdict_icon = "✅" if report.verdict == "PASS" else ("⏭️" if report.verdict == "SKIPPED" else "❌")
    lines = [
        f"{verdict_icon} 行為驗證: {report.verdict}",
        f"   通過場景: {report.scenarios_passed}/{report.scenarios_run}",
    ]
    for r in report.results:
        icon = "✅" if r.passed else "❌"
        lines.append(f"   {icon} {r.name} ({r.duration_seconds:.1f}s)")
        if not r.passed and r.error:
            lines.append(f"      錯誤: {r.error}")
        if r.console_errors:
            lines.append(f"      Console errors ({len(r.console_errors)}):")
            for ce in r.console_errors[:5]:
                lines.append(f"        [{ce['type']}] {ce['text'][:200]}")
        if r.screenshots:
            lines.append(f"      截圖: {', '.join(r.screenshots)}")

    return "\n".join(lines)


# ==========================================
# 技術債記錄工具（業務邏輯，非通用工具）
# ==========================================

def record_tech_debt(issue_id: str, missing_tests: List[str], reason: str) -> str:
    """
    記錄技術債到 JSON 檔案

    用於追蹤缺少測試的模組
    """
    try:
        debt_file = Path("tech_debt.json")

        if debt_file.exists():
            with open(debt_file, 'r', encoding='utf-8') as f:
                debts = json.load(f)
        else:
            debts = []

        new_debt = {
            "issue_id": issue_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "missing_tests": missing_tests,
            "reason": reason
        }

        debts.append(new_debt)

        with open(debt_file, 'w', encoding='utf-8') as f:
            json.dump(debts, f, indent=2, ensure_ascii=False)

        return f"✅ Tech debt recorded for {issue_id} ({len(missing_tests)} items)"

    except Exception as e:
        return f"❌ Error recording tech debt: {str(e)}"


# ==========================================
# 工具映射表（僅自訂工具，SDK 內建工具不需要列入）
# ==========================================

TOOL_MAP = {
    "run_typescript_check": run_typescript_check,
    "run_eslint": run_eslint,
    "run_behavior_validation": run_behavior_validation,
    "record_tech_debt": record_tech_debt,
}
