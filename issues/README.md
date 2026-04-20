# Issue 報告模板

此範本用於建立標準化的 Bug 報告，供 AI Agent 分析使用。

## 使用方式

1. 複製此檔案到 `issues/sources/` 目錄
2. 重新命名為 `{{PROJECT_PREFIX}}-XXXX.json`（如 `BUG-001.json`）
3. 填寫以下資訊

## 範本

```json
{
  "issue_id": "{{PROJECT_PREFIX}}-XXXX",
  "title": "簡短的問題標題",
  "module": "模組名稱 > 子模組",
  "description": "詳細的問題描述",
  "reproduction_steps": [
    "步驟 1: 開啟頁面 /path",
    "步驟 2: 點擊按鈕 X",
    "步驟 3: 觀察結果"
  ],
  "expected": "預期的正確行為",
  "actual": "實際發生的錯誤行為",
  "attachments": [
    {
      "type": "screenshot",
      "path": "issues/screenshots/xxx.png",
      "description": "錯誤截圖"
    }
  ],
  "priority": "High",
  "environment": {
    "browser": "Chrome 120",
    "os": "macOS",
    "device": "Desktop"
  },
  "reporter": "張三",
  "reported_date": "2026-02-04"
}
```

## 欄位說明

| 欄位                 | 類型   | 必填 | 說明                                |
| -------------------- | ------ | ---- | ----------------------------------- |
| `issue_id`           | string | ✅   | Issue ID（格式：{PREFIX}-{NUMBER}） |
| `title`              | string | ✅   | 問題標題                            |
| `module`             | string | ✅   | 問題所在模組                        |
| `description`        | string | ✅   | 詳細描述                            |
| `reproduction_steps` | array  | ✅   | 重現步驟                            |
| `expected`           | string | ✅   | 預期結果                            |
| `actual`             | string | ✅   | 實際結果                            |
| `attachments`        | array  | ❌   | 附件（截圖、日誌等）                |
| `priority`           | string | ❌   | 優先級（High/Medium/Low）           |
| `environment`        | object | ❌   | 環境資訊                            |
| `reporter`           | string | ❌   | 回報者                              |
| `reported_date`      | string | ❌   | 回報日期                            |

## 範例

### 範例 1: 按鈕點擊無反應

```json
{
  "issue_id": "BUG-001",
  "title": "搜尋頁面的「清除」按鈕點擊無反應",
  "module": "搜尋功能 > 搜尋結果頁",
  "description": "在搜尋結果頁面，點擊「清除」按鈕後，搜尋條件沒有被清空，頁面也沒有重新載入。",
  "reproduction_steps": [
    "步驟 1: 開啟搜尋頁面 /search",
    "步驟 2: 輸入關鍵字「測試」並搜尋",
    "步驟 3: 點擊「清除」按鈕",
    "步驟 4: 觀察：搜尋框中的文字沒有被清空"
  ],
  "expected": "點擊「清除」按鈕後，搜尋框應該被清空，並重新載入初始狀態",
  "actual": "點擊按鈕沒有任何反應，搜尋框保持原內容",
  "priority": "High",
  "environment": {
    "browser": "Chrome 120",
    "os": "macOS",
    "device": "Desktop"
  }
}
```

### 範例 2: 資料顯示錯誤

```json
{
  "issue_id": "BUG-002",
  "title": "使用者名單顯示重複資料",
  "module": "使用者管理 > 使用者列表",
  "description": "在使用者列表頁面，當有多個相同姓名的使用者時，會顯示重複的資料行。",
  "reproduction_steps": [
    "步驟 1: 登入系統",
    "步驟 2: 進入「使用者管理」→「使用者列表」",
    "步驟 3: 搜尋姓名「王小明」",
    "步驟 4: 觀察結果"
  ],
  "expected": "應該顯示 2 筆資料（王小明A 和 王小明B）",
  "actual": "顯示 4 筆資料，每個使用者都重複出現 2 次",
  "attachments": [
    {
      "type": "screenshot",
      "path": "issues/screenshots/bug-002-duplicate.png",
      "description": "重複資料截圖"
    }
  ],
  "priority": "Medium"
}
```

## Jira 批次輸入

如果使用 `issue_source.type: jira`，agent 直接從 Jira API 讀取，不需要本地 JSON 檔案。

**設定方式**

1. 在 `.env` 設定認證（一次即可）：

```bash
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_USER_EMAIL=your@email.com
JIRA_API_TOKEN=...  # https://id.atlassian.com/manage-profile/security/api-tokens
```

2. 在 `config.yaml` 設定 JQL：

```yaml
issue_source:
  type: jira
  options:
    jql_base: "project = PROJ AND assignee = currentUser() AND status = 'To Do'"
```

3. 執行：

```bash
# 用 jql_base 條件批次修復
agent-fix batch --config ./projects/my-project.yaml

# 附加本次 sprint / 版本條件（AND 串接）
agent-fix batch --config ./projects/my-project.yaml --filter "sprint = 'Sprint 10'"
agent-fix batch --config ./projects/my-project.yaml --filter "fixVersion = '1.2.0'"

# 預覽清單不執行
agent-fix batch --config ./projects/my-project.yaml --dry-run
```

---

## Google Sheets 批次輸入

如果使用 `issue_source.type: google_sheets`，請以 `issues/SHEETS_TEMPLATE.csv` 建立試算表：

1. Google Sheets → 檔案 → 匯入 → 上傳 `SHEETS_TEMPLATE.csv`
2. 依格式填入所有 issue
3. 在 `config.yaml` 設定 `issue_source.options.sheet_url`
4. 執行 `agent-fix batch` 批次處理

**欄位對應**

| 試算表欄位 | 說明 | 必填 |
|---|---|---|
| `issue_id` | Issue ID（如 BUG-001） | ✅ |
| `summary` | 問題標題 | ✅ |
| `module` | 問題所在模組 | ✅ |
| `description` | 詳細描述 | ✅ |
| `reproduction_steps` | 重現步驟，多步驟以換行（Enter）分隔 | ✅ |
| `expected` | 預期結果 | ✅ |
| `actual` | 實際結果 | ✅ |
| `priority` | High / Medium / Low | ❌ |
| `reporter` | 回報者 | ❌ |
| `reported_date` | 回報日期 | ❌ |

> `status` 欄位值為 `done`、`closed`、`fixed`、`resolved` 時會自動跳過。

---

## 注意事項

1. **Issue ID 格式**: 必須符合專案配置中的 `issue_prefix`
   - 範例：如果 `issue_prefix: "BUG"`，則為 `BUG-001`, `BUG-002`, ...
   - 範例：如果 `issue_prefix: "PROJ"`，則為 `PROJ-001`, `PROJ-002`, ...

2. **重現步驟**: 越詳細越好，包含：
   - URL 路徑
   - 點擊元素的名稱/位置
   - 輸入的資料
   - 預期看到的結果

3. **附件**: 如果有截圖或日誌，務必附上
   - 截圖放在 `issues/screenshots/` 目錄
   - 在 `attachments` 欄位中引用

4. **環境資訊**: 有助於分析環境相關問題
   - 瀏覽器版本
   - 作業系統
   - 裝置類型（Desktop/Mobile）

5. **優先級**: 根據影響程度決定
   - **High**: 嚴重影響功能，需立即修復
   - **Medium**: 影響使用體驗，但有替代方案
   - **Low**: 小問題，不影響主要功能
