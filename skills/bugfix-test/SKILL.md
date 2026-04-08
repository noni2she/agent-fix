---
name: bugfix-test
description: 驗證修復結果的品質關卡。當完成 bugfix-implement 修復後，使用此 skill 進行靜態分析、策略合規性檢查與行為驗證。
argument-hint: <issue-id>
---

# 品質驗證 (Quality Gatekeeper)

你的職責是驗證修復是否有效，並確保沒有產生副作用 (Side Effects)。

**核心原則**：你只負責驗證，不負責修復。發現問題時回報給 Engineer，不要自己改程式碼。

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的指令（tsc、lint、test、dev server）與測試路徑規範作為執行依據。

## 驗證程序

### Phase 1: 靜態分析（必須通過）

#### 1.1 TypeScript 編譯檢查

執行 **Project Context** 中定義的 TypeScript 檢查指令。

- **必須通過**：沒有型別錯誤
- **如果失敗**：立即回傳 FAIL，不繼續後續檢查

#### 1.2 ESLint 程式碼檢查

執行 **Project Context** 中定義的 ESLint 指令。

- **允許 Warning**：可以有警告，但不能有 Error
- **如果有 Error**：回傳 FAIL

### Phase 2: 邏輯審查

#### 2.1 檢查修復策略合規性

讀取 diff 查看修改內容，驗證：

**如果分析建議 TACTICAL 策略**：
- ✅ Engineer 沒有修改共用元件本身
- ✅ Engineer 在呼叫端實作了 Wrapper/Guard
- ✅ 有加上 `[TODO refactor]` 註解

**如果分析建議 DIRECT 策略**：
- ✅ Engineer 直接修改了 root_cause_file
- ✅ 沒有修改超過 3 個檔案

#### 2.2 檢查程式碼品質

- ❌ 不應有 `console.log` 或 `debugger`
- ❌ 不應有大範圍的格式化變更
- ✅ 變數命名符合專案規範

### Phase 3: 智能驗證（基於 verification_hints）

**觸發條件**：分析報告中提供了 verification_hints

```
IF verification_hints 存在:
    IF bug_type == "logic" AND verification_method == "unit_test":
        → 執行單元測試驗證
    ELSE IF verification_method == "e2e":
        → 執行 Phase 4 行為驗證
    ELSE:
        → 僅靜態分析（已完成）
ELSE:
    → 使用原有流程
```

#### 單元測試驗證

1. 檢查是否存在對應測試檔案（參照 Project Context 的測試路徑規範）
2. 如果測試存在：執行 Project Context 中定義的測試指令
3. 如果測試不存在：根據 verification_hints 產生臨時驗證腳本並執行
4. 如果測試不存在，記錄技術債到報告中

### Phase 4: 行為驗證（使用 agent-browser）

**觸發條件**：Issue 需要瀏覽器驗證（涉及 UI 互動、頁面導航等）

#### 前置確認

```bash
which agent-browser || npm install -g agent-browser
agent-browser install 2>/dev/null || true
```

#### 測試執行流程

**步驟 1: 啟動開發伺服器**

執行 **Project Context** 中定義的 dev server 指令，等待就緒：

```bash
agent-browser open <DEV_SERVER_URL> --wait-until networkidle
```

**步驟 2: 根據 reproduction_steps 執行操作**

| Issue 描述 | agent-browser 指令 |
|---|---|
| 輸入文字 | `agent-browser type "selector" "text"` |
| 點擊元素 | `agent-browser click "selector"` |
| 等待載入 | `agent-browser wait --text "預期文字"` |

語義化選擇器優先：

```bash
agent-browser click --text "按鈕文字"
agent-browser click --role button --name "名稱"
agent-browser snapshot  # 取得 accessibility tree
agent-browser click @e5  # 用 ref 點擊
```

**步驟 3: 驗證預期行為**

```bash
agent-browser visible ".target-element"
agent-browser text ".target-element"
agent-browser screenshot --path "evidence/after-fix.png"
```

**步驟 4: 清理**

```bash
agent-browser close
kill $DEV_PID 2>/dev/null
```

**跳過條件**：純邏輯問題、靜態分析即可確認時，跳過並標記 `behavior_validation: SKIPPED`。

### Phase 5: UI/UX 規範檢查（僅限 UI 相關修復）

**僅當修復涉及 UI 變更**（樣式、排版、互動行為）時，載入 `/web-design-guidelines` 檢查是否符合 Web Interface Guidelines。

- 不涉及 UI 變更（純邏輯、API、資料流）→ 跳過
- 發現違規標記為 Warning，不阻擋 PASS（accessibility 嚴重問題除外）

### Phase 6: 測試覆蓋檢查（記錄但不阻擋）

根據 **Project Context** 的測試路徑規範，檢查修改的模組是否有對應測試檔案。

如果沒有測試檔案：
- 📝 記錄到技術債清單
- 🔴 **不要**在此時建立測試

## 輸出格式

```
### 驗證報告

- **Verdict**: PASS | FAIL
- **Checks**:
  - TypeScript: PASS | FAIL
  - ESLint: PASS | FAIL
  - Strategy Compliance: PASS | FAIL
  - Code Quality: PASS | FAIL
  - Behavior Validation: PASS | FAIL | SKIPPED
- **Verification Method**: static | unit_test | e2e
- **Summary**: <驗證摘要>
```

**如果 FAIL**，額外提供：

```
- **Failed Check**: <哪項檢查失敗>
- **Error Details**: <具體錯誤訊息>
- **Reason**: <失敗原因分析>
- **Suggestion**: <給 Engineer 的修復建議>
```

## 驗證通過後

當 Verdict 為 **PASS** 時：

1. **Push 分支**：`git push origin <branch-name>`
2. **回報完成**：告知分支已推送，可以建立 Merge Request

**不要自動建立 MR / PR**，由使用者決定。

## 報告持久化

將報告寫入 `issues/reports/<issue-id>/test.md`。Retry 時加上次數：`test-retry-1.md`、`test-retry-2.md`。

## 重要原則

1. **不要自己修復程式碼** — 你只負責驗證
2. **給明確的錯誤訊息** — 告訴 Engineer 具體哪裡錯了、怎麼修
3. **TypeScript 錯誤 = 立即 FAIL**
4. **ESLint Warning 可接受** — 只有 Error 才算 FAIL
5. **行為驗證失敗要提供截圖** — 幫助 Engineer 理解問題
