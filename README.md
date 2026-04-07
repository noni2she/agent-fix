# Bugfix Workflow

通用 AI Bug 修復工作流程引擎，支援 Next.js + Monorepo 專案的自動化 Bug 分析與修復。

## ✨ 特色

- **配置驅動**：使用 YAML 配置檔案定義專案結構，無硬編碼
- **通用架構**：支援多種 Next.js + Monorepo 專案（Turborepo, Yarn Workspaces 等）
- **AI 驅動**：整合 GitHub Copilot + LangGraph 進行智能分析與修復
- **嚴格驗證**：使用 Pydantic 確保 Agent 輸出品質
- **行為驗證**：內建 Playwright 支援端到端驗證

## 🚀 快速開始

### 方式一：使用 CLI 工具（推薦）

```bash
# 1. 檢查並安裝依賴
python3 cli.py check-deps --fix

# 2. 初始化專案配置
python3 cli.py init \
  --project-name my-project \
  --project-root /path/to/project \
  --workspace web

# 3. 驗證配置
python3 cli.py validate ./config.yaml

# 4. 設定環境變數
export PROJECT_CONFIG=./config.yaml

# 5. 準備 Bug 報告
cp issues/TEMPLATE.json issues/sources/BUG-001.json
vim issues/sources/BUG-001.json

# 6. 執行修復
python3 cli.py run BUG-001
```

### 方式二：手動設定

```bash
# 1. 安裝相依套件
pip install -e .
playwright install chromium

# 2. 複製並編輯配置檔案
cp config-template.yaml config/my-project.yaml
vim config/my-project.yaml

# 3. 配置環境變數
export PROJECT_CONFIG=./config/my-project.yaml

# 4. 準備 Bug 報告
cp issues/TEMPLATE.json issues/sources/BUG-001.json
vim issues/sources/BUG-001.json

# 5. 執行工作流程
python main.py BUG-001
```

### CLI 工具詳細說明

詳見 [CLI 使用指南](docs/CLI_USAGE.md)

## 📁 專案結構

```
bugfix-workflow/
├── cli.py                       # CLI 工具（新）
├── main.py                      # 主程式入口
├── config-template.yaml         # 配置範本
├── .env.example                 # 環境變數範本
├── examples/                    # 配置範例
│   ├── morse-webapp.yaml        # Turborepo 範例
│   └── minimal-nextjs.yaml      # 單一專案範例
├── engine/                      # 核心引擎
│   ├── config.py                # 配置系統（通用化）
│   ├── project_spec.py          # 專案規格（通用化）
│   ├── models.py                # 資料模型
│   ├── validators.py            # 驗證器
│   ├── tools.py                 # 工具函式（參數化）
│   ├── tools_behavior_validation.py  # 行為驗證工具（參數化）
│   └── agent_runner.py          # Agent 執行器（通用化）
├── specs/agents/                # Agent 規格（通用化）
│   ├── analyst.md               # 分析師
│   ├── engineer.md              # 工程師
│   └── tester.md                # 測試員
├── issues/                      # Bug 報告
│   ├── TEMPLATE.json            # 報告範本
│   ├── sources/                 # 原始報告
│   └── reports/                 # 產生的報告
└── docs/                        # 文檔
    └── CLI_USAGE.md             # CLI 使用指南
```

## ⚙️ 配置說明

### 最小配置範例

```yaml
project_name: "my-project"
framework: "nextjs-15-app-router"
language: "typescript"
issue_prefix: "BUG"

paths:
  root: "../my-project"
  shared_components:
    - "src/components/"
  isolated_modules:
    - "src/app/"

quality_checks:
  typescript:
    command: "npm run type-check"
    enabled: true
  eslint:
    command: "npm run lint"
    enabled: true
```

### 完整配置選項

請參考 [config-template.yaml](config-template.yaml) 查看所有可用選項。

## 🔧 使用指南

### Analyst（分析師）

自動分析 Bug 的根本原因、影響範圍和修復策略。

**輸出**：

- 根本原因檔案和行號
- 影響範圍評估
- 建議修復策略（Direct/Tactical）

### Engineer（工程師）

根據 Analyst 的分析執行修復，並遵循專案規範。

**功能**：

- 自動建立 Git 分支
- 修改程式碼
- 提交變更

### Tester（測試員）

驗證修復是否正確，包含靜態檢查和行為驗證。

**檢查項目**：

- TypeScript 型別檢查
- ESLint 程式碼檢查
- 策略遵守檢查
- 行為驗證（可選，使用 Playwright）

## 🎯 支援的專案類型

### 目前支援

- ✅ Next.js 15 App Router + Turborepo
- ✅ Next.js 14/13 + Yarn Workspaces
- ✅ Next.js 單一專案

### 規劃支援

- 🔄 React + Vite + Monorepo
- 🔄 Vue 3 + Monorepo
- 🔄 其他前端框架

## 📊 自訂化

### 1. 擴展工具函式

在 `engine/tools.py` 中新增工具函式，並註冊到 `TOOL_MAP`。

### 2. 自訂 Agent 規格

編輯 `specs/agents/*.md` 檔案調整 Agent 行為。

### 3. 新增 Skills

在專案的 `.github/skills/` 目錄新增 skill，並在配置中引用：

```yaml
skills:
  directories:
    - "../my-project/.github/skills"
```

## 🧪 測試

````bash
# 執行所有測試
pytest

# 執行特定測試
pytest tests/test_config.py
� CLI 命令

### `init` - 初始化專案配置

```bash
python3 cli.py init \
  --project-name my-app \
  --project-root /path/to/project \
  --workspace web \
  --issue-prefix BUG
````

### `validate` - 驗證配置檔案

```bash
python3 cli.py validate ./config.yaml
python3 cli.py validate ./config.yaml --strict
```

### `check-deps` - 檢查依賴套件

```bash
python3 cli.py check-deps
python3 cli.py check-deps --fix
```

### `run` - 執行 Bug 修復流程

```bash
python3 cli.py run BUG-001
python3 cli.py run BUG-001 --config ./config.yaml
```

詳見 **[CLI 使用指南](docs/CLI_USAGE.md)** 了解更多。

## 📚 文檔

- **[CLI 使用指南](docs/CLI_USAGE.md)** - 詳細的 CLI 工具使用說明
- **[快速開始指南](QUICK_START.md)** - 5 分鐘快速上手
- **[配置範本](config-template.yaml)** - 完整的配置選項說明

## 📝 變更日誌

### v1.0.0 (2026-02-04)

**重大更新：通用化重構完成**

- ✨ **新功能：CLI 工具** - 提供 init, validate, check-deps, run 命令
- ✅ **配置驅動架構** - YAML 配置系統，無硬編碼
- ✅ **支援 Next.js + Monorepo** - Turborepo, Yarn Workspaces 等
- ✅ **工具參數化** - 所有路徑和設定從配置讀取
- ✅ **Agent Specs 通用化** - 移除專案特定範例
- ✅ **完整文檔** - CLI 使用指南與快速開始

## 📄 授權

MIT License - 詳見 [LICENSE](LICENSE)

## 💬 支援

有問題或建議？請開 Issue 或聯繫維護者。

---

**Note**: 本專案從 `ai-bugfix-workflow` 重構而來，專注於通用性和可維護性。
