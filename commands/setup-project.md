---
description: 初始化目前專案的 agent-fix 配置。自動偵測框架結構並生成 config.yaml，引導設定 Jira 憑證與測試帳號。不需要傳入路徑：直接在目標專案目錄開啟 Claude Code session，執行此指令即可。
argument-hint: (no arguments needed)
---

# Setup Project

你是 **Agent Fix 初始化助手**。你的任務是讓使用者能夠在 5 分鐘內完成配置，然後執行第一個 `/agent-fix:fix-one-issue`。

## 目標目錄

使用 `$CWD`（Claude Code session 的當前工作目錄）作為目標專案路徑。**不需要使用者傳入路徑**。

---

## Step 1 — 確認目標專案

讀取 `$CWD/package.json`（若存在）確認這是目標專案根目錄。

- 若找不到 `package.json`：詢問使用者「這是目標專案根目錄嗎？還是需要指定子目錄？」
- 若找到：顯示 `✅ 目標專案：<name>（<$CWD>）` 後繼續。

---

## Step 2 — 執行 project-init Skill

執行以下 Task，傳入目前目錄路徑：

```
Task("project-init", "<$CWD>")
```

> project-init skill 會自動偵測框架、monorepo、品質工具、dev server、auth 登入模組，
> 並生成 `config.yaml` 與 `context_sources.md` 到 agent-fix 的 `projects/<slug>/` 目錄。

等待 project-init 完成，取得：
- `config_path`：生成的 config.yaml 路徑（格式：`projects/<slug>/config.yaml`）
- `project_slug`：slug 名稱

顯示：`✅ 配置已生成：<config_path>`

---

## Step 3 — 設定 Issue 來源

讀取生成的 `config_path`，找到 `issue_source.type`：

**若 `type: jira`**：
```
📋 Jira 設定

目前 config.yaml 指定 Jira 為 issue 來源。
請確認 agent-fix 根目錄的 .env 已設定以下變數：

  JIRA_BASE_URL=https://your-company.atlassian.net
  JIRA_USER_EMAIL=your@email.com
  JIRA_API_TOKEN=...  # 在 https://id.atlassian.com/manage-profile/security/api-tokens 取得

已設定的話，輸入 "ok" 繼續。未設定的話，現在幫你寫入 .env？（輸入 Jira URL 或按 Enter 跳過）
```

若使用者提供值 → 寫入 agent-fix 目錄的 `.env`（不覆蓋已存在的值）。

**若 `type: local_json`**：
```
📋 Local JSON 模式

Issues 從 projects/<slug>/issues/ 讀取。
執行前請複製範本並填寫：

  cp schemas/issue_template.json projects/<slug>/issues/ISSUE-001.json
  # 編輯 ISSUE-001.json，填入 summary、description、reproduction_steps 等

繼續設定行為驗證（Playwright）...
```

**若 `type: google_sheets`**：
```
📋 Google Sheets 模式

請確認 .env 已設定 GOOGLE_API_KEY，或在 config.yaml 的 issue_source.options.credentials_file 指定 service account JSON 路徑。

繼續設定行為驗證（Playwright）...
```

---

## Step 4 — 設定行為驗證帳號

讀取生成的 `config_path`，檢查 `behavior_validation.enabled`：

**若 `enabled: true`**：
```
🎭 行為驗證（Playwright）設定

config.yaml 已啟用 Playwright E2E 驗證。需要測試帳號：

  TEST_USERNAME=...   # 測試帳號（建議使用專屬 QA 帳號）
  TEST_PASSWORD=...

已設定的話，輸入 "ok"。現在要設定嗎？（輸入帳號或按 Enter 跳過）
```

若使用者提供值 → 寫入 agent-fix 目錄的 `.env`。

**若 `enabled: false`**：
顯示 `ℹ️ 行為驗證已停用（config.yaml behavior_validation.enabled: false）`，跳過。

---

## Step 5 — 載入配置確認

呼叫 `mcp__agent-fix-tools__set_project_config`：
```
config_path = <config_path from Step 2>
```

- 若回傳 `✅`：顯示成功訊息。
- 若回傳 `❌`：顯示錯誤，引導使用者修正 config.yaml 後重試。

---

## 完成輸出

```
═══════════════════════════════════════════════════════════════
✅ 專案初始化完成！

  專案：<project_name>
  配置：<config_path>

下一步 — 開始修復第一個 Bug：

  /agent-fix:fix-one-issue <ISSUE-ID>

  例：/agent-fix:fix-one-issue CHATAPP-5339

  （同 session 內後續執行不需要再帶 config path）

Batch 模式（Terminal）：

  export PROJECT_CONFIG=<config_path>
  agent-fix --issues CHATAPP-5339
  agent-fix --source jira --jql "project = CHATAPP AND status = 'To Do'"
═══════════════════════════════════════════════════════════════
```
