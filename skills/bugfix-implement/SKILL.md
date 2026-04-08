---
name: bugfix-implement
description: 根據分析報告實作修復。當已經完成 bugfix-analyze 分析、有明確的 root cause 和修復策略後，使用此 skill 進行實際修復。
argument-hint: <issue-id>
---

# 修復實作 (Tactical & Risk-Aware Engineer)

你負責根據分析報告進行修復。核心原則：**「穩定性優於完美的程式碼」**。

> **Project Context** 已在本次任務開頭注入。請以 Project Context 中定義的指令（build、lint、test）與目錄結構作為專案依據。

## Git Workflow

**在開始修復前，必須遵循 Git workflow：**

1. **檢查狀態**：確認當前 Git 狀態與分支，確保 working tree 乾淨
2. **同步最新**：`git pull origin main`
3. **建立分支**：從 main 建立 `bugfix/<issue-id>-<description>`
4. **執行修復**：修改程式碼
5. **確認變更**：檢查 diff，確認只改了該改的檔案
6. **建立 commit**：遵循 Conventional Commits 格式

```bash
# Commit message 格式
fix(<scope>): <description>
```

## 🚨 策略遵守規則（絕對禁止違反）

**你必須無條件遵守分析報告中的 `fix_strategy` 建議！**

- ✅ 分析建議 `DIRECT` → 使用 Direct Fix
- ✅ 分析建議 `TACTICAL` → 使用 Tactical Fix
- ❌ **禁止**自行判斷並改用其他策略

### 例外情況（僅 3 種可回報錯誤而不修復）

1. **找不到檔案**：root_cause_file 不存在
2. **檔案內容不符**：root_cause_line 處的程式碼與分析描述不符
3. **型別錯誤無法解決**：修復後產生無法修復的靜態型別錯誤

## 修復策略

### 策略 A: Direct Fix（直接修復）

**適用情境**：獨立模組、影響範圍 ≤ 3 個檔案、非核心共用元件

**執行方式**：
1. 讀取 root_cause_file
2. 根據 root_cause_line 定位錯誤
3. 修正邏輯錯誤
4. 寫回檔案

### 策略 B: Tactical Fix（戰術性修復）

**適用情境**：共用套件、多處引用的元件、核心功能

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

## 修復規範

- 遵循專案命名規範
- 不要引入 `console.log` 或 `debugger`
- 不要修改無關的程式碼（例如格式化整個檔案）
- **最多修改 3 個檔案**；如果需要修改 > 3 個，回報「建議作為重構專案處理」

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
4. **使用 `git commit --amend`** 更新之前的 commit

### 重試檢查清單

- [ ] 已理解 Tester 回饋的所有內容
- [ ] 已實際修改程式碼（不是只檢查）
- [ ] 修改內容完全遵守 Tester 的建議
- [ ] 沒有重複之前的錯誤
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
