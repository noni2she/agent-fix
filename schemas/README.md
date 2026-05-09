# schemas/

此目錄存放 agent-bugfix pipeline 使用的通用 schema 與範本。

## 檔案

| 檔案 | 說明 |
|------|------|
| `issue_template.json` | 本地 issue 標準格式。放入 `projects/<slug>/issues/sources/` 並重命名為 issue ID（如 `PROJ-001.json`）。 |
| `sheets_template.csv` | Google Sheets 批次輸入格式。匯入試算表後填入 issue，對應 `issue_source.type: google_sheets`。 |
| `config_turborepo_example.yaml` | Turborepo + Next.js 專案的 `config.yaml` 範例，供 project-init 參考。 |

## Issue 來源

Pipeline 支援三種 issue 來源，在各專案的 `config.yaml` 中設定 `issue_source.type`：

| 類型 | 說明 |
|------|------|
| `local_json` | 本地 JSON 檔案，放入 `projects/<slug>/issues/sources/`，格式參考 `issue_template.json` |
| `jira` | 透過 Jira API 讀取，設定 `jql_base` 篩選條件 |
| `google_sheets` | 透過 Google Sheets 讀取，格式參考 `sheets_template.csv` |

外部來源（Jira / GitHub Issues）由 `issue-extract` subagent 自動轉換為統一格式，無需手動處理。
