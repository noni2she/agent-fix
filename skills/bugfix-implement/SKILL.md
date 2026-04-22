---
name: bugfix-implement
description: 根據分析報告實作修復。當已經完成 bugfix-analyze 分析、有明確的 root cause 和修復策略後，使用此 skill 進行實際修復。
argument-hint: <issue-id>
---

# 修復實作 (Tactical & Risk-Aware Engineer)

你負責根據分析報告進行修復。核心原則：**「穩定性優於完美的程式碼」**。

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的指令（build、lint、test）與目錄結構作為專案依據。

## 🔒 Git 前置關卡（修改任何程式碼前必須完成）

**禁止在完成以下步驟前使用 Edit / Write 工具。**

逐步執行並在繼續前確認每個指令的輸出：

```bash
# Step 1: 確認 working tree 乾淨
git status

# Step 2: 切換至 main 並同步最新程式碼
git checkout main && git pull origin main

# Step 3: 建立 bugfix 分支
git checkout -b bugfix/<issue-id>-<description>

# Step 4: 確認已在正確分支上
git branch --show-current
```

確認 Step 4 輸出為 `bugfix/...` 後，才可以進行程式碼修改。

⛔ **若跳過上述任一步驟直接修改程式碼，視為違規，必須立即停止、回復現場，並重新執行關卡。**

## 🚨 策略遵守規則（絕對禁止違反）

**你必須無條件遵守分析報告中的 `fix_strategy` 建議！**

- ✅ 分析建議 `DIRECT` → 使用 Direct Fix
- ✅ 分析建議 `TACTICAL` → 使用 Tactical Fix
- ❌ **禁止**自行判斷並改用其他策略

### 例外情況（僅 3 種可回報錯誤而不修復）

1. **找不到檔案**：root_cause_file 不存在
2. **檔案內容不符**：root_cause_line 處的程式碼與分析描述不符
3. **型別錯誤無法解決**：修復後產生無法修復的靜態型別錯誤

## 驗證分析建議（實作前必做）

**⚠️ 在開始實作修復之前，必須先驗證分析報告的建議是否可行！**

1. 讀取 root_cause_file、impacted_files、相關 store/hook/元件
2. 確認建議使用的 store、hook、prop 是否存在
3. 決定：可行 → 繼續；不可行 → 立即停止並回報

```
### 分析建議驗證失敗

- **問題步驟**: <哪個建議有誤>
- **原因**: <為什麼不可行>
- **證據**: <從程式碼找到的實際型別/介面定義>
- **正確做法**: <應該怎麼做>
```

## 修復策略

### 策略 A: Direct Fix（直接修復）

**適用情境**：獨立模組、影響範圍 ≤ 3 個檔案、非核心共用元件

**執行方式**：
1. 讀取 root_cause_file
2. 根據 root_cause_line 定位錯誤
3. 修正邏輯錯誤
4. 寫回檔案

### 策略 B: Tactical Fix（戰術性修復）

**適用情境**：共用套件、引用 > 3 次的元件、核心功能（auth、websocket、store）

**執行方式**：
1. **不要修改原始共用檔案**
2. 在**呼叫端 (Caller)** 實作 Wrapper 或 Guard Clause
3. 加上 `// TODO` 註解標記技術債

```typescript
// ✅ 正確做法：在呼叫端隔離修復
// [TODO refactor] ISSUE-1234: Tactical fix to avoid regression
// 原因: SharedButton 是共用元件，被多個頁面使用，直接修改風險高
// 未來應: 統一修正共用元件並更新所有呼叫端
function SafeButton({ isActive, ...props }) {
  return <SharedButton isActive={!isActive} {...props} />
}
```

## Coding Standards

修復程式碼時，根據 **Project Context** 中 `skills.directories` 定義的 skill 路徑，在以下情境載入對應 skill：

| 情境 | 建議載入的 skill 類型 |
|------|----------------------|
| 新增或修改核心元件/模組 | 架構與效能規則（如 `vercel-react-best-practices`） |
| 涉及資料獲取（fetch/API call） | 非同步處理規則 |
| 新增 import 或第三方套件 | 套件管理規則 |
| 修改 UI 樣式或互動行為 | UI/設計規範（如 `web-design-guidelines`） |

若 Project Context 未定義 coding standards skill，遵循 Project Context 提供的命名規範即可。

## ✅ Commit 前驗證關卡

**禁止在通過以下驗證前執行 `git commit`。**

根據 **Project Context** 中啟用的 `quality_checks` 逐一執行對應指令（指令定義在 config 的 `quality_checks` 區塊）：

- TypeScript 型別檢查（若啟用）：必須 exit code 0，沒有任何 error
- ESLint（若啟用）：Warning 可接受，Error 不行
- Prettier（若啟用）：格式必須通過
- 確認 diff：`git diff` 確認只修改了該改的檔案

驗證失敗時：**不要 commit**，回報錯誤、修正後重新驗證。

## Git Commit

通過驗證後，建立 commit：

```bash
# Step 5: 確認 diff 只包含該改的檔案
git diff

# Step 6: 建立 commit（Conventional Commits 格式）
git commit -m "<type>(<scope>): <description>"
```

## 修復規範

- 遵循專案命名規範
- 不要引入 `console.log` 或 `debugger`
- 不要修改無關的程式碼（例如格式化整個檔案）
- 保持原有程式碼風格
- **最多修改 3 個檔案**；如需修改 > 3 個，回報「建議作為重構專案處理」

### Tactical Fix 註解格式

```typescript
// [TODO refactor] <issue_id>: <簡短說明>
// 原因: <為什麼要用 Tactical Fix>
// 未來應: <理想的重構方向>
```

## 處理 Tester 回饋與重試

1. **仔細閱讀回饋**：理解具體錯誤、失敗原因、修復建議
2. **禁止重複相同的錯誤**
3. **必須實際修改程式碼**：不能只讀檔案確認後不做任何修改
4. **完全遵守建議**：Tester 的 suggestion 是明確的修改指示
5. **使用 `git commit --amend`** 更新之前的 commit

### 重試檢查清單

- [ ] 已讀取並理解 Tester 回饋的所有內容
- [ ] 已實際修改程式碼（不是只檢查）
- [ ] 修改內容完全遵守 Tester 的建議
- [ ] 沒有重複之前的錯誤
- [ ] 已通過 quality_checks 驗證
- [ ] 已確認 diff 正確
- [ ] 已更新 commit

## 輸出格式

```
### 修復報告

- **Strategy Used**: DIRECT | TACTICAL
- **Modified Files**: <修改的檔案列表>
- **Git Branch**: <分支名稱>
- **Git Commit**: <commit message>
- **Fix Summary**: <修復摘要>
- **Estimated Risk**: <0-1 風險評估>
- **Action Log**: <執行步驟記錄>
```

## 報告持久化

修復完成後，將報告寫入 `issues/reports/<issue-id>/implement.md`（目錄不存在時自動建立）。
