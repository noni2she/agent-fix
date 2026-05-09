---
name: bugfix-test
description: 驗證修復結果的品質關卡。完成 bugfix-implement 後，進行靜態分析、策略合規性檢查與行為驗證。
argument-hint: <analyze-report-path> <implement-report-path>
---

# 品質驗證

你的職責是驗證修復是否有效，確保沒有產生副作用。**不負責修復**——發現問題只回報給 Engineer，不自己改程式碼。

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的指令（tsc、lint、dev server）與測試路徑規範作為執行依據。

## 輸入

- **analyze.md**：Root Cause、Fix Strategy、reproduction_steps、expected
- **implement.md**：Branch、Modified Files、Fix Summary

## 驗證程序

### Phase 1: 靜態分析

#### 1.1 TypeScript 編譯檢查

執行 Project Context 中定義的 TypeScript 指令。

- 必須通過：無型別錯誤
- 失敗：立即回傳 FAIL，不繼續後續 Phase

#### 1.2 ESLint 程式碼檢查

執行 Project Context 中定義的 ESLint 指令。

- Warning 允許；Error = FAIL

### Phase 2: 邏輯審查

#### 2.1 策略合規性

讀取 git diff 確認修復符合 analyze.md 的 Fix Strategy：

TACTICAL 策略：
- 沒有修改共用元件本身
- 呼叫端有 Wrapper / Guard Clause
- 有 `[TODO refactor]` 註解

DIRECT 策略：
- 直接修改了 root_cause_file
- 沒有修改超過 3 個檔案

#### 2.2 程式碼品質

- 不應有 `console.log` 或 `debugger`
- 不應有大範圍格式化變更
- 變數命名符合專案規範

#### 2.3 Side Effect 靜態分析

```bash
git diff --name-only   # 取得修改的檔案清單
```

對每個修改的檔案，grep 直接 import 它的其他模組（一層深度），列入驗證報告的 Side Effect Risk 欄位，供 MR reviewer 參考。

> 目前 pipeline 無 unit test / integration test，side effect 驗證僅覆蓋直接靜態依賴範圍。動態行為層面的 regression 由人工 MR review（未來由 issue verify team 的 AI MR review）把關。

### Phase 3: 行為驗證

**觸發條件（任一成立即執行）**：
- implement.md 的 Modified Files 包含 `.tsx` / `.jsx` 副檔名
- implement.md 的 Modified Files 包含 `.css` / `.scss` / `.less` 副檔名
- analyze.md 的 Root Cause Description 包含視覺相關關鍵字：render、display、layout、scroll、overflow、animation、style、visibility、modal、interaction

**不觸發**（三條都不符）：修改限於 `.ts` / `.js`，且 Root Cause Description 無視覺關鍵字。跳過時標記 `behavior_validation: SKIPPED`。

**步驟 0：先觀察，再設計場景**

1. 呼叫 `run_behavior_validation` 執行僅含 `goto` 的場景，截圖確認當前頁面狀態
2. 從截圖或 DOM 取得真實存在的 selector
3. 依觀察結果設計後續 scenario

禁止憑空猜測 selector 或按鈕文字。

**步驟 1：設計驗證場景**

- 從 analyze.md 的 `reproduction_steps` 對應動作序列
- 從 Project Context 的 Behavior Validation Scenario Schema 取得可用 action / assertion 類型
- assertions 方向：**確認 expected result 出現**（而非重現 bug）

> browser 操作規則參照 `references/browser-reproduction.md`，斷言方向相反。

**步驟 2：執行 `run_behavior_validation`**

傳入 scenario JSON，由 Python 端執行 Playwright 驗證（auto-wait + retry assertions）。

**步驟 3：解讀結果**

- PASS → 繼續 Phase 4
- FAIL → 重試一次：截圖確認當下頁面狀態，調整 selector 或動作序列後重試
  - 重試仍 FAIL → 回傳 FAIL，附上失敗動作/斷言、錯誤訊息、截圖路徑

### Phase 4: UI 規範檢查（條件式）

**觸發條件**：Phase 3 已執行

查詢 Project Context 中宣告的 UI knowledge skill，確認修復後的 UI 符合設計規範。

違規記錄為 Warning，不阻擋 PASS（accessibility 嚴重問題除外）。

### Phase 5: 測試覆蓋（記錄）

根據 Project Context 的測試路徑規範，確認修改的模組是否有對應測試檔案。

無測試檔案時記錄技術債，不建立測試，不阻擋 Verdict。

## 輸出格式

```
### 驗證報告

- **Verdict**: PASS | FAIL
- **Checks**:
  - TypeScript: PASS | FAIL
  - ESLint: PASS | FAIL
  - Strategy Compliance: PASS | FAIL
  - Code Quality: PASS | FAIL
  - Side Effect Risk: <直接依賴此修改的模組列表，供 MR reviewer 參考>
  - Behavior Validation: PASS | FAIL | SKIPPED
- **Verification Method**: static | e2e
- **Summary**: <驗證摘要>
```

FAIL 時額外提供：

```
- **Failed Check**: <哪項檢查失敗>
- **Error Details**: <具體錯誤訊息>
- **Reason**: <失敗原因分析>
- **Suggestion**: <給 Engineer 的修復建議>
```

## 驗證通過後

Verdict 為 PASS 時：

1. Push 分支：`git push origin <branch-name>`
2. 根據 Project Context 的 `auto_create_mr` 設定決定是否自動建立 MR

## 報告持久化

將報告寫入 task prompt 指定的絕對路徑（`Write your verification report to: <path>`）。
報告存放在 **agent root**（非被修正的目標專案目錄）。

## 重要原則

1. 不要自己修復程式碼——只負責驗證
2. 給明確的錯誤訊息——告訴 Engineer 具體哪裡錯了、怎麼修
3. TypeScript 錯誤 = 立即 FAIL
4. ESLint Warning 可接受——只有 Error 才算 FAIL
5. 行為驗證失敗要提供截圖，幫助 Engineer 理解問題
