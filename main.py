#!/usr/bin/env python3
"""
Agent Fix v3.1 — Entry Point (向後相容)

建議使用 CLI 方式執行：
  agent-fix run <issue-id>
  afix run <issue-id>

直接執行（需先設定 PROJECT_CONFIG）：
  export PROJECT_CONFIG=./config/my-project.yaml
  python main.py <issue-id>
"""
import sys
import asyncio
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方式: python main.py <issue_id>")
        print("範例: python main.py BUG-001")
        print()
        print("或使用 CLI：")
        print("  agent-fix run BUG-001 --config ./config/my-project.yaml")
        sys.exit(1)

    from engine.workflow import run_workflow
    asyncio.run(run_workflow(sys.argv[1]))
