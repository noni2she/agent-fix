"""
自訂工具函式庫

Copilot SDK 已內建以下工具，不需要自訂：
- execute (shell/Bash): 任意 shell 指令（含 git 操作）
- read (Read): 讀取檔案
- edit (Edit/Write): 編輯/寫入檔案
- search (Grep/Glob): 文字搜尋 + 檔案搜尋

本檔案提供：
1. 業務邏輯工具（品質檢查、行為驗證、技術債）
2. 檔案系統工具（供 Claude/OpenAI adapter 使用，Copilot 已內建）
"""
import asyncio
import fnmatch
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
# 檔案系統工具（Claude/OpenAI adapter 使用；Copilot SDK 已內建）
# ==========================================

_MAX_FILE_SIZE = 100 * 1024  # 100KB 讀取上限


def read_file(path: str) -> str:
    """
    讀取指定路徑的檔案內容

    Args:
        path: 檔案路徑（絕對或相對路徑）

    Returns:
        檔案內容字串，或錯誤訊息
    """
    try:
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            return f"❌ 檔案不存在: {path}"
        if not file_path.is_file():
            return f"❌ 路徑不是檔案: {path}"
        size = file_path.stat().st_size
        if size > _MAX_FILE_SIZE:
            return f"❌ 檔案過大 ({size} bytes)，上限 {_MAX_FILE_SIZE} bytes: {path}"
        return file_path.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"❌ 無讀取權限: {path}"
    except Exception as e:
        return f"❌ 讀取失敗: {e}"


def list_directory(path: str) -> str:
    """
    列出指定目錄內容

    Args:
        path: 目錄路徑（絕對或相對路徑）

    Returns:
        目錄內容列表字串（含 [DIR] / [FILE] 標示），或錯誤訊息
    """
    try:
        dir_path = Path(path).expanduser().resolve()
        if not dir_path.exists():
            return f"❌ 路徑不存在: {path}"
        if not dir_path.is_dir():
            return f"❌ 路徑不是目錄: {path}"

        entries = []
        for entry in sorted(dir_path.iterdir()):
            tag = "[DIR] " if entry.is_dir() else "[FILE]"
            entries.append(f"{tag} {entry.name}")

        if not entries:
            return f"（空目錄）{path}"
        return "\n".join(entries)
    except PermissionError:
        return f"❌ 無讀取權限: {path}"
    except Exception as e:
        return f"❌ 列出目錄失敗: {e}"


def search_files(pattern: str, directory: str = ".", file_glob: str = "*") -> str:
    """
    在目錄中搜尋包含指定 pattern 的行

    Args:
        pattern:    搜尋字串（支援 regex）
        directory:  搜尋根目錄（預設當前目錄）
        file_glob:  只搜尋符合此 glob 的檔案（預設 *，例如 *.ts）

    Returns:
        搜尋結果（格式：檔案路徑:行號: 內容），或錯誤訊息
    """
    try:
        # 優先使用 ripgrep，其次 grep
        cmd = ["rg", "--line-number", "--glob", file_glob, pattern, directory]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode in (0, 1):  # 1 = no matches
            output = result.stdout.strip()
            if not output:
                return f"（無符合結果）pattern={pattern}, dir={directory}"
            lines = output.split("\n")
            if len(lines) > 50:
                lines = lines[:50]
                lines.append(f"... (截斷，顯示前 50 筆)")
            return "\n".join(lines)
    except FileNotFoundError:
        pass  # rg 不存在，fallback 到 grep
    except subprocess.TimeoutExpired:
        return "❌ 搜尋超時"

    try:
        cmd = ["grep", "-rn", "--include", file_glob, pattern, directory]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if not output:
            return f"（無符合結果）pattern={pattern}, dir={directory}"
        lines = output.split("\n")
        if len(lines) > 50:
            lines = lines[:50]
            lines.append(f"... (截斷，顯示前 50 筆)")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "❌ 搜尋超時"
    except Exception as e:
        return f"❌ 搜尋失敗: {e}"


def write_file(path: str, content: str) -> str:
    """
    寫入（或建立）檔案

    Args:
        path:    檔案路徑（絕對或相對路徑）
        content: 檔案內容

    Returns:
        成功或錯誤訊息
    """
    try:
        file_path = Path(path).expanduser().resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"✅ 已寫入: {file_path} ({len(content)} bytes)"
    except PermissionError:
        return f"❌ 無寫入權限: {path}"
    except Exception as e:
        return f"❌ 寫入失敗: {e}"


# ==========================================
# 工具映射表
# ==========================================

TOOL_MAP = {
    # 業務邏輯工具
    "run_typescript_check": run_typescript_check,
    "run_eslint": run_eslint,
    "run_behavior_validation": run_behavior_validation,
    "record_tech_debt": record_tech_debt,
    # 檔案系統工具（Claude/OpenAI adapter 用）
    "read_file": read_file,
    "list_directory": list_directory,
    "search_files": search_files,
    "write_file": write_file,
}
