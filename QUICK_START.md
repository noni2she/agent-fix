# ⚡ 5 分鐘快速開始指南

這份指南將幫助你在 5 分鐘內完成第一個 Bug 的自動修復流程。

## 前置需求

- Python 3.13+
- 專案使用 Next.js 或類似架構
- GitHub Copilot 訂閱（用於 Agent 執行）

## 步驟 1：安裝依賴（1 分鐘）

```bash
cd /path/to/bugfix-workflow

# 自動檢查並安裝所有依賴
python3 cli.py check-deps --fix
```

這會自動安裝 LangGraph、Copilot SDK、Playwright 等所有必要套件。

## 步驟 2：初始化配置（1 分鐘）

```bash
# 為你的專案生成配置檔案
python3 cli.py init \
  --project-name my-app \
  --project-root /path/to/your/project \
  --workspace web \
  --issue-prefix BUG \
  --output ./config.yaml

# 設定環境變數
export PROJECT_CONFIG=./config.yaml
```

## 步驟 3：驗證配置（30 秒）

```bash
# 檢查配置是否正確
python3 cli.py validate ./config.yaml

# 如果看到 "✅ 配置檔案驗證通過"，表示成功！
```

## 步驟 4：準備 Bug 報告（1 分鐘）

```bash
# 複製範本
cp issues/TEMPLATE.json issues/sources/BUG-001.json

# 編輯 Bug 資訊
nano issues/sources/BUG-001.json
```

最小化範例：

```json
{
  "metadata": {
    "id": "BUG-001",
    "title": "修復按鈕顏色錯誤",
    "priority": "high",
    "reporter": "developer@example.com"
  },
  "description": "登入頁面的按鈕顏色應該是藍色但顯示為紅色",
  "steps_to_reproduce": ["開啟 http://localhost:3000/login", "查看登入按鈕"],
  "expected_behavior": "按鈕應該是藍色 (#3B82F6)",
  "actual_behavior": "按鈕顯示為紅色",
  "affected_files": ["src/app/login/page.tsx"]
}
```

## 步驟 5：執行修復（1-2 分鐘）

```bash
# 執行自動修復工作流程
python3 cli.py run BUG-001
```

工作流程會：

1. 🔍 **Analyst** 分析 Bug 和相關檔案
2. 🛠️ **Engineer** 實作修復
3. ✅ **Tester** 驗證修復

## 步驟 6：檢查結果（30 秒）

```bash
# 查看生成的報告
cat issues/reports/BUG-001_validation.json

# 查看驗證報告
cat issues/reports/BUG-001_verification.md
```

如果看到 `"status": "success"`，恭喜！你的第一個 Bug 已自動修復 🎉

## 🚀 下一步

### 進階配置

如果需要更精細的控制，編輯 `config.yaml`：

```yaml
# 開啟詳細日誌
debug: true

# 調整 Playwright 設定
behavior_validation:
  headless: false # 看到瀏覽器執行過程
  timeout: 60000 # 增加超時時間

# 自訂工作流程
workflow:
  max_iterations: 5
  auto_commit: true
  create_pr: true
```

### 整合到 CI/CD

```yaml
# .github/workflows/bugfix.yml
name: Auto Bug Fix
on:
  issues:
    types: [labeled]

jobs:
  fix:
    if: contains(github.event.issue.labels.*.name, 'auto-fix')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Run Bugfix Workflow
        run: |
          python3 cli.py check-deps --fix
          python3 cli.py run ${{ github.event.issue.number }}
```

### 探索更多功能

- **[CLI 完整指南](docs/CLI_USAGE.md)** - 所有命令的詳細說明
- **[配置選項](config-template.yaml)** - 完整的配置參考
- **[README](README.md)** - 專案概覽與完整功能說明

## ❓ 疑難排解

### 問題：`ModuleNotFoundError: No module named 'langgraph'`

```bash
# 重新執行依賴安裝
python3 cli.py check-deps --fix
```

### 問題：`playwright executable doesn't exist`

```bash
# 手動安裝 Playwright 瀏覽器
playwright install chromium
```

### 問題：`Environment variable PROJECT_CONFIG not set`

```bash
# 設定環境變數
export PROJECT_CONFIG=./config.yaml

# 或在 .env 檔案中設定
echo "PROJECT_CONFIG=./config.yaml" >> .env
```

### 問題：Agent 執行失敗

1. 檢查是否有 GitHub Copilot 訂閱
2. 驗證配置檔案：`python3 cli.py validate --strict`
3. 啟用除錯模式：在 config.yaml 設定 `debug: true`

## 💡 小提示

- **批次處理**：使用萬用字元執行多個 Bug：`python3 cli.py run "BUG-*"`
- **自訂範本**：複製 `issues/TEMPLATE.json` 並修改為你的專案範本
- **配置範例**：查看 `examples/` 資料夾中的實際專案配置

---

**需要更多幫助？** 查看 [完整 README](README.md) 或 [開 Issue](https://github.com/your-repo/issues)
