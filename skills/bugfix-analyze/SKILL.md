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

> 瀏覽器工具效率規則：載入 `../references/browser-efficiency.md`

<!-- GATE:REPRODUCE -->
### Step 0: 重現問題（瀏覽器優先）

**Step 0 的職責是「重現」，不是「分析」。** 透過瀏覽器親自操作出 `actual` 描述的錯誤現象，才算重現成功。重現成功後才進入 Step 1 RCA。

> ⚠️ 不要在 Step 0 做程式碼追蹤或根因推理——那是 Steps 1–4 的工作。Step 0 只觀察「現象」。

→ 詳細程序：載入 `references/browser-reproduction.md`

<!-- GATE:RCA -->
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

**若修復方向涉及外部 API 契約變更** → 載入 `references/external-contract.md`

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

→ 觸發時載入 `references/ux-evaluation.md`

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
- **Confidence Score**: <依下表計算，base 1.0 扣分制，最低 0.1>
  - 根因定位：確切檔案+行號 (0) / 確切檔案無行號 (-0.10) / 只有模組名 (-0.25) / 無法定位 (-0.50)
  - 佐證來源：瀏覽器直接觀察 (0) / console error 或 network 4xx 間接佐證 (-0.05) / 靜態分析無法重現 (-0.20) / 純假設無工具佐證 (-0.40)
  - 假設競爭：根因唯一 (0) / 有 1 個備選假設 (-0.05) / 有 2+ 個等可能假設 (-0.15)
  - 修復路徑：明確知道改哪行 (0) / 方向明確細節待確認 (-0.05) / 修復方式不確定 (-0.10)
  - 外部依賴假設：不涉及外部契約 (0) / 涉及且有文件或實測佐證 (-0.05) / 涉及但僅靠程式碼推測 (-0.40) / 程式碼看起來正確但行為失常（bug 可能在外部）→ 強制 need_more_info
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

完成分析後，將報告寫入 task prompt 指定的絕對路徑（`Write analysis report to: <path>`）。
報告與截圖都存放在 **agent root**（非被修正的目標專案目錄）。

## 注意事項

1. **不要猜測**：找不到明確錯誤位置時，status 設為 `need_more_info`
2. **不要修復**：你只負責分析，不要產生完整修復程式碼
3. **精確行號**：root_cause_line 必須是實際行號，不能估計
4. **驗證引用**：impacted_count 要根據實際搜尋結果
5. **檢查客製化能力**：判斷共用元件需要 TACTICAL 前，先確認有無 className/style 等 props
