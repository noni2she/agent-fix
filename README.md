# Agent Fix

> Claude Code 插件 — 一個指令端對端修復 Bug：issue 擷取 → 重現 + 根源分析 → 實作 → 驗證。

## Features

- **Claude Code 原生** — 以 plugin 形式運作，Claude Code 負責 agentic loop、工具分發、context 管理
- **配置驅動** — 使用 YAML 定義專案結構，支援任意框架與 Monorepo
- **四段 Sub-agent** — extract / analyze / implement / test 各自獨立 session，context 不累積
- **Judge Gate** — 每個 phase 結束後語意判斷 PROCEED / RETRY / CHECKPOINT，品質有保障
- **MCP 工具伺服器** — 5 個 domain 工具作為 MCP server 暴露，plugin 呼叫標準介面
- **Declarative Harness** — `harness_rules.yaml` 集中管理 phase tool 限制與截斷規則
- **Behavior Validation** — Playwright 行為驗證，上限 3 次，強制先觀察再執行
- **批次執行** — SDK driver 逐一在 git worktree 內執行，crash-safe state 檔支援中斷恢復

## Architecture

```
agent-fix/
├── .claude-plugin/
│   └── plugin.json                # Plugin 宣告（name / description / author）
├── commands/
│   └── fix-one-issue.md           # 主指令：序列化 sub-agents + judge gate
├── agents/
│   ├── extract.md                 # Sub-agent: 從來源取 issue，回傳 IssueData JSON
│   ├── analyze.md                 # Sub-agent: 瀏覽器重現 + 根源分析 + 寫 analyze.md
│   ├── implement.md               # Sub-agent: git branch + 實作修復 + 品質檢查
│   └── test.md                    # Sub-agent: 靜態分析 + 策略合規 + 行為驗證
├── mcp_servers/
│   └── agent_fix_tools/
│       └── server.py              # 5-tool MCP server（stdio，FastMCP）
├── batch_runner/
│   └── driver.py                  # SDK driver：批次發 issue，worktree 隔離
├── engine/
│   ├── config.py                  # ProjectConfig（Pydantic YAML 驗證）
│   ├── harness_rules.yaml         # Phase tool 限制 + 截斷規則（declarative）
│   ├── tools.py                   # Domain 工具（品質檢查 / 行為驗證 / 技術債）
│   ├── behavior_validation/       # Playwright runner（BehaviorValidator）
│   ├── issue_source/              # Issue 來源 adapter（local_json / Jira / Sheets）
│   └── skill_loader.py            # SKILL.md 讀取（park，備 Phase 2/3 使用）
├── skills/                        # 現有 SKILL.md（舊式 skill，可被 sub-agents 參考）
├── projects/                      # 各目標專案配置
│   └── <slug>/
│       └── config.yaml            # 專案配置
└── .mcp.json                      # MCP server 配置（chrome-devtools + agent-fix-tools）
```

### Workflow（Sub-agent Pipeline）

```
/fix-one-issue <ISSUE-ID>
    │
    ├─ [extract sub-agent]
    │       fetch_issue(issue_id) → IssueData JSON
    │       Gate 0: ❌ → CHECKPOINT
    │
    ├─ [analyze sub-agent]   ← 收到 IssueData JSON
    │       Step 0: 瀏覽器重現（chrome-devtools MCP）
    │       → Evidence Package（reproduce_confidence）
    │       Gate 1a: confidence < 0.5 → RETRY once → CHECKPOINT
    │       Steps 1–5: 讀原始碼 → 定位根因 → 評估影響 → 選策略
    │       → 寫 issues/reports/<id>/analyze.md
    │       Gate 1b: 缺 Root Cause File/Line → RETRY once → CHECKPOINT
    │
    ├─ [implement sub-agent]  ← 收到 analyze.md 路徑
    │       git worktree branch → 實作修復（DIRECT / TACTICAL）
    │       → run_typescript_check + run_eslint
    │       → 寫 issues/reports/<id>/implement.md
    │       Gate 2: TS FAILED → RETRY once → CHECKPOINT
    │
    └─ [test sub-agent]       ← 收到 analyze.md + implement.md 路徑
            靜態分析 + 策略合規 + 行為驗證（≤ 3 次 Playwright）
            → 寫 issues/reports/<id>/test.md
            Gate 3: FAIL → RETRY once → CHECKPOINT
            PASS / SKIPPED → 輸出 Fix Complete 摘要
```

| Phase | Sub-agent | 主要工具 | 輸出 |
|-------|-----------|---------|------|
| **extract** | extract | `fetch_issue` MCP | IssueData JSON |
| **analyze** | analyze | chrome-devtools MCP + Read/Grep | `analyze.md` |
| **implement** | implement | Edit/Write/Bash + `run_typescript_check` / `run_eslint` MCP | `implement.md` |
| **test** | test | `run_behavior_validation` / `record_tech_debt` MCP | `test.md` |

## Quick Start

### 1. 安裝

```bash
git clone https://github.com/noni2she/agent-fix.git
cd agent-fix
uv sync   # 安裝 Python 依賴（含 mcp, playwright）
```

### 2. 初始化專案配置

複製範本並填入目標專案資訊：

```bash
cp config-template.yaml projects/<slug>/config.yaml
# 編輯 config.yaml：project_root, issue_source, quality_checks, dev_server
```

### 3. 設定環境

```bash
# 必填
export PROJECT_CONFIG=./projects/<slug>/config.yaml
export ANTHROPIC_API_KEY=...   # 批次 SDK driver 使用

# 行為驗證（選填，需要登入時）
export PROJ_TEST_USERNAME=...
export PROJ_TEST_PASSWORD=...
```

### 4. 安裝 Plugin 到 Claude Code

```bash
claude plugin install .
```

### 5. 執行修復

在 Claude Code 對話中：

```
/fix-one-issue PROJ-001
```

或使用批次 SDK driver：

```bash
python -m batch_runner.driver --issues PROJ-001,PROJ-002
python -m batch_runner.driver --issues-file issues.txt
python -m batch_runner.driver --source jira --jql "project = PROJ AND status = 'To Do'"
```

## CLI Commands

| 指令 | 說明 |
|------|------|
| `/fix-one-issue <ISSUE-ID>` | 在 Claude Code 中端對端修復單一 issue |
| `python -m batch_runner.driver --issues A,B,C` | 批次修復（sequential，worktree 隔離） |
| `python -m batch_runner.driver --batch-id <id>` | 恢復中斷的批次 |

## Configuration

詳見 [config-template.yaml](config-template.yaml) 查看所有選項。

### MCP Servers

`.mcp.json` 宣告兩個 MCP server，Claude Code 自動管理生命週期：

| Server | 用途 | 觸發 Phase |
|--------|------|-----------|
| `chrome-devtools` | 瀏覽器重現（截圖 / DevTools） | analyze Step 0 |
| `agent-fix-tools` | Domain 工具（fetch_issue / 品質檢查 / 行為驗證） | 所有 phases |

### Harness Rules

`engine/harness_rules.yaml` 集中管理 phase 約束，不散落程式碼：

```yaml
phases:
  reproduce:
    mcp_servers: [chrome-devtools]
    tool_limits:
      take_screenshot: 1       # 超過回傳 Positive Prompt Injection
      evaluate_script: 5
  test:
    tool_limits:
      run_behavior_validation: 3   # 強制先 view/bash 確認 selector 再呼叫
```

## Custom Tools

以下 5 個工具由 `mcp_servers/agent_fix_tools/server.py` 暴露為 MCP tools：

| 工具 | 用途 | Sub-agent |
|------|------|-----------|
| `fetch_issue` | 從 local_json / Jira / Sheets 取 issue | extract |
| `run_typescript_check` | TypeScript 編譯檢查（timeout 120s） | implement, test |
| `run_eslint` | ESLint 檢查（warning 允許，error = FAIL） | implement, test |
| `run_behavior_validation` | Playwright E2E 驗證（≤ 3 次/session） | test |
| `record_tech_debt` | 寫入 tech_debt.json（跳過測試時記錄） | test |

## Testing

```bash
uv run pytest
```

---

**Version**: v4.0.0 | **License**: MIT
