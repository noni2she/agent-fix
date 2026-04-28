# engine/workflow.py
"""
Agent Bugfix v3.1 — Skill-Based Workflow Engine

Skills 架構：
  - 通用 skills：agent-fix/skills/（流程邏輯，不含專案細節）
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
import time
from pathlib import Path
from dotenv import load_dotenv

from .config import ProjectConfig, load_config_from_env, ConfigurationError
from .project_spec import ProjectSpec
from .skill_loader import load_skill
from .issue_source import create_adapter, IssueNotFoundError, IssueSourceError
from .agent_runner import (
    create_session,
    run_in_session,
    setup_sdk_error_silencing,
    init_agent_runner,
    ANALYZE_IMPLEMENT_TOOLS,
    TEST_TOOLS,
    INIT_TOOLS,
)
from .mcp_client import MCPClientManager
from .tools import init_tools, set_current_issue_id

# skills/ 目錄路徑：相對於此檔案，往上一層再進 skills/
# 安裝後位於 site-packages/engine/workflow.py，skills/ 也會在 site-packages/skills/
SKILLS_DIR = Path(__file__).parent.parent / "skills"

# agent 本身的根目錄（存放 issues/reports, issues/screenshots）
# 與被修正的目標專案（project_root）完全分開
AGENT_ROOT = Path(__file__).parent.parent.resolve()


# ==========================================
# Workflow 初始化（延遲到執行時才載入 config）
# ==========================================

def init_workflow() -> tuple[ProjectConfig, ProjectSpec, Path]:
    """
    初始化 workflow 所需元件，延遲到執行時才載入。
    不在 module 層級執行，避免 import 時觸發 sys.exit。
    """
    load_dotenv()

    print("\n" + "=" * 60)
    print("🚀 Agent Bugfix v3.1 — Skill-Based")
    print("=" * 60)

    config = load_config_from_env()
    spec = ProjectSpec(config)
    project_root = config.get_project_root()

    print(f"  ✅ Project: {config.project_name}")
    print(f"  ✅ Framework: {config.framework}")
    print(f"  ✅ Root: {project_root}")
    print(f"  ✅ Skills: {SKILLS_DIR}")

    warnings = config.validate_project_structure()
    if warnings:
        print(f"\n  ⚠️  Warnings:")
        for w in warnings:
            print(f"     - {w}")

    init_tools(config)
    init_agent_runner(config, spec)
    print("=" * 60 + "\n")

    return config, spec, project_root


# ==========================================
# Project Context 生成（從 config.yaml 動態生成）
# ==========================================

def load_project_context(config: ProjectConfig, project_root: Path, agent_root: Path = AGENT_ROOT) -> str:
    """
    從 ProjectConfig 動態生成專案 context，注入每個 phase prompt 開頭。

    以 config.yaml 驅動，動態生成通用 project context，
    注入每個 phase prompt 開頭，無需額外 SKILL.md。
    """
    cfg = config

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

    # Skills Directories（注入所有可用 skill 路徑）
    skill_dirs = cfg.skills.directories
    skills_section = ""
    if skill_dirs:
        dirs_list = "\n".join(f"- {d}" for d in skill_dirs)
        skills_section = f"""
### Available Skills Directories

當 skill 指示你載入其他 skill（如 `/vercel-react-best-practices`、`/web-design-guidelines`）時，
在以下目錄中尋找對應的 `<skill-name>/SKILL.md` 檔案：

{dirs_list}

用 `read_file` 讀取後再依照規則撰寫程式碼。
"""

    # Behavior Validation scenario schema（只在 enabled 時注入）
    bv_section = ""
    if config.behavior_validation.enabled:
        bv_section = f"""
### Behavior Validation — Scenario Schema

When `verification_method == "e2e"`, call the `run_behavior_validation` tool with a JSON string:

```json
{{
  "name": "<issue-id>",
  "url_path": "/path/to/test",
  "actions": [
    {{"type": "goto",       "value": "/path"}},
    {{"type": "wait_for",  "selector": "#element",          "timeout": 10000}},
    {{"type": "click",     "selector": "#button"}},
    {{"type": "type",      "selector": "input#name",        "value": "text input"}}
  ],
  "assertions": [
    {{"type": "visible",      "selector": "#element",   "expected": true}},
    {{"type": "text_content", "selector": "#el",        "expected": "expected text"}},
    {{"type": "url",                                     "expected": "/expected-path"}},
    {{"type": "count",        "selector": ".items",     "expected": 3}}
  ]
}}
```

Dev server: http://localhost:{dev_port}
Rules:
- Always start with a `goto` action
- Use `wait_for` before interacting with dynamically rendered elements
- Do NOT add `screenshot` actions — Python takes a screenshot automatically on failure
- Design assertions based on `reproduction_steps` and expected fix outcome
"""

    return f"""> 🌐 語言指令：請以 **{cfg.response_language}** 回覆所有回應（分析報告、說明、摘要），程式碼與指令維持原文。

## Project Context

**Project**: {cfg.project_name} ({cfg.framework})
**Target project root** (read/modify source code here): {project_root}
**Agent root** (write reports & screenshots here): {agent_root}
- Reports: `{agent_root}/issues/reports/{cfg.get_project_key()}/<issue-id>/`
- Screenshots: `{agent_root}/issues/screenshots/{cfg.get_project_key()}/<issue-id>/`

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
{f'- Domain logic: {chr(44).join(cfg.paths.domain_logic)}' if cfg.paths.domain_logic else ''}{skills_section}{bv_section}
---
"""


# ==========================================
# Issue 載入
# ==========================================

# ==========================================
# 報告讀取（用於路由決策）
# ==========================================

def read_analyze_status(issue_id: str, report_dir: Path) -> str:
    report = report_dir / issue_id / "analyze.md"
    if not report.exists():
        return "missing"
    text = report.read_text(encoding='utf-8')
    if re.search(r'\*\*Status\*\*[:\s]+already_fixed', text, re.IGNORECASE):
        return "already_fixed"
    if re.search(r'\*\*Status\*\*[:\s]+confirmed', text, re.IGNORECASE):
        return "confirmed"
    if re.search(r'\bconfirmed\b', text, re.IGNORECASE) and \
       not re.search(r'need_more_info', text, re.IGNORECASE):
        return "confirmed"
    return "need_more_info"


def read_test_verdict(issue_id: str, report_dir: Path, retry: int = 0) -> str:
    filename = "test.md" if retry == 0 else f"test-retry-{retry}.md"
    report = report_dir / issue_id / filename
    if not report.exists():
        return "FAIL"
    text = report.read_text(encoding='utf-8')
    match = re.search(r'\*\*Verdict\*\*[:\s]+\**\s*(PASS|FAIL)\**', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if 'PASS' in text.upper() and 'FAIL' not in text.upper():
        return "PASS"
    return "FAIL"


def read_report(issue_id: str, report_type: str, report_dir: Path, retry: int = 0) -> str:
    filename = f"test-retry-{retry}.md" if report_type == "test" and retry > 0 else f"{report_type}.md"
    report = report_dir / issue_id / filename
    return report.read_text(encoding='utf-8') if report.exists() else f"(report not found: {filename})"


# ==========================================
# Workflow
# ==========================================

async def _execute_workflow(
    issue_id: str,
    config: ProjectConfig,
    project_root: Path,
    mcp_manager=None,
):
    """
    執行完整 bug fix 流程：
      Phase 1 (analyze) + Phase 2 (implement) → 共用 session
      Phase 3 (test) → 每次 fork 新 session
      Test FAIL → retry implement 回主 session（帶失敗回饋）

    mcp_manager：可從外部傳入（batch 模式共用），若為 None 則自行建立與關閉。
    """
    # issues/ 報告目錄：issues/reports/<project-key>/（固定在 agent root，不是目標專案）
    project_key = config.get_project_key()
    report_dir = AGENT_ROOT / "issues" / "reports" / project_key
    report_dir.mkdir(parents=True, exist_ok=True)

    # 透過 issue source adapter 取得 issue 資料
    adapter = create_adapter(config.issue_source)
    try:
        adapter.validate()
        issue_report = adapter.fetch(issue_id)
    except IssueNotFoundError as e:
        print(f"\n❌ Issue not found: {e}")
        sys.exit(1)
    except IssueSourceError as e:
        print(f"\n❌ Failed to fetch issue: {e}")
        sys.exit(1)
    # 提取圖片附件（analyze 階段使用），不寫入 issue_json
    issue_images: list[dict] = issue_report.pop("_images", None) or []
    if issue_images:
        print(f"  📎 附件圖片：{len(issue_images)} 張，將隨 analyze prompt 傳入")
    issue_json = json.dumps(issue_report, ensure_ascii=False, indent=2)

    # 鎖定 issue_id，確保 run_behavior_validation 截圖目錄不受 AI scenario name 影響
    set_current_issue_id(issue_id)

    # 載入通用 skills + 動態生成專案 context
    _, analyze_body = load_skill("bugfix-analyze", SKILLS_DIR)
    _, implement_body = load_skill("bugfix-implement", SKILLS_DIR)
    _, test_body = load_skill("bugfix-test", SKILLS_DIR)
    project_context = load_project_context(config, project_root)

    print(f"\n{'=' * 60}")
    print(f"  Agent Bugfix v3.1 (Skill-Based)")
    print(f"  Project: {config.project_name}")
    print(f"  Issue: {issue_id}")
    print(f"{'=' * 60}")

    # ----------------------------------------
    # MCP manager：外部傳入則共用，否則自行建立
    # ----------------------------------------
    _owns_mcp = mcp_manager is None
    if _owns_mcp:
        enabled_mcp = {k: v for k, v in config.mcp_servers.items() if v.enabled}
        if enabled_mcp:
            print("\n🔌 啟動 MCP servers (analyze phase)...")
            mcp_manager = await MCPClientManager.create(enabled_mcp)

    # ----------------------------------------
    # 建立主 session（analyze + implement 共用）
    # ----------------------------------------
    print("\n🔧 建立主 session (analyze + implement)...")
    _, main_session = await create_session(ANALYZE_IMPLEMENT_TOOLS, mcp_manager=mcp_manager)

    # ----------------------------------------
    # Phase 1: bugfix-analyze
    # ----------------------------------------
    print(f"\n{'─' * 60}")
    print("  Phase 1 / bugfix-analyze")
    print(f"{'─' * 60}")

    analyze_msg = f"""{project_context}{analyze_body}

---

Task: Analyze the following issue.

Issue report:
{issue_json}

Target project root (source code): {project_root}
Write analysis report to: {report_dir / issue_id / "analyze.md"}
Write screenshots to: {AGENT_ROOT / "issues" / "screenshots" / project_key / issue_id}/
"""
    await run_in_session(main_session, "analyze", analyze_msg, max_tool_calls=50,
                         images=issue_images or None)

    status = read_analyze_status(issue_id, report_dir)
    print(f"\n  📊 Analyze status: {status}")
    if status == "already_fixed":
        print(f"\n  ✅ Issue already fixed in codebase, no action needed.")
        print(f"     Report: issues/reports/{issue_id}/analyze.md")
        if mcp_manager:
            await mcp_manager.stop()
        return
    if status != "confirmed":
        print(f"\n  ⏸️  Analysis stopped (status={status}) — insufficient information to proceed.")
        print(f"     Check issues/reports/{issue_id}/analyze.md for known findings.")
        if mcp_manager:
            await mcp_manager.stop()
        return

    # ----------------------------------------
    # Phase 2: bugfix-implement（同一 session）
    # ----------------------------------------
    print(f"\n{'─' * 60}")
    print("  Phase 2 / bugfix-implement")
    print(f"{'─' * 60}")

    implement_msg = f"""---
## ROLE SWITCH: bugfix-implement

You've completed the analysis phase above. The code investigation is in this session's context — you don't need to re-read files you already read. Now switch to implementation mode.

{implement_body}

---

Task: Implement the fix for issue {issue_id}.
Target project root (source code): {project_root}

Read analysis report from: {report_dir / issue_id / "analyze.md"}
Write implementation report to: {report_dir / issue_id / "implement.md"}

Project Context (commands & paths):
{project_context}"""
    await run_in_session(main_session, "implement", implement_msg, max_tool_calls=30)

    # MCP servers：自行建立的才在此關閉；外部共用的由 batch 層負責關閉
    if _owns_mcp and mcp_manager:
        await mcp_manager.stop()
        mcp_manager = None
        print("\n🔌 MCP servers stopped")

    # ----------------------------------------
    # Phase 3: bugfix-test（每次 fork 新 session）
    # ----------------------------------------
    max_retries = 3
    for retry in range(max_retries + 1):
        label = f"Phase 3 / bugfix-test{f' (retry {retry})' if retry > 0 else ''}"
        print(f"\n{'─' * 60}")
        print(f"  {label}")
        print(f"{'─' * 60}")

        _, test_session = await create_session(TEST_TOOLS)

        retry_section = ""
        if retry > 0:
            prev = read_report(issue_id, "test", report_dir, retry - 1) if retry > 1 else read_report(issue_id, "test", report_dir)
            retry_section = f"""
## Previous Test Failure (retry {retry})

{prev}

The engineer has made additional fixes. Re-verify everything.
"""

        report_path = (
            report_dir / issue_id / "test.md" if retry == 0
            else report_dir / issue_id / f"test-retry-{retry}.md"
        )

        test_msg = f"""{project_context}{test_body}
{retry_section}
---

Task: Verify the fix for issue {issue_id}.
Target project root (source code): {project_root}

Context reports to read:
- Analysis: {report_dir / issue_id / "analyze.md"}
- Implementation: {report_dir / issue_id / "implement.md"}

Write your verification report to: {report_path}
"""
        await run_in_session(test_session, "test", test_msg, max_tool_calls=40)

        verdict = read_test_verdict(issue_id, report_dir, retry)
        print(f"\n  ⚖️  Verdict: {verdict}")

        if verdict == "PASS":
            print(f"\n  ✅ Fix complete! All checks passed.")
            print(f"     Reports: {report_dir / issue_id}/")
            return

        if retry < max_retries:
            print(f"\n  🔄 Test FAIL → retry implement ({retry + 1}/{max_retries})")
            test_report = read_report(issue_id, "test", report_dir, retry)
            retry_msg = f"""---
## IMPLEMENT RETRY {retry + 1}/{max_retries}: Previous fix failed

The previous implementation did not pass verification. Here is the test failure report:

{test_report}

{implement_body}

---

Task: Fix the identified issues for {issue_id}.
Target project root (source code): {project_root}

Context:
- Analysis: {report_dir / issue_id / "analyze.md"}
- Previous implementation: {report_dir / issue_id / "implement.md"}
"""
            await run_in_session(
                main_session, f"implement-retry-{retry + 1}", retry_msg, max_tool_calls=30
            )
        else:
            print(f"\n  💀 Max retries ({max_retries}) reached, workflow terminated")


def _fmt_duration(seconds: float) -> str:
    """將秒數格式化為可讀字串，如 '2m 34s' 或 '45s'。"""
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


async def run_batch_workflow(issue_ids: list[str]):
    """
    批次執行：依序處理每個 issue，逐一執行完整 bug fix 流程。
    任一 issue 失敗不中斷後續執行，最後彙總結果。
    """
    try:
        config, spec, project_root = init_workflow()
    except ConfigurationError as e:
        print(f"\n❌ Configuration Error: {e}\n")
        sys.exit(1)

    total = len(issue_ids)
    passed: list[str] = []
    skipped: list[str] = []   # already_fixed or need_more_info
    failed: list[str] = []
    timings: dict[str, float] = {}   # issue_id → elapsed seconds
    _batch_t0 = time.perf_counter()

    print(f"""
╭──────────────────────────────────────────────────────────╮
│      Agent Bugfix v3.1 — Batch Mode                      │
│      Project: {config.project_name:<38}│
│      Issues:  {total:<38}│
╰──────────────────────────────────────────────────────────╯
""")

    loop = asyncio.get_event_loop()
    restore = setup_sdk_error_silencing(loop)

    # 建立共用 MCP manager（所有 issue 共用同一個 Chrome instance）
    enabled_mcp = {k: v for k, v in config.mcp_servers.items() if v.enabled}
    shared_mcp = None
    if enabled_mcp:
        print("\n🔌 啟動 MCP servers（batch 共用）...")
        shared_mcp = await MCPClientManager.create(enabled_mcp)

    try:
        for idx, issue_id in enumerate(issue_ids, 1):
            print(f"\n{'═'*60}")
            print(f"  [{idx}/{total}] {issue_id}")
            print(f"{'═'*60}")
            _issue_t0 = time.perf_counter()
            try:
                await _execute_workflow(issue_id, config, project_root, mcp_manager=shared_mcp)
                timings[issue_id] = time.perf_counter() - _issue_t0
                print(f"\n  ⏱️  {issue_id} 耗時：{_fmt_duration(timings[issue_id])}")
                # 讀取 analyze status 判斷是否真的跑完修復，或是中途中止
                report_dir = AGENT_ROOT / "issues" / "reports" / config.get_project_key()
                status = read_analyze_status(issue_id, report_dir)
                if status in ("already_fixed", "need_more_info", "missing"):
                    skipped.append(issue_id)
                else:
                    passed.append(issue_id)
            except Exception as e:
                timings[issue_id] = time.perf_counter() - _issue_t0
                print(f"\n  ❌ {issue_id} failed: {e}  ({_fmt_duration(timings[issue_id])})")
                import traceback
                traceback.print_exc()
                failed.append(issue_id)
    finally:
        if shared_mcp:
            await shared_mcp.stop()
            print("\n🔌 MCP servers stopped (batch)")
        restore()

    total_elapsed = time.perf_counter() - _batch_t0
    print(f"""
╭──────────────────────────────────────────────────────────╮
│      Batch Complete                                       │
│      ✅ Fixed:   {len(passed):<41}│
│      ⏸️  Skipped: {len(skipped):<41}│
│      ❌ Failed:  {len(failed):<41}│
│      ⏱️  Total:   {_fmt_duration(total_elapsed):<41}│
╰──────────────────────────────────────────────────────────╯""")

    if passed:
        print("\n  Fixed:")
        for i in passed:
            print(f"    ✅ {i}  ({_fmt_duration(timings.get(i, 0))})")
    if skipped:
        print("\n  Skipped (already_fixed or need_more_info):")
        for i in skipped:
            report_dir = AGENT_ROOT / "issues" / "reports" / config.get_project_key()
            status = read_analyze_status(i, report_dir)
            print(f"    ⏸️  {i}  [{status}]  ({_fmt_duration(timings.get(i, 0))})")
    if failed:
        print("\n  Failed:")
        for i in failed:
            print(f"    ❌ {i}  ({_fmt_duration(timings.get(i, 0))})")


async def run_init_workflow(project_path: str, output_path: str, issue_prefix: str):
    """
    Smart init：用 LLM agent 探索目標專案，自動生成 config.yaml。

    Args:
        project_path:  目標專案根目錄絕對路徑
        output_path:   生成的 config.yaml 輸出路徑
        issue_prefix:  Issue ID 前綴（如 BUG、PROJ）
    """
    import os

    _, init_body = load_skill("project-init", SKILLS_DIR)

    # Copilot SDK 已內建 read_file / glob / grep 等工具，不需要額外註冊
    # Claude / OpenAI adapter 需要 INIT_TOOLS
    sdk = os.getenv("SDK_ADAPTER", "copilot")
    tool_names = [] if sdk == "copilot" else INIT_TOOLS

    print("\n" + "=" * 60)
    print("🚀 Agent Bugfix — Smart Project Init")
    print(f"   Target : {project_path}")
    print(f"   Output : {output_path}")
    print(f"   SDK    : {sdk}")
    print("=" * 60)

    loop = asyncio.get_event_loop()
    restore = setup_sdk_error_silencing(loop)

    try:
        _, session = await create_session(tool_names)

        prompt = f"""{init_body}

---

## Task

Analyze the project at the following path and generate a config.yaml.

- **project_path**: `{project_path}`
- **output_path**: `{output_path}`
- **issue_prefix**: `{issue_prefix}`

Follow the exploration steps in the skill above. Write the generated config.yaml to `{output_path}`.
"""
        await run_in_session(session, "init", prompt, max_tool_calls=30)
    finally:
        restore()


async def run_workflow(issue_id: str):
    """
    CLI entry point：初始化 workflow 後執行完整修復流程。
    所有初始化延遲到此處，避免 import 時觸發 sys.exit。
    """
    try:
        config, spec, project_root = init_workflow()
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

    print(f"""
╭──────────────────────────────────────────────────────────╮
│      Agent Bugfix v3.1 (Skill-Based)                     │
│      Project: {config.project_name:<38}│
│      Issue:   {issue_id:<38}│
╰──────────────────────────────────────────────────────────╯
""")
    loop = asyncio.get_event_loop()
    restore = setup_sdk_error_silencing(loop)
    try:
        await _execute_workflow(issue_id, config, project_root)
    except FileNotFoundError as e:
        print(f"\n❌ 錯誤: {e}")
    except Exception as e:
        print(f"\n❌ 發生錯誤: {e}")
        import traceback
        traceback.print_exc()
    finally:
        restore()
