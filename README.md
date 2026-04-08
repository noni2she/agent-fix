# Bugfix Workflow

> 通用 AI Bug 修復工作流程引擎 — Skill-Based，支援 Copilot / Claude / OpenAI SDK。

## Features

- **配置驅動** — 使用 YAML 定義專案結構，支援任意 Next.js + Monorepo 專案
- **Skill-Based 架構** — 以 SKILL.md 定義行為，流程邏輯與專案細節分離
- **多 SDK 支援** — GitHub Copilot / Anthropic Claude / OpenAI Agents（一行切換）
- **動態 Project Context** — 從 config.yaml 生成專案 context，注入每個 phase
- **Smart Retry** — 測試失敗自動回到 implement 重修（最多 3 次）
- **Token 優化** — analyze + implement 共用 session，test 獨立 session

## Architecture

```
bugfix-workflow/
├── main.py                    # Workflow 主入口（Python loop）
├── cli.py                     # CLI 工具（bfw run / init / validate）
├── config-template.yaml       # 專案配置範本
├── examples/                  # 配置範例
│   ├── morse-webapp.yaml      # Turborepo + Yarn Workspace
│   └── minimal-nextjs.yaml   # 單一 Next.js 專案
├── engine/
│   ├── config.py              # ProjectConfig（Pydantic YAML 驗證）
│   ├── project_spec.py        # ProjectSpec（TACTICAL 判斷邏輯）
│   ├── agent_runner.py        # Session 管理，透過 adapters 操作 SDK
│   ├── skill_loader.py        # 讀取 SKILL.md（frontmatter + body）
│   ├── tools.py               # 自訂工具（tsc/eslint check + tech debt）
│   ├── adapters/
│   │   ├── base.py            # AgentEvent / AgentSession / AgentAdapter ABC
│   │   ├── copilot_adapter.py # GitHub Copilot SDK
│   │   ├── claude_adapter.py  # Anthropic Claude SDK
│   │   └── openai_adapter.py  # OpenAI Agents SDK
│   └── __init__.py
├── skills/                    # 通用 bugfix skills（流程邏輯）
│   ├── bugfix-analyze/SKILL.md
│   ├── bugfix-implement/SKILL.md
│   └── bugfix-test/SKILL.md
└── issues/
    ├── TEMPLATE.json          # Issue 報告範本
    ├── sources/               # Bug 報告 JSON（輸入）
    └── reports/<issue-id>/    # 各 Phase 報告 Markdown（輸出）
```

### Workflow

```
analyze ──→ implement ──→ test ──→ PASS → done
  (共用 session)           │
                          FAIL
                           │
                    implement-retry ──→ test（最多 3 次）
```

### Project Context 生成

```
config.yaml → load_project_context() → 動態生成 Markdown
                ↓
每個 phase prompt = project_context + generic_skill_body
```

## Quick Start

### 安裝

```bash
# 安裝 uv（推薦）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安裝（選擇 SDK）
uv sync --extra copilot   # GitHub Copilot（預設）
uv sync --extra claude    # Anthropic Claude
uv sync --extra openai    # OpenAI Agents
uv sync --extra all       # 全部安裝
```

### 設定專案

```bash
# 初始化配置
python cli.py init \
  --project-name my-project \
  --project-root /path/to/project \
  --workspace web

# 或直接複製範本
cp config-template.yaml config/my-project.yaml
# 編輯 config/my-project.yaml

# 驗證配置
python cli.py validate config/my-project.yaml
```

### 執行修復

```bash
# 設定環境
cp .env.example .env
# 編輯 .env：PROJECT_CONFIG, SDK_ADAPTER

# 建立 Bug 報告
cp issues/TEMPLATE.json issues/sources/BUG-001.json

# 執行
python main.py BUG-001
# 或用 CLI
python cli.py run BUG-001
```

### 切換 SDK

```bash
# 只需改一個環境變數
export SDK_ADAPTER=claude   # 切換到 Anthropic Claude
export SDK_ADAPTER=openai   # 切換到 OpenAI Agents
export SDK_ADAPTER=copilot  # 切換回 GitHub Copilot（預設）
```

## Configuration

### config.yaml 範例

```yaml
project_name: "my-project"
framework: "nextjs-15-app-router"
issue_prefix: "BUG"

paths:
  root: "../my-project"
  shared_packages: ["packages/"]
  shared_components: ["apps/web/src/components/"]
  isolated_modules: ["apps/web/src/app/"]

high_risk_keywords: ["auth", "store", "websocket"]

quality_checks:
  typescript:
    command: "yarn workspace web tsc --noEmit"
  eslint:
    command: "yarn workspace web lint"

skills:
  directories: []  # 留空使用內建 skills/

monorepo:
  tool: "yarn-workspaces"
  main_workspace: "web"
```

詳見 [config-template.yaml](config-template.yaml) 查看所有選項。

## Custom Tools

| 工具 | 封裝價值 |
|------|---------|
| `run_typescript_check` | 讀 config 指令 + timeout + 錯誤摘要 |
| `run_eslint` | 讀 config 指令 + timeout + warning/error 判斷 |
| `record_tech_debt` | JSON 持久化 |

## Testing

```bash
uv run pytest
```

## Roadmap

- [ ] 通用 skills 在不同專案架構下的適用性驗證
- [ ] Plugin 格式發佈（Claude Code marketplace）

---

**Version**: v3.1.0
**License**: MIT
