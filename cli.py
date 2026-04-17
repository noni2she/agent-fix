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
    
    return parser


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
        print()
        print("📝 下一步：")
        print(f"   1. 確認配置檔案: {output_path}")
        print(f"   2. 驗證配置: agent-fix validate {output_path}")
        print(f"   3. 設定環境變數: export PROJECT_CONFIG={output_path}")
        print(f"   4. 執行修復: agent-fix run <issue-id> --config {output_path}")
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
    
    print("🔍 檢查依賴套件...\n")
    
    required_packages = {
        'pydantic': 'Pydantic (配置驗證)',
        'yaml': 'PyYAML (YAML 解析)',
        'copilot': 'GitHub Copilot SDK (Agent 執行)',
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
            
            packages_to_install = [pkg for pkg, _ in missing]
            # 特殊處理 yaml -> PyYAML
            packages_to_install = [
                'PyYAML' if pkg == 'yaml' else pkg 
                for pkg in packages_to_install
            ]
            
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
    else:
        print(f"❌ 未知命令: {args.command}")
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
