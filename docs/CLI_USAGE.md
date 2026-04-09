# Bugfix Workflow CLI 使用指南

## 概述

`cli.py` 是 Bugfix Workflow 的命令列工具，提供專案初始化、配置驗證、依賴檢查等功能。

## 安裝

```bash
# 1. 複製專案
git clone <repository-url>
cd bugfix-workflow

# 2. 安裝依賴（選擇 SDK）
uv sync --extra copilot   # GitHub Copilot（預設）
uv sync --extra claude    # Anthropic Claude
uv sync --extra openai    # OpenAI Agents
```

## 可用命令

### 1. `init` - 初始化專案配置

為您的專案建立配置檔案。

#### 基本用法

```bash
python3 cli.py init \
  --project-name my-nextjs-app \
  --project-root /path/to/project \
  --output ./config.yaml
```

#### 完整選項

```bash
python3 cli.py init \
  --project-name my-nextjs-app \          # 專案名稱 (必須)
  --project-root /path/to/project \       # 專案根目錄 (必須)
  --workspace web \                       # Monorepo workspace 名稱 (可選)
  --issue-prefix JIRA \                   # Issue ID 前綴 (預設: BUG)
  --output ./config.yaml \                # 輸出路徑 (預設: ./config.yaml)
  --template minimal                      # 模板類型 (minimal, full, turborepo)
```

#### 範例

**單一應用專案**：

```bash
python3 cli.py init \
  --project-name my-app \
  --project-root /Users/john/projects/my-app \
  --issue-prefix TASK
```

**Monorepo 專案**：

```bash
python3 cli.py init \
  --project-name my-monorepo \
  --project-root /Users/john/projects/my-monorepo \
  --workspace main-web \
  --issue-prefix BUG \
  --template full
```

**使用 turborepo 範例**：

```bash
python3 cli.py init \
  --project-name my-turborepo-app \
  --project-root /path/to/project \
  --workspace web \
  --template turborepo
```

輸出範例：

```
🚀 Bugfix Workflow - 初始化專案配置

📁 專案名稱: my-nextjs-app
📂 專案路徑: /Users/john/projects/my-app
🏗️  專案類型: 單一應用
🏷️  Issue 前綴: BUG

✅ 配置檔案已建立: ./config.yaml

📝 下一步：
   1. 編輯配置檔案: ./config.yaml
   2. 驗證配置: python3 cli.py validate ./config.yaml
   3. 設定環境變數: export PROJECT_CONFIG=./config.yaml
   4. 執行修復: python main.py <issue-id>
```

---

### 2. `validate` - 驗證配置檔案

檢查配置檔案的語法和內容是否正確。

#### 基本用法

```bash
python3 cli.py validate ./config.yaml
```

#### 完整選項

```bash
python3 cli.py validate ./config.yaml --strict
```

選項說明：

- `--strict`: 嚴格模式，將警告視為錯誤

#### 輸出範例

**成功**：

```
🔍 驗證配置檔案...

✅ 配置檔案語法正確

📋 配置摘要:
  專案名稱: my-nextjs-app
  框架: Next.js 15
  專案根目錄: /Users/john/projects/my-app
  Issue 前綴: BUG
  Monorepo: 是
    主 workspace: web
    工具: turborepo

✅ 配置驗證通過
```

**有警告**：

```
⚠️  發現 2 個警告：
  1. 路徑不存在: apps/web/src/app
  2. Skills 目錄不存在: .github/skills
```

**錯誤**：

```
❌ 配置錯誤: Missing required field: project_name
```

---

### 3. `check-deps` - 檢查依賴套件

檢查系統是否已安裝所有必要的 Python 套件。

#### 基本用法

```bash
python3 cli.py check-deps
```

#### 自動修復

```bash
python3 cli.py check-deps --fix
```

#### 輸出範例

**檢查結果**：

```
🔍 檢查依賴套件...

  ✅ pydantic             - Pydantic (配置驗證)
  ✅ yaml                 - PyYAML (YAML 解析)
  ❌ langchain_core       - LangChain Core (Agent 框架)
  ✅ langgraph            - LangGraph (工作流程)
  ✅ playwright           - Playwright (瀏覽器測試)

📊 統計: 4/5 已安裝

⚠️  缺少 1 個依賴套件

💡 提示：使用 --fix 選項自動安裝
   或手動安裝: pip install langchain_core
```

**自動安裝**：

```bash
python3 cli.py check-deps --fix

# 輸出：
🔧 自動安裝缺少的依賴...
Collecting langchain_core
  ...
✅ 依賴套件安裝完成
```

---

### 4. `run` - 執行 Bug 修復流程

執行完整的 Bug 修復工作流程。

#### 基本用法

```bash
# 方法 1: 使用環境變數
export PROJECT_CONFIG=./config.yaml
python3 cli.py run BUG-001

# 方法 2: 使用 --config 選項
python3 cli.py run BUG-001 --config ./config.yaml
```

#### 完整選項

```bash
python3 cli.py run <issue-id> [--config <config-file>]
```

參數說明：

- `<issue-id>`: Issue ID（必須），例如：BUG-001
- `--config, -c`: 配置檔案路徑（可選，預設從 `PROJECT_CONFIG` 環境變數讀取）

#### 執行前檢查

```bash
# 1. 驗證配置
python3 cli.py validate ./config.yaml

# 2. 檢查依賴
python3 cli.py check-deps

# 3. 設定環境變數
export PROJECT_CONFIG=./config.yaml

# 4. 執行修復
python3 cli.py run BUG-001
```

---

## 完整工作流程範例

### 情境：為新專案設定 Bugfix Workflow

```bash
# 步驟 1: 初始化配置
python3 cli.py init \
  --project-name awesome-app \
  --project-root /Users/john/projects/awesome-app \
  --workspace web \
  --issue-prefix JIRA \
  --output ./awesome-app-config.yaml

# 輸出：
# ✅ 配置檔案已建立: ./awesome-app-config.yaml

# 步驟 2: 編輯配置（根據專案需求調整）
vim ./awesome-app-config.yaml

# 步驟 3: 驗證配置
python3 cli.py validate ./awesome-app-config.yaml

# 輸出：
# ✅ 配置驗證通過

# 步驟 4: 檢查並安裝依賴
python3 cli.py check-deps --fix

# 輸出：
# ✅ 所有依賴套件已安裝

# 步驟 5: 設定環境變數
export PROJECT_CONFIG=./awesome-app-config.yaml

# 步驟 6: 準備 Issue 檔案
mkdir -p issues/sources
cp issues/TEMPLATE.json issues/sources/JIRA-001.json
vim issues/sources/JIRA-001.json

# 步驟 7: 執行 Bug 修復
python3 cli.py run JIRA-001

# 或直接使用 main.py
python main.py JIRA-001
```

---

## 環境變數

### `PROJECT_CONFIG`

指定配置檔案路徑。

```bash
export PROJECT_CONFIG=/path/to/config.yaml
```

使用這個環境變數可以避免每次執行都需要指定 `--config` 選項。

---

## 疑難排解

### 問題 1: `ModuleNotFoundError: No module named 'yaml'`

**原因**: 缺少 PyYAML 套件

**解決方法**:

```bash
pip install PyYAML
# 或使用
python3 cli.py check-deps --fix
```

### 問題 2: 配置驗證失敗

**原因**: 配置檔案格式錯誤或缺少必要欄位

**解決方法**:

1. 檢查錯誤訊息中的具體問題
2. 參考 `config-template.yaml` 或 `examples/` 中的範例
3. 使用 YAML 驗證工具檢查語法

### 問題 3: `PROJECT_CONFIG` 環境變數未設定

**錯誤訊息**:

```
❌ 錯誤：未設定 PROJECT_CONFIG 環境變數
```

**解決方法**:

```bash
export PROJECT_CONFIG=./config.yaml
# 或在執行時指定
python3 cli.py run BUG-001 --config ./config.yaml
```

### 問題 4: 專案路徑不存在

**錯誤訊息**:

```
❌ 錯誤：專案路徑不存在: /path/to/project
```

**解決方法**:

1. 確認專案路徑正確
2. 使用絕對路徑
3. 檢查路徑拼寫

---

## 進階用法

### 批次處理多個 Issue

```bash
#!/bin/bash
# fix-batch.sh

export PROJECT_CONFIG=./config.yaml

for issue_id in BUG-001 BUG-002 BUG-003; do
  echo "處理 $issue_id..."
  python3 cli.py run $issue_id
  echo "---"
done
```

### 自動化 CI/CD 整合

```yaml
# .github/workflows/bugfix.yml
name: Auto Bugfix

on:
  issues:
    types: [labeled]

jobs:
  fix:
    if: contains(github.event.issue.labels.*.name, 'auto-fix')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: python3 cli.py check-deps --fix

      - name: Run bugfix
        env:
          PROJECT_CONFIG: ./config.yaml
        run: |
          python3 cli.py run ${{ github.event.issue.number }}
```

---

## 參考資料

- [配置檔案範例](../config-template.yaml)
- [Turborepo 配置範例](../examples/turborepo-nextjs.yaml)
- [最小 Next.js 配置範例](../examples/minimal-nextjs.yaml)
- [主要 README](../README.md)
