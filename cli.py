#!/usr/bin/env python3
"""
Agent Fix CLI
通用化 AI Bug 修復工作流程的命令列工具

Commands:
  init        - 初始化專案配置
  validate    - 驗證配置檔案
  check-deps  - 檢查依賴套件
  run         - 執行 Bug 修復流程
"""
import sys
import argparse
from pathlib import Path
from typing import Optional
import shutil
import re


def create_parser() -> argparse.ArgumentParser:
    """建立命令列參數解析器"""
    parser = argparse.ArgumentParser(
        prog="agent-fix",
        description="通用化 AI Bug 修復工作流程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用指令")
    
    # init 命令
    init_parser = subparsers.add_parser(
        "init",
        help="自動偵測目標專案並生成 config.yaml"
    )
    init_parser.add_argument(
        "project_path",
        help="目標專案根目錄路徑 (例如: /path/to/my-app)"
    )
    init_parser.add_argument(
        "--issue-prefix",
        default="BUG",
        help="Issue ID 前綴 (預設: BUG)"
    )
    init_parser.add_argument(
        "--output",
        "-o",
        default="./config.yaml",
        help="輸出配置檔案路徑 (預設: ./config.yaml)"
    )
    
    # validate 命令
    validate_parser = subparsers.add_parser(
        "validate",
        help="驗證配置檔案"
    )
    validate_parser.add_argument(
        "config_file",
        help="配置檔案路徑"
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="嚴格模式：將警告視為錯誤"
    )
    
    # check-deps 命令
    deps_parser = subparsers.add_parser(
        "check-deps",
        help="檢查依賴套件"
    )
    deps_parser.add_argument(
        "--fix",
        action="store_true",
        help="自動安裝缺少的依賴"
    )
    
    # run 命令
    run_parser = subparsers.add_parser(
        "run",
        help="執行 Bug 修復流程"
    )
    run_parser.add_argument(
        "issue_id",
        help="Issue ID (例如: BUG-001)"
    )
    run_parser.add_argument(
        "--config",
        "-c",
        help="配置檔案路徑 (預設: 從 PROJECT_CONFIG 環境變數讀取)"
    )

    # batch 命令
    batch_parser = subparsers.add_parser(
        "batch",
        help="批次執行所有 Issue（從 issue_source 讀取清單）"
    )
    batch_parser.add_argument(
        "--config",
        "-c",
        help="配置檔案路徑 (預設: 從 PROJECT_CONFIG 環境變數讀取)"
    )
    batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="列出將執行的 Issue ID，但不實際執行"
    )
    batch_parser.add_argument(
        "--filter",
        "-f",
        metavar="PATTERN",
        help="以 glob pattern 篩選 Issue ID (例如: BUG-*)"
    )
    batch_parser.add_argument(
        "--limit",
        "-n",
        type=int,
        metavar="N",
        help="只執行前 N 個 Issue（測試用）"
    )
    batch_parser.add_argument(
        "--inspect",
        metavar="ISSUE_ID",
        nargs="?",
        const="__first__",
        help="印出 issue 的完整 raw JSON（供欄位比對用）。不指定 ID 則取第一筆"
    )

    return parser


def _interactive_setup(output_path: Path) -> None:
    """LLM 生成 yaml 後，互動式引導補齊三個無法自動偵測的設定。"""
    import yaml

    print("\n" + "─" * 50)
    print("⚙️  專案設定引導（按 Enter 使用預設值）")
    print("─" * 50)

    with open(output_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # ── 1. Issue 來源 ──────────────────────────────
    current_type = config.get("issue_source", {}).get("type", "local_json")
    answer = input(f"\n? Issue 來源 (jira/local_json/google_sheets) [{current_type}]: ").strip().lower()
    issue_type = answer if answer in ("jira", "local_json", "google_sheets") else current_type

    if "issue_source" not in config:
        config["issue_source"] = {}
    config["issue_source"]["type"] = issue_type

    if issue_type == "jira":
        config["issue_source"]["options"] = _setup_jira(
            config.get("issue_source", {}).get("options", {})
        )
        _check_jira_env()

    if issue_type == "google_sheets":
        config["issue_source"]["options"] = _setup_google_sheets(
            config.get("issue_source", {}).get("options", {})
        )

    # ── 2. Playwright 行為驗證 ─────────────────────
    current_bv = config.get("behavior_validation", {}).get("enabled", False)
    default_bv = "y" if current_bv else "n"
    answer = input(f"\n? 啟用 Playwright 行為驗證 (y/n) [{default_bv}]: ").strip().lower()
    bv_enabled = (answer == "y") if answer in ("y", "n") else current_bv

    if "behavior_validation" not in config:
        config["behavior_validation"] = {}
    config["behavior_validation"]["enabled"] = bv_enabled

    # ── 3. Chrome DevTools MCP ─────────────────────
    current_mcp = config.get("mcp_servers", {}).get("chrome-devtools", {}).get("enabled", False)
    default_mcp = "y" if current_mcp else "n"
    answer = input(f"\n? 啟用 Chrome DevTools MCP (y/n) [{default_mcp}]: ").strip().lower()
    mcp_enabled = (answer == "y") if answer in ("y", "n") else current_mcp

    if "mcp_servers" not in config:
        config["mcp_servers"] = {}
    if "chrome-devtools" not in config["mcp_servers"]:
        config["mcp_servers"]["chrome-devtools"] = {
            "command": "npx",
            "args": ["-y", "chrome-devtools-mcp@latest"],
        }
    config["mcp_servers"]["chrome-devtools"]["enabled"] = mcp_enabled

    # ── 寫回 yaml ──────────────────────────────────
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    print(f"\n✅ 設定已更新: {output_path}")


def _setup_jira(current_opts: dict) -> dict:
    """互動式設定 Jira 來源，設定 jql_base（可跳過）。"""
    print("\n  🎯 Jira 設定（直接按 Enter 跳過，之後再補填）")

    current_jql = current_opts.get("jql_base", "")
    jql = input(f"  ? jql_base JQL [{current_jql or '留空跳過'}]: ").strip()
    jql_base = jql or current_jql

    opts: dict = {}
    if jql_base:
        opts["jql_base"] = jql_base
    else:
        print("\n  ⚠️  尚未設定 jql_base，請之後在 config.yaml 補填：")
        print("       issue_source:")
        print("         type: jira")
        print("         options:")
        print('           jql_base: "project = PROJ AND assignee = currentUser() AND status = \'To Do\'"')

    print("\n  ℹ️  Jira 認證需在 .env 設定（公司層級，設定一次即可）：")
    print("     JIRA_BASE_URL=https://your-company.atlassian.net")
    print("     JIRA_USER_EMAIL=your@email.com")
    print("     JIRA_API_TOKEN=...  # https://id.atlassian.com/manage-profile/security/api-tokens")

    return opts


def _check_jira_env() -> None:
    """檢查 JIRA 環境變數是否已設定，若無則提示。"""
    import os
    from pathlib import Path

    # 嘗試讀取 .env
    env_file = Path(".env")
    env_content = env_file.read_text() if env_file.exists() else ""

    required = ["JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN"]
    missing = [k for k in required if not os.getenv(k) and k not in env_content]

    if missing:
        print("\n  ⚠️  請在 .env 設定以下 Jira 環境變數（公司層級，設定一次即可）：")
        for k in missing:
            print(f"     {k}=...")
    else:
        print("\n  ✅ Jira 環境變數已設定")


def _setup_google_sheets(current_opts: dict) -> dict:
    """互動式設定 Google Sheets 來源，允許跳過（之後在 config.yaml 補填）。"""
    from pathlib import Path

    print("\n  📊 Google Sheets 設定（直接按 Enter 跳過，之後再補填）")

    # ── sheet_url ──────────────────────────────────
    current_url = current_opts.get("sheet_url", "")
    url = input(f"  ? Sheet URL [{current_url or '留空跳過'}]: ").strip()
    sheet_url = url or current_url

    # ── 認證方式 ───────────────────────────────────
    current_creds = current_opts.get("credentials_file", "")
    creds = input(f"  ? Service account JSON 路徑 [{current_creds or '留空跳過'}]: ").strip()
    credentials_file = creds or current_creds or None

    opts: dict = {}
    if sheet_url:
        opts["sheet_url"] = sheet_url
    else:
        opts["sheet_url"] = ""
        print("\n  ⚠️  尚未設定 Sheet URL，請之後在 config.yaml 補填：")
        print("       issue_source:")
        print("         type: google_sheets")
        print("         options:")
        print("           sheet_url: \"https://docs.google.com/spreadsheets/d/...\"")

    if credentials_file:
        opts["credentials_file"] = credentials_file
    else:
        print("\n  ℹ️  認證方式（擇一設定）：")
        print("     · Service account：在 config.yaml 填入 credentials_file 路徑")
        print("     · API key（公開試算表）：export GOOGLE_API_KEY=AIza...")

    # ── 試算表欄位提示 ─────────────────────────────
    template_path = Path(__file__).parent / "issues" / "SHEETS_TEMPLATE.csv"
    print("\n  📋 試算表欄位範本：")
    if template_path.exists():
        print(f"     {template_path}")
        print("     Google Sheets → 檔案 → 匯入 → 上傳此 CSV 即可建立欄位")
    else:
        print("     必要欄位：issue_id, summary, module, description,")
        print("               reproduction_steps, expected, actual")
        print("     reproduction_steps 使用換行（\\n）分隔多個步驟")

    return opts


def _print_chrome_setup_hint(config_path: Path) -> None:
    """若 chrome-devtools MCP 已啟用，印出一次性登入設定提示。"""
    import yaml

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception:
        return

    mcp = config.get("mcp_servers", {}).get("chrome-devtools", {})
    if not mcp.get("enabled", False):
        return

    pre_launch = mcp.get(
        "pre_launch",
        "open -na 'Google Chrome' --args --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug"
    )

    print()
    print("─" * 50)
    print("🌐 Chrome DevTools MCP 已啟用 — 首次使用前請完成登入設定")
    print("─" * 50)
    print()
    print("  請依序執行以下步驟（一次性設定）：")
    print()
    print("  1. 開啟 Chrome（帶 remote debugging）：")
    print(f"     {pre_launch}")
    print()
    print("  2. 在開啟的 Chrome 中登入目標專案帳號")
    print()
    print("  3. 關閉 Chrome")
    print()
    print("  ✅ 完成後登入狀態會保留，之後執行 batch 時自動沿用。")
    print("     ⚠️  重開機後 /tmp/chrome-debug 會被清除，需重新執行上述步驟。")
    print("─" * 50)


def command_init(args) -> int:
    """智慧初始化：用 LLM agent 探索專案，自動生成 config.yaml"""
    import asyncio

    project_path = Path(args.project_path).resolve()
    if not project_path.exists():
        print(f"❌ 錯誤：專案路徑不存在: {project_path}")
        return 1
    if not project_path.is_dir():
        print(f"❌ 錯誤：路徑不是目錄: {project_path}")
        return 1

    output_path = Path(args.output).resolve()

    try:
        from engine.workflow import run_init_workflow
        asyncio.run(run_init_workflow(
            project_path=str(project_path),
            output_path=str(output_path),
            issue_prefix=args.issue_prefix.upper(),
        ))

        _interactive_setup(output_path)
        _print_chrome_setup_hint(output_path)

        print()
        print("📝 下一步：")
        print(f"   1. 驗證配置: agent-fix validate {output_path}")
        print(f"   2. 設定環境變數: export PROJECT_CONFIG={output_path}")
        print(f"   3. 執行修復: agent-fix run <issue-id> --config {output_path}")
        return 0
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


def command_validate(args) -> int:
    """驗證配置檔案"""
    from engine.config import ProjectConfig, ConfigurationError
    
    print("🔍 驗證配置檔案...\n")
    
    config_file = Path(args.config_file)
    if not config_file.exists():
        print(f"❌ 錯誤：配置檔案不存在: {config_file}")
        return 1
    
    try:
        # 載入配置
        config = ProjectConfig.from_yaml(str(config_file))
        
        print(f"✅ 配置檔案語法正確")
        print()
        print(f"📋 配置摘要:")
        print(f"  專案名稱: {config.project_name}")
        print(f"  框架: {config.framework}")
        print(f"  專案根目錄: {config.get_project_root()}")
        print(f"  Issue 前綴: {config.issue_prefix}")
        
        if config.monorepo:
            print(f"  Monorepo: 是")
            print(f"    主 workspace: {config.monorepo.main_workspace}")
            if config.monorepo.tool:
                print(f"    工具: {config.monorepo.tool}")
        else:
            print(f"  Monorepo: 否")
        
        print()
        
        # 驗證專案結構
        warnings = config.validate_project_structure()
        
        if warnings:
            print(f"⚠️  發現 {len(warnings)} 個警告：")
            for i, warning in enumerate(warnings, 1):
                print(f"  {i}. {warning}")
            print()
            
            if args.strict:
                print("❌ 嚴格模式：有警告視為失敗")
                return 1
        
        print("✅ 配置驗證通過")
        return 0
        
    except ConfigurationError as e:
        print(f"❌ 配置錯誤: {e}")
        return 1
    except Exception as e:
        print(f"❌ 未預期的錯誤: {e}")
        import traceback
        traceback.print_exc()
        return 1


def command_check_deps(args) -> int:
    """檢查依賴套件"""
    import importlib.util
    import os

    print("🔍 檢查依賴套件...\n")

    sdk = os.getenv("SDK_ADAPTER", "copilot")
    _sdk_pkg_map = {
        "copilot": ("copilot",    "GitHub Copilot SDK"),
        "claude":  ("anthropic",  "Anthropic Claude SDK"),
        "openai":  ("agents",     "OpenAI Agents SDK"),
    }
    sdk_pkg, sdk_label = _sdk_pkg_map.get(sdk, _sdk_pkg_map["copilot"])

    required_packages = {
        'pydantic':  'Pydantic (配置驗證)',
        'yaml':      'PyYAML (YAML 解析)',
        sdk_pkg:     f'{sdk_label} (Agent 執行，SDK_ADAPTER={sdk})',
        'playwright': 'Playwright (瀏覽器測試)',
    }
    
    missing = []
    installed = []
    
    for package, description in required_packages.items():
        spec = importlib.util.find_spec(package)
        if spec is None:
            missing.append((package, description))
            print(f"  ❌ {package:20} - {description}")
        else:
            installed.append((package, description))
            print(f"  ✅ {package:20} - {description}")
    
    print()
    print(f"📊 統計: {len(installed)}/{len(required_packages)} 已安裝")
    
    if missing:
        print(f"\n⚠️  缺少 {len(missing)} 個依賴套件")
        
        if args.fix:
            print("\n🔧 自動安裝缺少的依賴...")
            import subprocess
            
            _install_name = {"yaml": "PyYAML", "copilot": "github-copilot-sdk", "agents": "openai-agents"}
            packages_to_install = [_install_name.get(pkg, pkg) for pkg, _ in missing]
            
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', *packages_to_install
                ])
                print("\n✅ 依賴套件安裝完成")
                return 0
            except subprocess.CalledProcessError as e:
                print(f"\n❌ 安裝失敗: {e}")
                return 1
        else:
            print("\n💡 提示：使用 --fix 選項自動安裝")
            print(f"   或手動安裝: pip install {' '.join([pkg for pkg, _ in missing])}")
            return 1
    
    print("\n✅ 所有依賴套件已安裝")
    return 0


def command_batch(args) -> int:
    """批次執行所有 Issue"""
    import os
    import asyncio
    import fnmatch

    if args.config:
        os.environ['PROJECT_CONFIG'] = args.config

    if 'PROJECT_CONFIG' not in os.environ:
        print("❌ 錯誤：未設定 PROJECT_CONFIG 環境變數")
        print("\n請設定配置檔案路徑：")
        print("  export PROJECT_CONFIG=./config.yaml")
        print("或使用 --config 選項：")
        print("  agent-fix batch --config ./config.yaml")
        return 1

    try:
        from engine.config import ProjectConfig
        from engine.issue_source import create_adapter

        config = ProjectConfig.from_yaml(os.environ['PROJECT_CONFIG'])
        adapter = create_adapter(config.issue_source)
        adapter.validate()

        is_jira = config.issue_source.type == "jira"

        # Jira: --filter 作為 JQL 傳入 list_all()，由 adapter 串接
        # 其他:  list_all() 回傳全部，再用 fnmatch 篩選
        issue_ids = adapter.list_all(filter=args.filter if is_jira else None)

        if not issue_ids:
            print("⚠️  沒有找到任何 Issue")
            return 0

        # 非 Jira：套用 fnmatch --filter
        if args.filter and not is_jira:
            issue_ids = [i for i in issue_ids if fnmatch.fnmatch(i, args.filter)]
            if not issue_ids:
                print(f"⚠️  沒有符合 '{args.filter}' 的 Issue")
                return 0

        if args.limit and args.limit > 0:
            issue_ids = issue_ids[:args.limit]

        print(f"\n📋 共 {len(issue_ids)} 個 Issue：")
        for i, issue_id in enumerate(issue_ids, 1):
            print(f"  {i:3}. {issue_id}")

        if args.inspect:
            target = args.inspect if args.inspect != "__first__" else issue_ids[0]
            print(f"\n🔎 Fetching raw response for {target} ...")
            raw = adapter.fetch(target)
            import json as _json
            print(_json.dumps(raw, ensure_ascii=False, indent=2))
            return 0

        if args.dry_run:
            print("\n(dry-run 模式，不實際執行)")
            return 0

        print()
        from engine.workflow import run_batch_workflow
        asyncio.run(run_batch_workflow(issue_ids))
        return 0

    except Exception as e:
        print(f"❌ 批次執行失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


def command_run(args) -> int:
    """執行 Bug 修復流程"""
    import os
    import asyncio
    
    # 設定配置檔案
    if args.config:
        os.environ['PROJECT_CONFIG'] = args.config
    
    # 檢查環境變數
    if 'PROJECT_CONFIG' not in os.environ:
        print("❌ 錯誤：未設定 PROJECT_CONFIG 環境變數")
        print("\n請設定配置檔案路徑：")
        print("  export PROJECT_CONFIG=./config.yaml")
        print("或使用 --config 選項：")
        print(f"  agent-fix run {args.issue_id} --config ./config.yaml")
        return 1
    
    # 導入並執行 workflow
    try:
        from engine.workflow import run_workflow
        asyncio.run(run_workflow(args.issue_id))
        return 0
    except FileNotFoundError as e:
        print(f"❌ 錯誤: {e}")
        return 1
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """主程式入口"""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # 執行對應命令
    if args.command == "init":
        return command_init(args)
    elif args.command == "validate":
        return command_validate(args)
    elif args.command == "check-deps":
        return command_check_deps(args)
    elif args.command == "run":
        return command_run(args)
    elif args.command == "batch":
        return command_batch(args)
    else:
        print(f"❌ 未知命令: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
