"""
通用工具函式庫
支援配置驅動的檔案操作、搜尋、品質檢查等工具

重構亮點：
- 移除所有硬編碼路徑和 workspace 名稱
- 從 ProjectConfig 讀取所有配置
- 支援不同專案結構
"""
import os
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
# 基礎檔案操作工具
# ==========================================

def list_files(directory: str = ".") -> str:
    """列出目錄下的檔案和資料夾"""
    try:
        items = []
        for item in os.listdir(directory):
            if item.startswith('.'): 
                continue
            full_path = os.path.join(directory, item)
            if os.path.isdir(full_path):
                items.append(f"📁 {item}/")
            else:
                items.append(f"📄 {item}")
        return "\n".join(items) if items else "Empty directory"
    except Exception as e: 
        return f"Error: {str(e)}"

def read_file(filepath: str) -> str:
    """讀取檔案內容"""
    try:
        if not os.path.exists(filepath):
            return f"Error: File not found - {filepath}"
        
        with open(filepath, "r", encoding='utf-8') as f:
            content = f.read()
        
        # 加上行號方便定位
        lines = content.split('\n')
        numbered_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered_lines)
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filepath: str, content: str) -> str:
    """寫入檔案 (覆蓋)"""
    try:
        # 確保目錄存在
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        
        with open(filepath, "w", encoding='utf-8') as f:
            f.write(content)
        
        return f"✅ Successfully wrote to {filepath} ({len(content)} chars)"
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================================
# 搜尋與分析工具
# ==========================================

def grep_search(keyword: str, include_pattern: str = "**/*.{ts,tsx,js,jsx}") -> str:
    """
    搜尋檔案內容
    
    Args:
        keyword: 要搜尋的關鍵字
        include_pattern: 檔案過濾模式 (預設: TypeScript/JavaScript 檔案)
    """
    config = _get_config()
    project_root = config.get_project_root()
    
    # 建立搜尋目錄列表
    search_dirs = []
    
    # 加入所有配置的路徑
    if config.paths.shared_packages:
        search_dirs.extend([str(project_root / p) for p in config.paths.shared_packages])
    if config.paths.shared_components:
        search_dirs.extend([str(project_root / p) for p in config.paths.shared_components])
    if config.paths.isolated_modules:
        search_dirs.extend([str(project_root / p) for p in config.paths.isolated_modules])
    if config.paths.domain_logic:
        search_dirs.extend([str(project_root / p) for p in config.paths.domain_logic])
    
    # 如果沒有配置路徑，搜尋整個專案
    if not search_dirs:
        search_dirs = [str(project_root)]
    
    results = []
    
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
            
        for root, _, files in os.walk(search_dir):
            # 排除常見的忽略目錄
            if any(ignore in root for ignore in ['.git', 'node_modules', '.next', 'dist', '.turbo', 'build']):
                continue
            
            for file in files:
                # 只搜尋指定類型的檔案
                if not file.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    continue
                
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if keyword.lower() in content.lower():
                            # 找出包含關鍵字的行號
                            lines = content.split('\n')
                            matching_lines = [
                                (i+1, line.strip()) 
                                for i, line in enumerate(lines) 
                                if keyword.lower() in line.lower()
                            ]
                            
                            # 相對路徑顯示
                            rel_path = os.path.relpath(path, project_root)
                            results.append(f"\n📄 {rel_path}")
                            for line_num, line_content in matching_lines[:3]:  # 只顯示前3行
                                results.append(f"  L{line_num}: {line_content[:100]}")
                except:
                    continue
    
    if not results:
        return f"No matches found for '{keyword}'"
    
    return "\n".join(results[:50])  # 限制結果數量

# ==========================================
# 品質檢查工具
# ==========================================

def run_typescript_check() -> str:
    """執行 TypeScript 編譯檢查"""
    config = _get_config()
    project_root = config.get_project_root()
    
    try:
        print(f"🔍 執行 TypeScript 檢查")
        
        # 從配置取得命令
        ts_config = config.quality_checks.typescript
        if not ts_config.enabled:
            return "ℹ️  TypeScript check is disabled in config"
        
        # 解析命令（支援 workspace 和直接命令）
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
            # 只返回錯誤摘要，避免輸出過長
            error_lines = [line for line in output.split('\n') if 'error TS' in line]
            error_summary = '\n'.join(error_lines[:10])  # 只顯示前10個錯誤
            return f"❌ TypeScript check FAILED:\n{error_summary}"
            
    except subprocess.TimeoutExpired:
        return "❌ TIMEOUT: TypeScript check took too long (>120s)"
    except FileNotFoundError as e:
        return f"❌ ERROR: Command not found. Check your config: {e}"
    except Exception as e:
        return f"❌ ERROR: {str(e)}"

def run_eslint() -> str:
    """執行 ESLint 檢查"""
    config = _get_config()
    project_root = config.get_project_root()
    
    try:
        print(f"🔍 執行 ESLint 檢查")
        
        # 從配置取得命令
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
        
        # ESLint 允許有 Warning，只要沒有 Error
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
# 技術債記錄工具
# ==========================================

def record_tech_debt(issue_id: str, missing_tests: List[str], reason: str) -> str:
    """
    記錄技術債到 JSON 檔案
    
    用於追蹤缺少測試的模組
    """
    try:
        debt_file = Path("tech_debt.json")
        
        # 讀取現有的技術債
        if debt_file.exists():
            with open(debt_file, 'r', encoding='utf-8') as f:
                debts = json.load(f)
        else:
            debts = []
        
        # 新增記錄
        new_debt = {
            "issue_id": issue_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "missing_tests": missing_tests,
            "reason": reason
        }
        
        debts.append(new_debt)
        
        # 寫回檔案
        with open(debt_file, 'w', encoding='utf-8') as f:
            json.dump(debts, f, indent=2, ensure_ascii=False)
        
        return f"✅ Tech debt recorded for {issue_id} ({len(missing_tests)} items)"
        
    except Exception as e:
        return f"❌ Error recording tech debt: {str(e)}"

# ==========================================
# Git 版本控管工具
# ==========================================

def git_status() -> str:
    """查看當前 Git 狀態"""
    config = _get_config()
    project_root = str(config.get_project_root())
    
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return f"❌ Git status failed: {result.stderr}"
        
        output = result.stdout.strip()
        if not output:
            return "✅ Working tree clean (no changes)"
        
        return f"📊 Git Status:\n{output}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def git_current_branch() -> str:
    """取得當前 Git 分支名稱"""
    config = _get_config()
    project_root = str(config.get_project_root())
    
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return f"❌ Failed to get branch: {result.stderr}"
        
        branch = result.stdout.strip()
        return f"🌿 Current branch: {branch}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def git_create_branch(branch_name: str, base_branch: str = "main") -> str:
    """
    建立並切換到新的 Git 分支
    
    Args:
        branch_name: 新分支名稱 (例: bugfix/BUG-001-button-issue)
        base_branch: 基礎分支 (預設: main)
        
    Returns:
        操作結果訊息
    """
    config = _get_config()
    project_root = str(config.get_project_root())
    
    try:
        # 確保在 base_branch 上
        subprocess.run(
            ["git", "checkout", base_branch],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # 拉取最新變更
        subprocess.run(
            ["git", "pull", "origin", base_branch],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # 建立新分支
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            # 如果分支已存在，嘗試切換
            if "already exists" in result.stderr:
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    return f"ℹ️  Switched to existing branch: {branch_name}"
            return f"❌ Failed to create branch: {result.stderr}"
        
        return f"✅ Created and switched to branch: {branch_name}"
    except subprocess.TimeoutExpired:
        return "❌ Git operation timed out"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def git_diff(filepath: str = "") -> str:
    """
    查看檔案差異
    
    Args:
        filepath: 檔案路徑 (為空則顯示所有變更)
        
    Returns:
        Git diff 輸出
    """
    config = _get_config()
    project_root = str(config.get_project_root())
    
    try:
        cmd = ["git", "diff"]
        if filepath:
            cmd.append(filepath)
        
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return f"❌ Git diff failed: {result.stderr}"
        
        output = result.stdout.strip()
        if not output:
            return "ℹ️  No changes to show"
        
        # 限制輸出長度
        lines = output.split('\n')
        if len(lines) > 100:
            output = '\n'.join(lines[:100]) + f"\n\n... (truncated {len(lines) - 100} lines)"
        
        return f"📝 Git Diff:\n{output}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def git_commit(message: str, files: List[str]) -> str:
    """
    建立 Git commit
    
    Args:
        message: Commit message (應遵循 Conventional Commits 格式)
        files: 要 commit 的檔案列表
        
    Returns:
        Commit 結果訊息，包含 commit SHA
        
    Example:
        git_commit(
            message="fix(search): resolve tab switch not triggering search\\n\\nReset isEndReached state when switching tabs.\\n\\nFixes BUG-001",
            files=["src/components/Search.tsx"]
        )
    """
    config = _get_config()
    project_root = str(config.get_project_root())
    
    try:
        # 先 add 檔案
        for file in files:
            result = subprocess.run(
                ["git", "add", file],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                return f"❌ Failed to add {file}: {result.stderr}"
        
        # 建立 commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return f"❌ Commit failed: {result.stderr}"
        
        # 取得 commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        commit_sha = sha_result.stdout.strip() if sha_result.returncode == 0 else "unknown"
        
        return f"✅ Committed successfully\nSHA: {commit_sha}\nFiles: {', '.join(files)}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ==========================================
# Shell 命令工具
# ==========================================

def run_command(command: str, cwd: str = None) -> str:
    """執行任意 shell 命令（用於 agent-browser 等 CLI 工具）"""
    config = _get_config()
    effective_cwd = cwd or str(config.get_project_root())
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=effective_cwd,
            capture_output=True,
            text=True,
            timeout=120
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return f"✅ Exit 0\n{output}" if output else "✅ Exit 0"
        else:
            return f"❌ Exit {result.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return "❌ TIMEOUT: Command took too long (>120s)"
    except Exception as e:
        return f"❌ ERROR: {str(e)}"


# ==========================================
# 工具映射表
# ==========================================

TOOL_MAP = {
    # 基礎檔案操作
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
    # 搜尋與分析
    "grep_search": grep_search,
    # 品質檢查
    "run_typescript_check": run_typescript_check,
    "run_eslint": run_eslint,
    # 技術債
    "record_tech_debt": record_tech_debt,
    # Shell 命令
    "run_command": run_command,
    # Git 版本控管工具
    "git_status": git_status,
    "git_current_branch": git_current_branch,
    "git_create_branch": git_create_branch,
    "git_diff": git_diff,
    "git_commit": git_commit,
}
