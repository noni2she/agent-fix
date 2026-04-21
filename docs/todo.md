# Agent Fix — 發展路線

> 最後更新：2026-04-17

## 專案定位

- **agent-fix**（本專案）：通用 AI 問題分析與修復代理引擎，config-driven，支援任意專案
- **agent-bugfix**（公司 GitLab）：公司內部版，同核心引擎，附帶公司專案配置範例

---

## 階段 1：Skills 定義與驗證（✅ 完成）

- [x] 建立三個核心 skills：bugfix-analyze / bugfix-implement / bugfix-test
- [x] bugfix-analyze 加入 Step 0（確認問題存在）
- [x] bugfix-implement 加入 Coding Standards Skill 參考段落
- [x] Skills 通用化：不含專案細節，透過 Project Context 注入

## 階段 2：Engine 架構（✅ 完成）

- [x] Skill-Based workflow：analyze → implement → test（retry ≤3）
- [x] Token 優化：analyze + implement 共用 session，test 獨立 session
- [x] SDK Adapter 抽象化（Copilot / Claude / OpenAI）
- [x] Config-driven ProjectConfig（Pydantic YAML 驗證）
- [x] ProjectSpec TACTICAL 判斷邏輯
- [x] `coding_standards_skill` 欄位（framework-agnostic）

## 階段 3：Package 化 — Direction B（✅ 完成）

- [x] 建立 `engine/workflow.py`：所有 config init 延遲到 `run_workflow()` 執行時
- [x] 修正 `cli.py`：`from main import main` → `from engine.workflow import run_workflow`
- [x] 修正 `SKILLS_DIR`：`Path(__file__).parent.parent / "skills"`（`__file__`-relative）
- [x] 更新 `pyproject.toml`：hatch wheel config 包含 engine + cli.py + skills/
- [x] `main.py` 簡化為向後相容 shim
- [x] 修正 `Dict[str, any]` → `Dict[str, Any]`（Pydantic bug）
- [x] `pip install` 後 `agent-fix run BUG-001` 全域可用

## 階段 4：批次執行（✅ 完成）

- [x] `agent-fix batch` CLI 指令（--dry-run、--filter）
- [x] `run_batch_workflow()` — 依序執行，單一失敗不中斷
- [x] `IssueSourceAdapter.list_all()` 抽象方法
- [x] `LocalJsonAdapter.list_all()` — 掃描 `issues/sources/*.json`
- [x] `GoogleSheetsAdapter` — 純記憶體快取，讀取 Sheet → 直接交 batch runner
- [x] `gspread` 為 optional `sheets` extra
- [x] `JiraAdapter.list_all()` — JQL query（jql_base + --filter AND 串接，支援分頁）

## 階段 5：Orchestrator-Worker 架構（🔴 最高優先，下一個大方向）

> **背景**：目前 1 agent + 3 skills 的一條龍流程存在「認知污染」問題——
> analyze 建立的假設會滲透到 implement，implement 的框架又影響 test 的客觀性。
> 即使 test 開了新 session，它仍讀了 analyze.md / implement.md，等同繼承了前兩階段的偏見。
>
> **解法**：引入 Orchestrator 作為純路由層，每個 phase 由獨立 subagent 執行，
> Orchestrator 控制每個 subagent 能看到的資訊，確保各 phase 的認知獨立性。

### 架構設計

```
Orchestrator（純路由，不做分析判斷）
├── spawn → Analyzer subagent    輸入：issue 描述（僅此）
│                                輸出：analyze.md
├── spawn → Implementer subagent 輸入：analyze.md（僅此）
│                                輸出：implement.md + code diff
└── spawn → Tester subagent      輸入：issue 原文 + code diff（不含 analyze / implement）
                                 輸出：test.md (PASS / FAIL)
```

### 各角色資訊隔離規則

| Subagent | 能看到 | 不能看到 |
|----------|--------|---------|
| Analyzer | issue 原文 | 任何修復相關資訊 |
| Implementer | analyze.md 結論 | Analyzer 的推理過程 |
| Tester | issue 原文 + diff | analyze.md / implement.md |

### 需要做的事

**核心架構**
- [ ] 新增 `engine/orchestrator.py`：Orchestrator 主控邏輯，負責 spawn subagent + 路由
- [ ] 各 phase 改為獨立 subagent session（`create_session` 各自呼叫）
- [ ] Orchestrator 控制每個 subagent 的輸入內容（資訊隔離）
- [ ] retry 邏輯移至 Orchestrator 層（Tester FAIL → Orchestrator 決定是否 re-spawn Implementer）
- [ ] 現有 `workflow.py` 重構或保留為向後相容的 legacy mode
- [ ] CLI 新增 `--mode orchestrator`（預設）vs `--mode legacy`（目前一條龍）

**MR 自動化**
- [ ] `config.yaml` 新增 `git_platform: github | gitlab`，Orchestrator 依此切換 CLI 命令
- [ ] Tester PASS 後自動建立 MR/PR，取得平台回傳的 MR/PR ID
- [ ] 從平台撈回 MR diff（`gh pr diff` / `glab mr diff`）作為 Reviewer 輸入
- [ ] 新增 `engine/reviewer.py`：AI Reviewer subagent（輸入：issue 原文 + 平台 MR diff，資訊隔離）
- [ ] Reviewer 評論寫回平台 MR（`gh pr review` / `glab mr note` + `glab mr approve`）
- [ ] Reviewer APPROVE → MR 留有初審紀錄，等待人類 merge；REQUEST CHANGES → 回饋 retry
- [ ] Orchestrator 總結報告明確列出衝突組的 merge 順序

**Batch + Scheduler**
- [ ] 新增 `engine/scheduler.py`：Conflict-aware Scheduler，管理衝突圖與排程
- [ ] Analyzer 完成後回報 `impacted_files`，Scheduler 動態更新衝突圖
- [ ] 所有 issue 一律從 main 建立 branch（含衝突組）
- [ ] 衝突組的後序 Implementer 收到前序修改摘要作為上下文（語義對齊，非 branch 繼承）
- [ ] Batch 結束後產出結構化總結報告（獨立組 / 衝突組含建議 merge 順序 / 失敗）

### 批次執行相容性

Orchestrator-Worker 與批次執行有兩個層次：

**層次 A：Per-issue Orchestrator（基礎）**

```
Batch Runner（迴圈）
└── Issue 1 → 自己的 Orchestrator → Analyzer → Implementer → Tester
└── Issue 2 → 自己的 Orchestrator → Analyzer → Implementer → Tester
└── Issue N → ...
```

每個 issue 有自己的 Orchestrator，按固定順序依序執行，issue 間彼此隔離。
簡單、易實作，但無跨 issue 協調能力。

**層次 B：Super Orchestrator + Conflict-aware Scheduler（進階）**

```
t=0   所有 Analyzer 並行（只讀，零衝突風險）
      [A1][A2][A3]...[A10]
       ↓  各自完成時回報 impacted_files

t=?   Scheduler 動態更新衝突圖，有空位立刻 spawn Implementer
      ├── I2 start（無衝突，A2 完成即跑）
      ├── I1 start（無衝突，A1 完成即跑）
      ├── I3 wait （與 I1 碰同一個檔案，等 I1 + T1 完成後才跑）
      └── ...

t=?   Tester 隨對應 Implementer 完成後立刻 spawn
      ├── T2 start（I2 完成）
      ├── T1 start（I1 完成）
      └── ...

t=end 全部 N 個 issue 完成，無不必要等待
```

Scheduler 的核心邏輯：
- 所有 Analyzer 並行（read-only，永遠安全）
- Analyzer 完成後回報 `impacted_files`，Scheduler 更新衝突圖
- 衝突圖決定哪些 Implementer 可並行、哪些需序列化
- 唯一的等待是**有意義的**（真實的檔案衝突），不是浪費

**衝突組的 branching 策略（設計決策：all-from-main）**

所有 issue 的 Implementer **一律從 main 建立 branch**，包括衝突組：

```
main
 ├── bugfix/issue-1  (Button.tsx: fix A)
 └── bugfix/issue-3  (Button.tsx: fix B，同樣從 main 開出)

merge 順序（依 Orchestrator 建議）：
  bugfix/issue-1 → main  ✅ 乾淨
  bugfix/issue-3 → main  ⚠️  可能有衝突，人類需手動解
```

衝突組內的後序 Implementer 仍會收到「issue-1 已修改此檔案的以下內容」的上下文，
讓修復策略在語義上保持一致，**但 branch 本身不繼承 issue-1 的 commit**。

**選擇此策略的原因**：
- MR diff 乾淨（只含自己的修改），code review 友善
- 不產生「linked branch」的複雜依賴關係
- 代價是：衝突組在 merge 時可能需要人類解衝突

**總結報告的責任**：Orchestrator 在報告中明確標出衝突組的建議 merge 順序，
讓人類按順序操作，衝突也只需處理一次（merge 靠後的那個）。

> 層次 A 是 Stage 5 的初始實作目標，層次 B 是 batch 場景下的進階演化方向。

### MR 自動化流程

Tester PASS 後，Orchestrator 繼續執行以下自動化步驟：

```
Tester PASS
├── push branch（已有）
├── 建立 MR / PR
│   ├── GitHub → gh pr create
│   └── GitLab → glab mr create
├── 取得 MR/PR ID → 從平台撈 diff
│   ├── GitHub → gh pr diff <id>
│   └── GitLab → glab mr diff <id>
├── spawn AI Reviewer subagent
│   ├── 輸入：原始 issue + 從平台撈回的 MR diff
│   │         ↑ 不含 analyze.md / implement.md，確保 Reviewer 視角獨立
│   ├── Review 評論寫回平台 MR（人類進 MR 即可看到）
│   │   ├── GitHub → gh pr review <id> --comment / --approve / --request-changes
│   │   └── GitLab → glab mr note <id> / glab mr approve <id>
│   ├── APPROVE → MR 標記 approved，等待人類 merge
│   └── REQUEST CHANGES → 評論留在 MR 上 → 回饋 Implementer → retry → 重跑
└── 人類進 GitLab / GitHub，看到帶有完整 AI review 紀錄的 MR，做最終 merge 決策
```

**平台相容性**：agent-fix（GitHub）與 agent-bugfix（GitLab）使用不同 CLI 工具，
Orchestrator 根據 `config.yaml` 的 `git_platform: github | gitlab` 切換命令。

**人類審查閘門原則**：AI 負責建 MR 和初審（效率），人類保留最終 merge 決定權（品質把關）。

### 總結報告格式

所有 issue 跑完後，Orchestrator 輸出總結，**明確列出 merge 順序**，讓人類照著操作：

```
=== Batch 修復完成 ===

獨立組（任意順序 merge）：
  ✅ issue-2  → MR #42  bugfix/issue-2-search-result
  ✅ issue-4  → MR #43  bugfix/issue-4-login-redirect
  ✅ issue-7  → MR #44  bugfix/issue-7-avatar-display

衝突組（請依序 merge）：
  1. ✅ issue-1  → MR #45  bugfix/issue-1-button-text
  2. ✅ issue-3  → MR #46  bugfix/issue-3-button-style  ← 需在 issue-1 merge 後再 merge

失敗（需人工介入）：
  ❌ issue-5   retry 3 次仍 FAIL，reports/issue-5/test-retry-3.md
  ❌ issue-9   Analyzer 無法定位 root cause，reports/issue-9/analyze.md
```

### 設計決策（待確認）

- subagent 的 spawn 機制：複用現有 `create_session()` 還是新抽象層？
- Orchestrator 是否需要有自己的 LLM session，或純 Python 邏輯？
- retry 上限：Orchestrator 層統一管理 vs 各 subagent 自己 retry？
- Branching 策略採 all-from-main：MR diff 乾淨，代價是衝突組 merge 時需人類手動解衝突
- GitHub / GitLab 無原生 PR dependency，衝突組的正確 merge 順序由總結報告提示人類；如需強制依賴可評估 Graphite 等第三方工具

---

## 階段 6：並行執行 — Git Worktree（v3.3，規劃中）

- [ ] 每個 issue 建立獨立 git worktree（temp branch）
- [ ] `asyncio.gather` 並行執行 `_execute_workflow()`（可設 max_workers）
- [ ] PASS 後 merge worktree；FAIL 後 discard
- [ ] Config：`batch.parallel: true`、`batch.max_workers: 3`

## 階段 7：Retro 機制 — Skill 持續進化（規劃中）

> **目標**：每次修復工作流結束後，可透過 retro 階段提煉經驗，持續改善 skills 與專案配置。

### 設計決策（待確認）

- [ ] 觸發方式：獨立 CLI 指令 `agent-fix retro <issue-id>`（優先）vs `run --retro` flag
- [ ] 要不要 human-in-the-loop？（CLI 互動收集使用者觀察）
- [ ] Layer 1 skill PR 門檻（累積 3+ 同類 issue？or 每次？）

### 核心功能

- [ ] 新增 `bugfix-retro` skill（獨立 session，讀取三個 phase 報告 + 使用者觀察）
- [ ] Retro 報告分層標記：Layer 1（Generic Skill → PR candidate）vs Layer 2（Project Context → 改本地）
- [ ] 輸出 `issues/reports/<id>/retro.md`
- [ ] 新增 CLI 指令 `agent-fix retro <issue-id>`
- [ ] 跨 issue 分析 `agent-fix retro --cross --since <date>`
- [ ] 新增 `docs/retro-log.md` 作為 retro 索引

### 改善落地流程

```
retro 發現改善點
       ↓
  本地先改 + 跑幾次驗證
       ↓
  ┌────────────┐
  │ 有效 + 通用 │ → PR 回 agent-fix
  │ 有效 + 特殊 │ → 留本地 / 轉 Layer 2 config
  │ 無效       │ → revert
  └────────────┘
```

### 風險注意

- Retro token 成本：用獨立 session + 較便宜 model
- 避免 over-fit：跨 issue 分析比單次 retro 更重要
- 避免 skill 碎片化：設 threshold（同類問題 3+ 次才改 skill）

## 階段 8：整合 behavior-validation Skill（待實作）

> **背景**：`.github/skills/behavior-validation/` 提供 Playwright-based 瀏覽器驗證能力，應取代 `bugfix-test` Phase 4 目前使用的 `agent-browser` CLI 佔位符。

### 需要做的事

- [ ] **`bugfix-test/SKILL.md` Phase 4 改寫**：移除 `agent-browser` CLI 指令，改為說明透過 `BehaviorValidator` Python API 執行瀏覽器驗證
  ```python
  from executor import BehaviorValidator
  validator = BehaviorValidator(project_root=..., port=...)
  report = await validator.validate(issue_id=..., dynamic_scenario={...})
  ```
- [ ] **Skills 路徑整合方案（擇一）**：
  - 方案 A（推薦）：在 `agent-fix/skills/` 加入 `behavior-validation/` symlink 指向 `.github/skills/behavior-validation/`
  - 方案 B：`config.yaml` 新增 `skills.external_directories`，`skill_loader.py` 支援多路徑查找
- [ ] **`PLAYWRIGHT_HEADLESS` 環境變數**：確認 agent-fix 執行時的 headless 預設行為（CI 環境應為 `true`）
- [ ] **`bugfix-test` 觸發條件清楚化**：在 SKILL.md 說明何時觸發行為驗證（`verification_method == "e2e"` 或 issue 包含 UI 互動）

### 設計決策（待確認）

- behavior-validation 是否要 pip install 為獨立套件，還是保持 source-level import？
- 如果 agent-fix 做成 PyPI 套件，behavior-validation 是否隨之打包？

---

## 階段 9：獨立 Plugin（可選，待架構穩定後進行）

- [ ] 將通用 skills 包裝為 `.claude-plugin/` 格式
- [ ] 建立 `plugin.json`、`marketplace.json`
- [ ] 發佈到 Claude Code marketplace 或內部分享
- [ ] 各專案透過 `claude plugin add` 安裝

---

## 工具替換記錄

| 原工具                  | 新工具                        | 原因                              |
| ----------------------- | ----------------------------- | --------------------------------- |
| Pydantic models         | Markdown 結構化輸出           | 不跨 session 傳遞，不需要嚴格型別 |
| LangGraph StateGraph    | Python 迴圈 + skill loader    | 序列工作流不需要 graph            |
| GitHub Copilot SDK only | 多 SDK Adapter                | 可切換 Copilot / Claude / OpenAI  |
| module-level init       | `engine/workflow.py` 延遲載入 | 避免 import 時 sys.exit           |

## 相關連結

- **agent-bugfix**（公司版）：GitLab 內部
- **GitHub**：`https://github.com/noni2she/agent-fix`
