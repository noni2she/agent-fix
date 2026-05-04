# Agent Fix

> 通用 AI 問題分析與修復代理引擎 — Skill-Based，支援 Copilot / Claude / OpenAI SDK。

## Features

- **配置驅動** — 使用 YAML 定義專案結構，支援任意框架與 Monorepo
- **Skill-Based 架構** — 以 SKILL.md 定義行為，流程邏輯與專案細節分離
- **多 SDK 支援** — GitHub Copilot / Anthropic Claude / OpenAI Agents（一行切換）
- **Smart Init** — LLM 自動偵測目標專案結構，生成 config.yaml
- **Orchestrator-Worker** — 每個 phase 獨立 session，資訊隔離防止 goal contamination
- **Progressive Disclosure** — Analyze 分三輪揭露 SKILL.md，消除 backward pressure
- **Artifact 語義驗證** — 每次 spawn 前以純 Python 驗證上游 artifact 品質
- **Smart Retry** — 測試失敗自動回到 implement 重修（最多 3 次）
- **MCP 支援** — bugfix-analyze 階段可接 chrome-devtools-mcp 等 MCP server

## Architecture

```
agent-fix/
├── install.sh                 # 一鍵安裝腳本
├── cli.py                     # CLI 入口（agent-fix / afix 指令）
├── main.py                    # 向後相容 shim（python main.py <id>）
├── config-template.yaml       # 專案配置範本
├── projects/                  # 配置範例
│   ├── turborepo-nextjs.yaml  # Turborepo + Yarn Workspace
│   └── minimal-nextjs.yaml    # 單一 Next.js 專案
├── engine/
│   ├── workflow.py            # Workflow 主邏輯（init + execute，延遲載入）
│   ├── orchestrator.py        # BugfixOrchestrator（Orchestrator-Worker 主控）
│   ├── config.py              # ProjectConfig（Pydantic YAML 驗證）
│   ├── project_spec.py        # ProjectSpec（TACTICAL 判斷邏輯）
│   ├── agent_runner.py        # Session 管理，透過 adapters 操作 SDK
│   ├── skill_loader.py        # 讀取 SKILL.md（frontmatter + body）
│   ├── mcp_client.py          # MCPClientManager（analyze phase MCP 整合）
│   ├── tools.py               # 自訂工具（品質檢查 + 檔案系統工具）
│   ├── adapters/
│   │   ├── base.py            # AgentEvent / AgentSession / AgentAdapter ABC
│   │   ├── copilot_adapter.py # GitHub Copilot SDK（v0.2.x）
│   │   ├── claude_adapter.py  # Anthropic Claude SDK
│   │   └── openai_adapter.py  # OpenAI Agents SDK
│   └── __init__.py
├── skills/
│   ├── bugfix-analyze/SKILL.md   # RCA 分析
│   ├── bugfix-implement/SKILL.md # 實作修復
│   ├── bugfix-test/SKILL.md      # 驗證修復
│   └── project-init/SKILL.md    # 自動生成專案配置
└── issues/
    ├── TEMPLATE.json          # Issue 報告範本
    ├── sources/               # Bug 報告 JSON（輸入）
    └── reports/<issue-id>/    # 各 Phase 報告 Markdown（輸出）
```

### Workflow（Orchestrator-Worker）

```
CLI / main.py
    │
    ▼
workflow._execute_workflow()
    │  fetch issue data（Python）
    │  load SKILL.md × 3
    │  build project_context
    │
    ▼
BugfixOrchestrator.run()
    │
    ├─── Analyze Phase（Progressive Disclosure，同一 session，三輪）
    │       │
    │       ├── [Gate A] 只看到：preamble + Step 0.0 + issue JSON
    │       │    ← 輸出：能力前置表
    │       │    驗證：response 非空？
    │       │
    │       ├── [Gate B] 只看到：Steps 0.1–0.4（不知道 Steps 1–5 存在）
    │       │    ← 輸出：瀏覽器操作 + 截圖
    │       │    驗證：screenshot 存在 OR 有觀察文字？
    │       │
    │       └── [Gate C] 只看到：Steps 1–5 + output format + report path
    │            ← 輸出：analyze.md（含 [tested]/[inferred] 標籤）
    │
    ├─── Spawn Gate：validate_analyze()
    │       status=confirmed + confidence≥0.6 + root_cause_file 存在？
    │       FAIL → 結束（不 spawn Implement）
    │
    ├─── Implement Phase（獨立 session，無 analyze 推理 context）
    │       只送：project_context + implement SKILL + analyze.md 結論
    │       ← 輸出：implement.md + 程式碼修改
    │
    ├─── Spawn Gate：validate_implement()
    │       implement.md 引用了 root_cause_file？
    │
    ├─── Test Phase（獨立 session）
    │       只送：project_context + test SKILL + report paths
    │       ← 輸出：test.md（含 Verdict: PASS/FAIL）
    │
    ├── PASS → 結束 ✅
    │
    └── FAIL（最多 3 次）
         → 新 Implement session（帶 test failure report）
         → 新 Test session
         → 直到 PASS 或達上限
```

| Phase | Session | Context 隔離 | 輸出 |
|-------|---------|-------------|------|
| **analyze** Gate A | 主 session（含 MCP） | issue + Step 0.0 only | 能力前置表 |
| **analyze** Gate B | 同 session（同 MCP） | Steps 0.1–0.4 only | 截圖 + 觀察 |
| **analyze** Gate C | 同 session | Steps 1–5 + report path | `analyze.md` |
| **implement** | 獨立 session | analyze.md 結論 only | `implement.md` |
| **test** | 獨立 session | report paths only | `test.md` |

## Quick Start

### 1. 安裝

```bash
git clone https://github.com/noni2she/agent-fix.git
cd agent-fix
bash install.sh   # 一鍵安裝（含 gh CLI 與 Copilot 驗證）
```

或手動安裝（選擇其中一個 SDK）：

```bash
uv tool install --editable ".[copilot]"   # GitHub Copilot（推薦）
uv tool install --editable ".[claude]"    # Anthropic Claude
uv tool install --editable ".[openai]"    # OpenAI Agents
```

安裝完成後，`agent-fix` 與 `afix` 指令可在任意目錄使用。

### 2. 初始化專案配置

```bash
# LLM 自動偵測目標專案結構，生成 config.yaml
agent-fix init /path/to/my-project --output ./projects/my-project.yaml

# 指定 issue prefix（對應 Jira project key 或自訂前綴）
agent-fix init /path/to/my-project --issue-prefix PROJ --output ./projects/my-project.yaml

# 驗證生成的配置
agent-fix validate ./projects/my-project.yaml
```

### 3. 設定環境

```bash
cp .env.example .env
# 編輯 .env：
#   PROJECT_CONFIG=./projects/my-project.yaml
#   SDK_ADAPTER=copilot   # 或 claude / openai
```

### 4. 執行修復

```bash
# 建立 issue（local_json 模式）
cp issues/TEMPLATE.json issues/sources/BUG-001.json
# 填入 issue 資訊

# 執行
agent-fix run BUG-001
agent-fix run BUG-001 --config ./projects/my-project.yaml   # 明確指定
afix run BUG-001                                            # 簡短別名
```

### 切換 SDK

```bash
export SDK_ADAPTER=claude   # Anthropic Claude
export SDK_ADAPTER=openai   # OpenAI Agents
export SDK_ADAPTER=copilot  # GitHub Copilot（預設）
```

## CLI Commands

```
agent-fix init     <project_path> [--output <path>] [--issue-prefix <prefix>]
agent-fix validate <config-file>
agent-fix run      <issue-id> [--config <path>]
agent-fix batch    [--config <path>] [--dry-run] [--filter <pattern>]
agent-fix check-deps [--fix]
```

## Configuration

詳見 [config-template.yaml](config-template.yaml) 查看所有選項。

### MCP Servers（可選）

在 config.yaml 中啟用 chrome-devtools-mcp，讓 bugfix-analyze 能觀察 runtime 行為：

```yaml
mcp_servers:
  chrome-devtools:
    command: npx
    args: ["-y", "chrome-devtools-mcp@latest"]
    enabled: true
```

## Custom Tools

| 工具 | 用途 | Adapter |
|------|------|---------|
| `run_typescript_check` | TypeScript 編譯檢查 | 全部 |
| `run_eslint` | ESLint 檢查 | 全部 |
| `run_behavior_validation` | Playwright E2E 驗證 | 全部 |
| `record_tech_debt` | 技術債記錄 | 全部 |
| `read_file` | 讀取檔案 | Claude / OpenAI |
| `list_directory` | 列出目錄 | Claude / OpenAI |
| `search_files` | 全文搜尋 | Claude / OpenAI |
| `write_file` | 寫入檔案 | Claude / OpenAI |

> Copilot SDK 已內建 read_file / glob / grep / edit_file，無需額外工具。

## Testing

```bash
uv run pytest
```

---

**Version**: v4.0.0 | **License**: MIT
