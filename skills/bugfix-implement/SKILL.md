---
name: bugfix-implement
description: 根據分析報告實作修復。當已完成 bugfix-analyze 分析、有明確的 root cause 和修復策略後使用。
argument-hint: <analyze-report-path>
---

# 修復實作

## 職責

根據 analyze.md 的修復計畫進行實作。評估工程方案、判斷技術影響，產出最小範圍的程式碼修改。

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的目錄結構、建置指令（build、lint、test）與 knowledge skills 作為專案依據。

## 輸入

- **analyze.md**：包含 Root Cause File/Line、Fix Strategy、Suggested Fix、Code Snippet

## Git 前置關卡

修改任何程式碼前，依序執行並確認每步輸出：

```bash
git status                                        # Step 1: 確認 working tree 乾淨
git checkout main && git pull origin main         # Step 2: 同步最新程式碼
git checkout -b bugfix/<issue-id>-<description>   # Step 3: 建立 bugfix 分支
git branch --show-current                         # Step 4: 確認在正確分支
```

Step 4 輸出必須為 `bugfix/...` 才可繼續修改程式碼。

## 策略遵守

必須無條件遵守 analyze.md 中的 `Fix Strategy`：

- `DIRECT` → 使用 Direct Fix
- `TACTICAL` → 使用 Tactical Fix

禁止自行改變策略。唯三例外（可回報錯誤而不修復）：
1. root_cause_file 不存在
2. root_cause_line 處的程式碼與分析描述不符
3. 修復後產生無法解決的靜態型別錯誤

## 實作前驗證

開始實作前，讀取 analyze.md 指定的 root_cause_file 與 impacted_files，確認：
- 建議使用的 store、hook、prop 實際存在
- root_cause_line 的程式碼符合分析描述

不可行時停止，輸出驗證失敗報告：

```
### 分析建議驗證失敗

- **問題步驟**: <哪個建議有誤>
- **原因**: <為什麼不可行>
- **證據**: <從程式碼找到的實際定義>
- **正確做法**: <應該怎麼做>
```

## 修復策略

### Direct Fix

適用：獨立模組、影響範圍 ≤ 3 個檔案、非核心共用元件

1. 讀取 root_cause_file
2. 根據 root_cause_line 定位錯誤
3. 修正邏輯錯誤並寫回

### Tactical Fix

適用：`packages/*`、引用 > 3 次的元件、核心功能（auth、websocket、store）

1. 不修改原始共用檔案
2. 在呼叫端實作 wrapper 或 guard clause
3. 加上 TODO 註解標記技術債

```
// [TODO refactor] <issue_id>: <簡短說明>
// 原因: <為什麼使用 Tactical Fix>
// 未來應: <理想的重構方向>
```

## 知識型 Skill 查詢

修改特定類型的程式碼前，查詢 **Project Context** 中宣告的對應 knowledge skill：

| 情境 | 查詢 knowledge skill 的類別 |
|------|---------------------------|
| 修改 UI component | rendering / re-render 規則 |
| 涉及資料獲取 | async / client-side 規則 |
| 新增第三方套件 | bundle size 規則 |
| 修改 Server Component | server-side 規則 |

Project Context 未宣告 knowledge skill 時，依 LLM 訓練知識處理。

## UX

確認實作沒有引入新的 UX 問題。

## Commit 前驗證

禁止在通過以下驗證前執行 `git commit`。讀取 Project Context 中 `quality_checks` 區塊，逐一執行所有 `enabled: true` 的指令：

- TypeScript 型別檢查：必須 exit code 0，無 error
- ESLint：warning 可接受，error 不行
- Prettier：格式必須通過
- `git diff`：確認只修改了該改的檔案，無意外變更

驗證失敗時，修正後重新驗證再 commit。

## Git Commit

```bash
git diff                                          # Step 5: 確認 diff 只包含應改的檔案
git commit -m "<type>(<scope>): <description>"    # Step 6: Conventional Commits 格式
```

## 修復規範

- 遵循專案命名規範（camelCase、PascalCase）
- 不引入 `console.log` 或 `debugger`
- 不修改無關程式碼，保持原有程式碼風格
- 最多修改 3 個檔案；若需修改更多，回報「建議作為重構專案處理」

## 處理 Tester 回饋

收到 tester 回饋後：

1. 理解具體錯誤與失敗原因
2. 實際修改程式碼（不能只確認後不修改）
3. 完全遵守 tester 的建議，不重複之前的錯誤
4. 通過驗證後建立新 commit（不使用 `--amend`）

## 輸出格式

```
### 修復報告

- **Branch**: bugfix/<issue-id>-<description>
- **Status**: success | failed | escalated
- **Modified Files**: <修改的檔案列表>
- **Fix Summary**: <1-2 行說明使用的工程方案與選擇理由，例如：「在 onChange 加入 300ms debounce 防止 video re-render；選 debounce 而非 throttle 因需等待輸入停止後才觸發」>
```

## 報告持久化

修復完成後，將報告寫入 task prompt 指定的絕對路徑（`Write implementation report to: <path>`）。
報告存放在 **agent root**（非被修正的目標專案目錄）。
