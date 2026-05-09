---
name: issue-extract
description: 識別外部 issue source 格式（Jira / GitHub Issues），萃取欄位並轉換為 pipeline 統一的標準欄位格式（issue_id / summary / module / description / reproduction_steps / expected / actual / attachments / comments）。
argument-hint: <raw issue JSON>
user-invocable: false
inject-agents-md: false
---

# Issue 格式萃取

## 職責

接收外部 issue tracker 的原始 JSON，識別來源，映射欄位，輸出標準欄位格式（見「輸出格式」章節的欄位定義）。

**不做**：欄位內容驗證、issue 品質評估、任何分析——只做格式轉換。

## 來源識別

| 特徵                                                                             | 判斷來源                 |
| -------------------------------------------------------------------------------- | ------------------------ |
| 有 `fields` 包裹層 + `key` 符合 `[A-Z]+-\d+` 格式                                | Jira                     |
| 有 `html_url` 包含 `github.com/.*/issues/` 或有 `number` + `body` + `user.login` | GitHub Issues            |
| 有 `identifier` 欄位（格式如 `TEAM-123`）+ `team` 物件                           | Linear（預留，尚未實作） |
| 其他                                                                             | 未知來源 → 輸出 error    |

## 欄位映射

### Jira

| 輸出欄位             | Jira 來源                                     | 備注                                  |
| -------------------- | --------------------------------------------- | ------------------------------------- |
| `issue_id`           | `key`（根層級）                               | 如 `CHATAPP-5339`                     |
| `summary`            | `fields.summary`                              |                                       |
| `module`             | 從 `fields.description` 解析 `**頁面/位置**:` |                                       |
| `description`        | `fields.description` 原文                     | 保留完整原文，含所有 `**欄位**:` 標記 |
| `reproduction_steps` | 從 `fields.description` 解析 `**重現步驟**:`  | 依 `>` 或換行切分為陣列               |
| `expected`           | 從 `fields.description` 解析 `**預期結果**:`  |                                       |
| `actual`             | 從 `fields.description` 解析 `**實際結果**:`  |                                       |
| `attachments`        | `fields.attachment[]`                         | 見 Attachment 格式                    |
| `comments`           | `fields.comment.comments[].body`              | 若 `fields.comment.total > 0`         |

**丟棄**：`priority`、`reporter`、`creator`、`assignee`、`status`、`customfield_*`、description 中的 `**版號**:`

**Jira description 解析規則**（公司固定格式）：

```
**版號**: ...           → 丟棄
**頁面/位置**: 發布      → module: "發布"
**重現步驟**: A>B>C>D   → reproduction_steps: ["A", "B", "C", "D"]
**預期結果**: ...        → expected: "..."
**實際結果**: ...        → actual: "..."
```

若 description 中找不到對應 `**欄位**:` 標記，該欄位填空字串 `""`。

---

### GitHub Issues

GitHub Issues 格式較自由，分兩種路徑：

**有結構**（body 包含 `## Steps to Reproduce`、`## Expected`、`## Actual` 等 heading）：
→ 依 heading 切分，直接映射對應欄位

**無結構**（自由文字）：
→ LLM 語義萃取，盡力識別重現步驟、預期、實際結果

| 輸出欄位             | GitHub 來源                                                                 | 備注                          |
| -------------------- | --------------------------------------------------------------------------- | ----------------------------- |
| `issue_id`           | `"{owner}/{repo}#{number}"`                                                 | 從 `html_url` 萃取 owner/repo |
| `summary`            | `title`                                                                     |                               |
| `module`             | `labels[]` 中第一個非通用 label（排除 `bug`、`enhancement`、`question` 等） | 若無則 `""`                   |
| `description`        | `body` 原文                                                                 |                               |
| `reproduction_steps` | 解析 body 或 LLM 語義萃取                                                   |                               |
| `expected`           | 解析 body 或 LLM 語義萃取                                                   |                               |
| `actual`             | 解析 body 或 LLM 語義萃取                                                   |                               |
| `attachments`        | 從 body Markdown 萃取圖片 URL（`![...](url)` 格式）                         |                               |
| `comments`           | 若 `comments > 0`，需額外呼叫 `comments_url` API                            |                               |

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

**回覆格式要求：只輸出一個 fenced \`\`\`json block，block 外不加任何說明文字。**

輸出必須包含以下所有欄位（無法映射時填 `""` 或 `[]`，不可省略欄位）：

```json
{
  "issue_id": "...",
  "summary": "...",
  "module": "...",
  "description": "...",
  "reproduction_steps": [],
  "expected": "...",
  "actual": "...",
  "attachments": [],
  "comments": []
}
```

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
