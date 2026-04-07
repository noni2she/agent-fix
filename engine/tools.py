"""
自訂工具函式庫（僅保留 SDK 未內建的業務邏輯工具）

Copilot SDK 已內建以下工具，不需要自訂：
- execute (shell/Bash): 任意 shell 指令（含 git 操作）
- read (Read): 讀取檔案
- edit (Edit/Write): 編輯/寫入檔案
- search (Grep/Glob): 文字搜尋 + 檔案搜尋

本檔案僅保留有封裝價值的業務邏輯工具。
"""
import subprocess
import json
import datetime
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
    "record_tech_debt": record_tech_debt,
}
