# bugfix-workflow/main.py
"""
Bugfix Workflow v3.1 — Skill-Based (Universal)

Skills 架構：
  - 通用 skills：bugfix-workflow/skills/（流程邏輯，不含專案細節）
  - 專案 context：由 config.yaml 動態生成，注入每個 phase prompt
  - 抽換 SDK：export SDK_ADAPTER=copilot|claude|openai

流程: bugfix-analyze → bugfix-implement → bugfix-test (retry ≤3)
Token 優化:
  - analyze + implement 共用 session（保留 file-read context）
  - test fork 新 session（獨立 context 省 token）
  - retry 回主 session（帶失敗回饋）
"""
import json
import asyncio
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

from engine import (
    ProjectConfig,
    ProjectSpec,
    load_config_from_env,
    ConfigurationError,
    init_agent_runner,
    init_tools,
)
from engine.skill_loader import load_skill
from engine.agent_runner import (
    create_session,
    run_in_session,
    setup_sdk_error_silencing,
    ANALYZE_IMPLEMENT_TOOLS,
    TEST_TOOLS,
)

load_dotenv()

# ==========================================
# 配置初始化
# ==========================================

try:
    print("\n" + "="*60)
    print("🚀 Bugfix Workflow v3.1 — Skill-Based")
    print("="*60)

    PROJECT_CONFIG = load_config_from_env()
    PROJECT_SPEC = ProjectSpec(PROJECT_CONFIG)
    PROJECT_ROOT = PROJECT_CONFIG.get_project_root()
    ISSUE_PREFIX = PROJECT_CONFIG.issue_prefix

    # 通用 skills 目錄（本地，流程邏輯）
    SKILLS_DIR = Path("skills").resolve()

    print(f"  ✅ Project: {PROJECT_CONFIG.project_name}")
    print(f"  ✅ Framework: {PROJECT_CONFIG.framework}")
    print(f"  ✅ Root: {PROJECT_ROOT}")
    print(f"  ✅ Skills: {SKILLS_DIR}")

    warnings = PROJECT_CONFIG.validate_project_structure()
    if warnings:
        print(f"\n  ⚠️  Warnings:")
        for w in warnings:
            print(f"     - {w}")

    init_tools(PROJECT_CONFIG)
    init_agent_runner(PROJECT_CONFIG, PROJECT_SPEC)
    print("="*60 + "\n")

except ConfigurationError as e:
    print(f"\n❌ Configuration Error: {e}\n")
    print("Set PROJECT_CONFIG environment variable:")
    print("  export PROJECT_CONFIG=./config/your-project.yaml\n")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Initialization Error: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

ISSUES_DIR = Path("issues/sources")
REPORT_DIR = Path("issues/reports")
ISSUES_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# Project Context 生成（從 config.yaml 動態生成）
# ==========================================

def load_project_context() -> str:
    """
    從 ProjectConfig 動態生成專案 context，注入每個 phase prompt 開頭。

    bugfix-workflow（通用版）以 config.yaml 驅動，
    不依賴固定的 morse-project-context SKILL.md。
    """
    cfg = PROJECT_CONFIG

    # 指令區塊
    ts_cmd = cfg.quality_checks.typescript.command
    lint_cmd = cfg.quality_checks.eslint.command
    test_cmd = cfg.quality_checks.tests.command if cfg.quality_checks.tests else None
    dev_cmd = cfg.dev_server.get("command") if cfg.dev_server else None
    dev_port = cfg.dev_server.get("port", 3000) if cfg.dev_server else 3000

    monorepo_info = (
        f"- Monorepo: {cfg.monorepo.tool} (workspace: {cfg.monorepo.main_workspace})"
        if cfg.monorepo else "- Single project"
    )

    # TACTICAL 判斷條件
    tactical_rows = []
    for p in cfg.paths.shared_packages:
        tactical_rows.append(f"| Path in `{p}` | **TACTICAL** | Shared package |")
    for p in cfg.paths.shared_components:
        tactical_rows.append(f"| Path in `{p}`, no customization props | **TACTICAL** | Shared component |")
    for k in cfg.high_risk_keywords:
        tactical_rows.append(f"| Path contains `{k}` | **TACTICAL** | High-risk module |")
    tactical_rows.append("| Other | **DIRECT** | Isolated module |")
    tactical_table = "\n".join(tactical_rows)

    return f"""## Project Context

**Project**: {cfg.project_name} ({cfg.framework})
**Root**: {PROJECT_ROOT}

### Commands

```bash
# TypeScript check
{ts_cmd}

# ESLint
{lint_cmd}
{f'# Tests{chr(10)}{test_cmd}' if test_cmd else ''}
{f'# Dev server{chr(10)}{dev_cmd}' if dev_cmd else ''}
```

Dev server URL: http://localhost:{dev_port}

### TACTICAL Fix Criteria

| Condition | Strategy | Reason |
|-----------|----------|--------|
{tactical_table}

### Project Structure

{monorepo_info}
- Shared packages: {', '.join(cfg.paths.shared_packages) or 'none'}
- Shared components: {', '.join(cfg.paths.shared_components) or 'none'}
- Isolated modules: {', '.join(cfg.paths.isolated_modules) or 'none'}
{f'- Domain logic: {chr(44).join(cfg.paths.domain_logic)}' if cfg.paths.domain_logic else ''}

---
"""


# ==========================================
# Issue 載入
# ==========================================

def load_issue_report(issue_id: str) -> dict:
    """載入 Bug 報告（從 issues/sources/<id>.json）"""
    bug_file = ISSUES_DIR / f"{issue_id}.json"
    if not bug_file.exists():
        raise FileNotFoundError(
            f"Bug report not found: {bug_file}\n"
            f"Please create the file using the template in issues/TEMPLATE.json"
        )
    with open(bug_file, 'r', encoding='utf-8') as f:
        return json.load(f)


# ==========================================
# 報告讀取（用於路由決策）
# ==========================================

def read_analyze_status(issue_id: str) -> str:
    report = REPORT_DIR / issue_id / "analyze.md"
    if not report.exists():
        return "missing"
    text = report.read_text(encoding='utf-8')
    if re.search(r'\*\*Status\*\*[:\s]+confirmed', text, re.IGNORECASE):
        return "confirmed"
    if re.search(r'\bconfirmed\b', text, re.IGNORECASE) and \
       not re.search(r'need_more_info', text, re.IGNORECASE):
        return "confirmed"
    return "need_more_info"


def read_test_verdict(issue_id: str, retry: int = 0) -> str:
    filename = "test.md" if retry == 0 else f"test-retry-{retry}.md"
    report = REPORT_DIR / issue_id / filename
    if not report.exists():
        return "FAIL"
    text = report.read_text(encoding='utf-8')
    match = re.search(r'\*\*Verdict\*\*[:\s]+\**\s*(PASS|FAIL)\**', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if 'PASS' in text.upper() and 'FAIL' not in text.upper():
        return "PASS"
    return "FAIL"


def read_report(issue_id: str, report_type: str, retry: int = 0) -> str:
    filename = f"test-retry-{retry}.md" if report_type == "test" and retry > 0 else f"{report_type}.md"
    report = REPORT_DIR / issue_id / filename
    return report.read_text(encoding='utf-8') if report.exists() else f"(report not found: {filename})"


# ==========================================
# Workflow
# ==========================================

async def run_workflow(issue_id: str):
    """
    執行完整 bug fix 流程：
      Phase 1 (analyze) + Phase 2 (implement) → 共用 session
      Phase 3 (test) → 每次 fork 新 session
      Test FAIL → retry implement 回主 session（帶失敗回饋）
    """
    issue_report = load_issue_report(issue_id)
    issue_json = json.dumps(issue_report, ensure_ascii=False, indent=2)

    # 載入通用 skills + 動態生成專案 context
    _, analyze_body = load_skill("bugfix-analyze", SKILLS_DIR)
    _, implement_body = load_skill("bugfix-implement", SKILLS_DIR)
    _, test_body = load_skill("bugfix-test", SKILLS_DIR)
    project_context = load_project_context()

    print(f"\n{'='*60}")
    print(f"  Bugfix Workflow v3.1 (Skill-Based)")
    print(f"  Project: {PROJECT_CONFIG.project_name}")
    print(f"  Issue: {issue_id}")
    print(f"{'='*60}")

    # ----------------------------------------
    # 建立主 session（analyze + implement 共用）
    # ----------------------------------------
    print("\n🔧 建立主 session (analyze + implement)...")
    _, main_session = await create_session(ANALYZE_IMPLEMENT_TOOLS)

    # ----------------------------------------
    # Phase 1: bugfix-analyze
    # ----------------------------------------
    print(f"\n{'─'*60}")
    print("  Phase 1 / bugfix-analyze")
    print(f"{'─'*60}")

    analyze_msg = f"""{project_context}{analyze_body}

---

Task: Analyze the following issue.

Issue report:
{issue_json}

Project root: {PROJECT_ROOT}
"""
    await run_in_session(main_session, "analyze", analyze_msg, max_tool_calls=50)

    status = read_analyze_status(issue_id)
    print(f"\n  📊 Analyze status: {status}")
    if status != "confirmed":
        print(f"\n  ❌ Analysis not confirmed (status={status}), workflow terminated")
        return

    # ----------------------------------------
    # Phase 2: bugfix-implement（同一 session）
    # ----------------------------------------
    print(f"\n{'─'*60}")
    print("  Phase 2 / bugfix-implement")
    print(f"{'─'*60}")

    implement_msg = f"""---
## ROLE SWITCH: bugfix-implement

You've completed the analysis phase above. The code investigation is in this session's context — you don't need to re-read files you already read. Now switch to implementation mode.

{implement_body}

---

Task: Implement the fix for issue {issue_id}.
Project root: {PROJECT_ROOT}

Read issues/reports/{issue_id}/analyze.md for the fix strategy and root cause.

Project Context (commands & paths):
{project_context}"""
    await run_in_session(main_session, "implement", implement_msg, max_tool_calls=30)

    # ----------------------------------------
    # Phase 3: bugfix-test（每次 fork 新 session）
    # ----------------------------------------
    max_retries = 3
    for retry in range(max_retries + 1):
        label = f"Phase 3 / bugfix-test{f' (retry {retry})' if retry > 0 else ''}"
        print(f"\n{'─'*60}")
        print(f"  {label}")
        print(f"{'─'*60}")

        _, test_session = await create_session(TEST_TOOLS)

        retry_section = ""
        if retry > 0:
            prev = read_report(issue_id, "test", retry - 1) if retry > 1 else read_report(issue_id, "test")
            retry_section = f"""
## Previous Test Failure (retry {retry})

{prev}

The engineer has made additional fixes. Re-verify everything.
"""

        report_path = (
            f"issues/reports/{issue_id}/test.md" if retry == 0
            else f"issues/reports/{issue_id}/test-retry-{retry}.md"
        )

        test_msg = f"""{project_context}{test_body}
{retry_section}
---

Task: Verify the fix for issue {issue_id}.
Project root: {PROJECT_ROOT}

Context reports to read:
- Analysis: issues/reports/{issue_id}/analyze.md
- Implementation: issues/reports/{issue_id}/implement.md

Write your verification report to: {report_path}
"""
        await run_in_session(test_session, "test", test_msg, max_tool_calls=40)

        verdict = read_test_verdict(issue_id, retry)
        print(f"\n  ⚖️  Verdict: {verdict}")

        if verdict == "PASS":
            print(f"\n  ✅ Fix complete! All checks passed.")
            print(f"     Reports: issues/reports/{issue_id}/")
            return

        if retry < max_retries:
            print(f"\n  🔄 Test FAIL → retry implement ({retry + 1}/{max_retries})")
            test_report = read_report(issue_id, "test", retry)
            retry_msg = f"""---
## IMPLEMENT RETRY {retry + 1}/{max_retries}: Previous fix failed

The previous implementation did not pass verification. Here is the test failure report:

{test_report}

{implement_body}

---

Task: Fix the identified issues for {issue_id}.
Project root: {PROJECT_ROOT}

Context:
- Analysis: issues/reports/{issue_id}/analyze.md
- Previous implementation: issues/reports/{issue_id}/implement.md
"""
            await run_in_session(
                main_session, f"implement-retry-{retry + 1}", retry_msg, max_tool_calls=30
            )
        else:
            print(f"\n  💀 Max retries ({max_retries}) reached, workflow terminated")


# ==========================================
# Entry point
# ==========================================

async def main(issue_id: str):
    print(f"""
╭──────────────────────────────────────────────────────────╮
│      Bugfix Workflow v3.1 (Skill-Based)                  │
│      Project: {PROJECT_CONFIG.project_name:<38}│
│      Issue:   {issue_id:<38}│
╰──────────────────────────────────────────────────────────╯
""")
    loop = asyncio.get_event_loop()
    restore = setup_sdk_error_silencing(loop)
    try:
        await run_workflow(issue_id)
    except FileNotFoundError as e:
        print(f"\n❌ 錯誤: {e}")
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        restore()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方式: python main.py <issue_id>")
        print(f"範例: python main.py {ISSUE_PREFIX}-1234")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
