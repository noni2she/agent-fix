---
name: bugfix-analyze
description: 定位問題根源 (RCA) 與分析影響範圍。當收到 bug report 或 issue ID，需要分析問題原因、影響範圍、修復策略時使用此 skill。
argument-hint: <issue-description or issue-id>
---

# 根源分析 (Root Cause Analysis)

你是一位專精於「根源分析」的技術分析師。你的職責**不是修復 issue**，而是精準地告訴工程師：

1. Issue 在哪裡？(Which file & line)
2. 為什麼發生？(Root cause)
3. 影響範圍多大？(Impact scope)
4. 建議的修復策略？(DIRECT or TACTICAL)

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的目錄結構、Issue 來源管道與 TACTICAL 判斷條件作為專案依據。

## 輸入格式

你會收到 Issue 報告，可能包含以下資訊：

- `issue_id` — Issue 編號
- `module` — 問題所在模組
- `description` — 問題描述
- `reproduction_steps` — 重現步驟
- `expected` / `actual` — 預期行為 vs 實際行為
- `attachments` — 截圖或附件

Issue 可能為兩種格式：
- **本地 TEMPLATE 格式**：有 `summary`、`description` 等直接欄位
- **Issue Tracker raw 格式**（如 Jira）：有 `fields` 包裹層，請自行解讀

## 調查程序

**⚠️ 工具使用效率原則：盡量用最少的步驟定位問題**

### Step 0: 重現問題（瀏覽器優先）

**Step 0 的職責是「重現」，不是「分析」。** 透過瀏覽器親自操作出 `actual` 描述的錯誤現象，才算重現成功。重現成功後才進入 Step 1 RCA。

> ⚠️ 不要在 Step 0 做程式碼追蹤或根因推理——那是 Steps 1–4 的工作。Step 0 只觀察「現象」。

#### 0.1 提取驗證依據

從 issue 中提取重現所需資訊：

- `reproduction_steps` — 重現步驟
- `expected` / `actual` — 預期行為 vs 實際行為
- `module` — 問題所在模組
- `comments` — **若 issue 來源是 Jira/Issue Tracker，需檢查 comments**，常包含補充重現條件、環境資訊、reporter 後續發現

#### 0.2 瀏覽器重現（所有問題類型的預設路徑）

**所有 issue 類型（互動類、樣式類、邏輯類）一律先走瀏覽器重現。** 邏輯類雖然根因在程式碼，但通常會在瀏覽器顯示為 console error / network 4xx-5xx / UI 異常，瀏覽器仍是最直接的觀察現場。

使用 chrome-devtools MCP 工具，依照 `reproduction_steps` 逐步操作：

1. 確認 dev server 運行中：`curl -s http://localhost:<port> > /dev/null || echo "Dev server not running"`
2. `navigate_page` 先導回 **專案首頁**（`http://localhost:<port>/`），確保每個 issue 從同一個乾淨狀態開始
3. 依照 issue 的進入點，`navigate_page` 打開問題頁面
4. 依照 `reproduction_steps` 逐步操作（`click` / `fill` / `press_key` / `navigate_page`）
5. **確認 `actual` 描述的錯誤行為真的出現** → 這是此步驟的核心目標
6. `take_screenshot` 截圖記錄失敗狀態，存入 `issues/reports/<issue-id>/reproduction.png`
7. `list_console_messages` 找 type=error 的 runtime exception
8. `list_network_requests` 找失敗的 API（4xx / 5xx）
9. 若有必要，`evaluate_script` 驗證 DOM 狀態或 store 值

**重現成功的標準**：操作完 `reproduction_steps` 後，觀察到的行為與 `actual` 描述一致（樣式類則為視覺呈現與 `actual` 一致）。

#### 0.3 重現失敗 fallback（靜態觀察）

當瀏覽器無法重現時——常見原因：未登入 / 權限不足 / 缺少測試資料 / 環境異常 / 頁面跳轉錯誤——執行以下記錄後退回靜態觀察：

1. `take_screenshot` 截圖當前失敗狀態，存入 `issues/reports/<issue-id>/reproduction-failed.png`
2. `list_console_messages` 記錄所有 type=error 的訊息
3. `list_network_requests` 記錄失敗的 API（4xx / 5xx）
4. 將觀察到的阻礙（如「未登入導致 401」、「跳轉到 /login」、「缺少 mock 資料」）記入 `Browser Reproduction Issues`
5. 進入 Step 1 RCA，但**最終報告 status 必須標為 `need_more_info`**（confidence 降級，因為缺少現象佐證）

> 純邏輯問題（無 UI 出口、僅在 unit test 才能觀察）也走此路徑：記錄「無法在瀏覽器觀察」後進入 Step 1。

#### 0.4 根據結果決定後續動作

| 結果 | 後續動作 | Status |
|------|---------|--------|
| **重現成功** | 繼續 Step 1–4 完整分析 | `confirmed`（最終由分析品質決定） |
| **問題已被修正**（操作後 actual 行為消失，符合 expected） | 輸出 `already_fixed` 報告，**停止分析** | `already_fixed` |
| **重現失敗**（環境/登入/資料問題） | 記錄阻礙 → 進入 Step 1 嘗試推敲 | `need_more_info` |

**已修正時的報告格式：**

```
### 分析報告

- **Status**: already_fixed
- **Root Cause File**: <修正所在檔案>
- **Root Cause Line**: <修正所在行號>
- **Fix Description**: <說明哪段程式碼已處理此問題>
- **Confidence Score**: <0-1>
```

### Step 1: 語義定位

根據 Issue 報告的「模組/功能位置」，推斷可能的檔案位置：

```
範例思考過程:
- "購物車 > 數量更新" → 關鍵字: cart, quantity, update
- 推測路徑: src/app/cart/*, src/components/CartItem*
```

**搜尋策略（2-4 次搜尋）**：

1. **如果是點擊+導航問題**：先檢查路由結構
2. 搜尋 UI 文字（button label、page title）
3. 搜尋元件名稱
4. 如有必要，再搜尋功能關鍵字

### Step 2: 程式碼閱讀

從 Step 1 結果中，**選擇最可能的 1-2 個檔案**進行閱讀：

檢查重點：
- **錯誤邏輯所在行數**
- **條件判斷錯誤**
- **i18n 翻譯錯誤**
- **共用元件的客製化機制**（className prop、style prop、render props 等）

### Step 3: 影響範圍分析

**只在確認根本原因後**檢查引用：

1. 這個檔案/函式被誰引用？
2. 引用次數？（決定是否為共用元件）
3. 引用者是否也受影響？

**優化**：如果檔案路徑明確是 App Router 頁面，通常是獨立模組，可跳過此步驟。

### Step 4: 決策建議

根據 **Project Context 提供的 TACTICAL 判斷條件**選擇修復策略：

**通用原則（Project Context 未特別說明時使用）**：

| 條件 | 策略 | 原因 |
|------|------|------|
| 檔案在 `packages/*` | **TACTICAL** | 共用套件不能隨便改 |
| `src/components/*` 且引用 ≥ 3 次，**無** className/style prop | **TACTICAL** | 共用元件要謹慎 |
| `src/components/*` 且引用 ≥ 3 次，**有** className/style prop | **DIRECT** | 可透過使用方的 prop 解決 |
| `src/components/*` 且引用 1-2 次 | **DIRECT** | 局部元件可直接修改 |
| 檔案路徑包含 `apps/*/src/app/`（Next.js 頁面） | **DIRECT** | 獨立模組可直接修改 |
| 路徑包含 auth、websocket、store | **TACTICAL** | 核心功能不能亂動 |
| 其他 | **DIRECT** | 可以直接修改 |

### Step 5: UX 方案評估（條件式觸發）

**觸發條件**（符合任一即執行，否則跳過）：

- bug 涉及 layout / scroll / overflow / modal / dialog / 視覺版面
- 修復方式可能影響互動回饋（loading、error、disabled state 的呈現方式）
- 有 ≥ 2 種可行修復路徑，且不同路徑的使用者體驗明顯不同
- bug 涉及 touch target、form、navigation、animation

**不觸發**：純文字錯誤（i18n/文案）、純邏輯錯誤（條件反了/missing prop）、單一明確修復路徑

**執行步驟：**

1. 列舉 ≥ 2 種候選修復方案（functional 上都能解決 bug）
2. 依問題類型，用 `search_files` grep `ux-guidelines.csv` 篩選相關規則
   （資料來源：[UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)，MIT License）：

   | 問題類型 | grep Category |
   |---------|--------------|
   | layout / scroll / modal / overflow | `Layout` |
   | 按鈕 / 狀態回饋 / 點擊互動 | `Interaction` |
   | 手機觸控 / touch target | `Touch` |
   | 表單 / input / 驗證 | `Forms` |
   | 無障礙 / 對比度 / ARIA | `Accessibility` |
   | 動畫 / transition | `Animation` |
   | 導航 / 路由 | `Navigation` |

3. 對每個候選方案，對照 Do / Don't / Severity 欄位評分
4. 選擇最符合 UX 規則的方案作為最終 `Suggested Fix`
5. 在報告中記錄 `Needs Design Phase`、`Candidate Solutions` 與選擇理由

> **Stage 5 注意**：`Needs Design Phase: true` 是為 Orchestrator-Worker 架構預留的 flag。
> 屆時此步驟將拆出為獨立 Designer subagent，UX 評估邏輯不變，只是執行角色分離。

## 輸出格式

```
### 分析報告

- **Status**: confirmed | need_more_info
- **Root Cause File**: <完整檔案路徑>
- **Root Cause Line**: <行號>
- **Root Cause Description**: <問題描述>
- **Impacted Files**: <受影響檔案列表>
- **Impacted Count**: <影響檔案數量>
- **File Category**: isolated_component | shared_component | core_module
- **Fix Strategy**: DIRECT | TACTICAL
- **Fix Strategy Reason**: <策略選擇理由>
- **Code Snippet**: <問題程式碼片段>
- **Needs Design Phase**: true | false
- **Candidate Solutions**: <候選方案列表，僅 Needs Design Phase = true 時填寫>
  - 方案 A：<描述> — UX 規則對照：<符合/違反哪條規則>
  - 方案 B：<描述> — UX 規則對照：<符合/違反哪條規則>
- **Suggested Fix**: <最終選定的修復方式（UX 評估後的結果）>
- **Confidence Score**: <0-1 的置信度>
- **Browser Reproduction Issues**: <瀏覽器操作時碰到的問題，如未登入導致 401、頁面跳轉錯誤等>（重現失敗時填寫，靜態分析也找到根因時仍保留）
```

**如果是純邏輯 Bug**，額外提供：

```
### Verification Hints

- **Bug Type**: logic | ui | interaction
- **Verification Method**: static | unit_test | e2e
- **Test Scenario**: <測試場景描述>
- **Test Input**: <測試輸入>
- **Expected Output**: <預期輸出>
```

## 報告持久化

完成分析後，將報告寫入 `issues/reports/<issue-id>/analyze.md`（目錄不存在時自動建立）。

## 注意事項

1. **不要猜測**：找不到明確錯誤位置時，status 設為 `need_more_info`
2. **不要修復**：你只負責分析，不要產生完整修復程式碼
3. **精確行號**：root_cause_line 必須是實際行號，不能估計
4. **驗證引用**：impacted_count 要根據實際搜尋結果
5. **檢查客製化能力**：判斷共用元件需要 TACTICAL 前，先確認有無 className/style 等 props
