---
name: issue-extract
description: 識別外部 issue source 格式（Jira / GitHub Issues），萃取欄位並轉換為 pipeline 統一的 TEMPLATE.json 格式。
argument-hint: <raw issue JSON>
user-invocable: false
---

# Issue 格式萃取

## 職責

接收外部 issue tracker 的原始 JSON，識別來源，映射欄位，輸出標準 TEMPLATE.json。

**不做**：欄位內容驗證、issue 品質評估、任何分析——只做格式轉換。

> **使用本地 issue 時**：若 issue 已按照 `issues/TEMPLATE.json` 格式建立並放置於 `issues/sources/`，Orchestrator 應直接使用，不需呼叫此 subagent。

## 來源識別

| 特徵 | 判斷來源 |
|------|---------|
| 有 `fields` 包裹層 + `key` 符合 `[A-Z]+-\d+` 格式 | Jira |
| 有 `html_url` 包含 `github.com/.*/issues/` 或有 `number` + `body` + `user.login` | GitHub Issues |
| 有 `identifier` 欄位（格式如 `TEAM-123`）+ `team` 物件 | Linear（預留，尚未實作） |
| 其他 | 未知來源 → 輸出 error |

## 欄位映射

### Jira

| TEMPLATE 欄位 | Jira 來源 | 備注 |
|--------------|-----------|------|
| `issue_id` | `key`（根層級） | 如 `PROJ-123` |
| `summary` | `fields.summary` | |
| `module` | 從 `fields.description` 解析位置/頁面欄位 | 見 description 解析規則 |
| `description` | `fields.description` 原文 | 保留完整原文 |
| `reproduction_steps` | 從 `fields.description` 解析重現步驟欄位 | 依分隔符切分為陣列 |
| `expected` | 從 `fields.description` 解析預期結果欄位 | |
| `actual` | 從 `fields.description` 解析實際結果欄位 | |
| `attachments` | `fields.attachment[]` | 見 Attachment 格式 |
| `comments` | `fields.comment.comments[].body` | 若 `fields.comment.total > 0` |

**丟棄**：`priority`、`reporter`、`creator`、`assignee`、`status`、`customfield_*`

**Jira description 解析規則**：

Jira description 通常包含 `**欄位名**:` 結構化格式。以語義識別對應欄位：
- 位置 / 頁面 / 功能路徑 → `module`
- 重現步驟 / 操作步驟 → `reproduction_steps`（依 `>`、換行或數字序號切分為陣列）
- 預期結果 / 期望行為 → `expected`
- 實際結果 / 實際行為 → `actual`

若 description 中找不到對應欄位，填空字串 `""`。

---

### GitHub Issues

GitHub Issues 格式較自由，分兩種路徑：

**有結構**（body 包含 `## Steps to Reproduce`、`## Expected`、`## Actual` 等 heading）：
→ 依 heading 切分，直接映射對應欄位

**無結構**（自由文字）：
→ LLM 語義萃取，盡力識別重現步驟、預期、實際結果

| TEMPLATE 欄位 | GitHub 來源 | 備注 |
|--------------|------------|------|
| `issue_id` | `"{owner}/{repo}#{number}"` | 從 `html_url` 萃取 owner/repo |
| `summary` | `title` | |
| `module` | `labels[]` 中第一個非通用 label（排除 `bug`、`enhancement`、`question` 等） | 若無則 `""` |
| `description` | `body` 原文 | |
| `reproduction_steps` | 解析 body 或 LLM 語義萃取 | |
| `expected` | 解析 body 或 LLM 語義萃取 | |
| `actual` | 解析 body 或 LLM 語義萃取 | |
| `attachments` | 從 body Markdown 萃取圖片 URL（`![...](url)` 格式） | |
| `comments` | 若 `comments > 0`，需額外呼叫 `comments_url` API | |

> 建立本地 GitHub Issue 時，建議參考 `issues/TEMPLATE.json` 格式撰寫 issue body，可提升萃取準確率。

---

### Linear（預留擴充）

尚未實作。新增時：
1. 在「來源識別」表格加入 Linear 特徵
2. 在此新增 Linear 欄位映射章節

---

## Attachment 格式

```json
{
  "type": "<screenshot | video | document>",
  "path": "<content URL>",
  "description": "<filename>"
}
```

`type` 根據 mimeType 判斷：`image/*` → `screenshot`；`video/*` → `video`；其他 → `document`

**只保留 URL，不下載、不 base64。**

## 輸出格式

標準 TEMPLATE.json，所有欄位必須存在（無法映射時填 `""` 或 `[]`）。

無法識別來源時輸出：
```json
{
  "error": "unknown_source",
  "raw": "<原始輸入>"
}
```

## 注意事項

1. **只做格式轉換**：不評估 issue 品質，不補充推測內容
2. **description 保留原文**：即使已萃取結構化欄位，`description` 仍保留完整原始描述
3. **無法映射的欄位**：填 `""` 或 `[]`，不省略欄位
4. **attachments 只保留 URL**：不下載
