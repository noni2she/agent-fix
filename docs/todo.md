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
> **解法**：引入 Orchestrator 作為 Team Lead 層，每個 phase 由獨立 subagent 執行。
> Orchestrator 負責兩件事：（1）精確控制每個 subagent 的輸入內容（認知隔離），
> （2）在 spawn 下一個 subagent 前，語義驗證上游 artifact 是否符合對應 SKILL.md 的規範。

### 架構設計

```
Orchestrator（路由層：依上游產物的 flag 決定 spawn，不做獨立分析）
├── spawn → Analyzer subagent     輸入：issue 描述（僅此）
│                                 輸出：analyze.md（含 needs_design_phase flag）
├── [條件式] spawn → Designer subagent  僅在 needs_design_phase = true 時觸發
│                                 輸入：analyze.md + ux-guidelines.csv（依 Category grep）
│                                 輸出：design.md（候選方案列表 + UX 評估 + 選定方案）
├── spawn → Implementer subagent  輸入：analyze.md + design.md（若存在，否則僅 analyze.md）
│                                 輸出：implement.md + code diff
└── spawn → Tester subagent       輸入：issue 原文 + code diff（不含 analyze / implement）
                                  內部：storageState auth（login once，TTL 快取，Tester 自行管理）
                                  輸出：test.md (PASS / FAIL)
        │
        └── [PASS] → push branch + 建立 MR/PR → 交接 MR ID 給 Issue Review Orchestrator
```

### Orchestrator 稽核模型（Team Lead）

Orchestrator 不介入 subagent 執行過程，在每次 spawn 前語義驗證上游 artifact：

| 驗證時機 | 驗證對象 | 通過條件 |
|---------|---------|---------|
| spawn Designer 前 | analyze.md | 關鍵 step 有執行證據（`[tested]`/`[inferred]` 標籤、Browser Reproduction Issues 欄位） |
| spawn Implementer 前 | analyze.md | `status = confirmed`，`confidence > 0.6`，root cause file + line 存在 |
| spawn Tester 前 | implement.md | 修改範圍與 analyze.md 的 `impacted_files` 一致 |
| spawn Issue Review 前 | test.md | `status = PASS` |

驗證不通過 → retry（不超過上限）→ 觸發 Checkpoint。

> **Artifact 設計原則**：SKILL.md 要求 subagent 在 artifact 的 `調查過程` 區塊記錄每個關鍵 step 的執行證據（`[tested]`/`[inferred]` 標籤），而非只有結論。Artifact 本身就是執行過程的稽核軌跡，Orchestrator 驗證 artifact，不侵入執行層，也不需要 tool_call_log。

---

> **目前過渡方案（Stage 5 前）**：UX 評估暫時內嵌於 Analyzer 的 Step 5，
> 由 analyze 自行完成方案列舉 + CSV grep + 選方案，輸出進 `analyze.md`。
> Stage 5 重構時，將此邏輯拆出為獨立 Designer subagent，職責不變，架構更清晰。

### Designer subagent 觸發條件

Analyzer 判斷以下任一條件成立時，設 `needs_design_phase: true`：

- 修復方案涉及 layout / scroll / overflow / modal / dialog
- 不同修復路徑的使用者體驗明顯不同（e.g. nested scroll vs sticky footer）
- 涉及互動回饋（loading / error / disabled state）且有多種實作選擇
- 涉及 touch target / form / navigation / animation

**不觸發**：純文字錯誤、純邏輯錯誤（條件反了）、missing prop、單一明確修復路徑

### 各角色資訊隔離規則

| Subagent | 能看到 | 不能看到 |
|----------|--------|---------|
| Analyzer | issue 原文 | 任何修復相關資訊 |
| Designer | analyze.md + ux-guidelines.csv | Analyzer 的推理過程 |
| Implementer | analyze.md + design.md（若存在） | Analyzer/Designer 的推理過程 |
| Tester | issue 原文 + diff | analyze.md / implement.md / design.md |
| （Issue Review 各 Reviewer，見 Stage 5.3）| MR diff（從平台撈）| analyze.md / implement.md / test.md |

### 需要做的事

**Skill 品質改善（與重構同步進行）**
- [ ] **Confidence Score 改為加權求和格式**：現行為 base 1.0 扣分制，改為 `S = Σ(wᵢ × sᵢ) / Σwᵢ`，每個 criterion 二元 {0,1}，wᵢ ∈ {1,2,3}（nice-to-have / important / must-have）；社群研究（Agentic Rubrics, RULERS）顯示此格式更透明、不易被 LLM 幻覺出「剛好過門檻的分數」

**核心架構**
- [ ] 新增 `engine/orchestrator.py`：Orchestrator 主控邏輯，負責 spawn subagent + 路由
- [ ] 各 phase 改為獨立 subagent session（`create_session` 各自呼叫）
- [ ] Orchestrator 控制每個 subagent 的輸入內容（資訊隔離）
- [ ] Orchestrator 在每次 spawn 前語義驗證上游 artifact（見稽核模型表格）
- [ ] retry 邏輯移至 Orchestrator 層（Tester FAIL → Orchestrator 決定是否 re-spawn Implementer）
- [ ] 現有 `workflow.py` 重構或保留為向後相容的 legacy mode
- [ ] CLI 新增 `--mode orchestrator`（預設）vs `--mode legacy`（目前一條龍）

**MR 自動化（Issue Fixing 端）**
- [ ] `config.yaml` 新增 `git_platform: github | gitlab`，Orchestrator 依此切換 CLI 命令
- [ ] Tester PASS 後自動 push branch + 建立 MR/PR，取得平台回傳的 MR/PR ID
- [ ] 將 MR ID 交接給 Issue Review Orchestrator（見 Stage 5.3）
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

所有 Implementer 一律從 main 建立 branch，含衝突組。衝突組的後序 Implementer 收到前序修改摘要作為語義上下文，但不繼承其 commit。MR diff 因此乾淨，代價是衝突組 merge 時可能需要人類手動解衝突。Orchestrator 總結報告標明建議 merge 順序。

> 層次 A 是 Stage 5 的初始實作目標，層次 B 是 batch 場景下的進階演化方向。

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

### 設計決策

- **Orchestrator 實作：LLM**：自行判斷 spawn 時機，透過 Python spawn 工具執行。Scheduler（衝突圖、拓撲排序）以 Python 工具形式嵌入。資訊隔離由 Python spawn 工具強制執行，不靠 LLM 自律。
- **合規驗證策略：artifact 語義驗證，非執行軌跡追蹤**：Orchestrator 讀 artifact 做語義驗證，不追蹤 tool_call_log。SKILL.md 要求 subagent 在 artifact 中記錄執行證據（`[tested]`/`[inferred]` 標籤等），artifact 本身即稽核軌跡。
- **Analyze 階段採 Progressive Disclosure（Gated Context Reveal）**：Orchestrator 分段揭露 SKILL.md 指令（Step 0.0 → Step 0.1–0.4 → Steps 1–4），每段驗證通過才送下一段。解決的問題：LLM 同時看到完整指令和終點目標時，會產生 context rot（注意力稀釋）——重現細節被忽略，碰到障礙傾向跳過並合理化走向靜態分析。失敗只 retry 當前段，不重跑整個 phase。社群對應術語：Progressive Disclosure；理論依據見 `docs/research.md`（agent-fix repo）。
- **不使用 Claude Code Task tool**：Task tool 預設繼承 parent context，無法保證資訊隔離（見 [GitHub issue #20304](https://github.com/anthropics/claude-code/issues/20304)）。agent-fix 自己實作 spawn。
- **不引入 Agent Teams / Claude Managed Agents**：Subagents 父子階層已足夠，worker 間無橫向溝通需求；Managed Agents 為雲端服務，不適用本地 CLI。
- **Branching 策略採 all-from-main**：MR diff 乾淨，衝突組 merge 時需人類手動解衝突。
- **retry 上限**：Orchestrator 層統一管理，各 subagent 不自己 retry。

---

## 階段 5.3：Issue Review — 獨立 Orchestrator-Worker（規劃中）

> **定位**：與 Issue Discovery（Stage 11）、Issue Fixing（Stage 5）並列的第三組 Orchestrator-Worker。
> Issue Fixing 建立 MR 後，以 MR ID 作為交接介面，Issue Review Orchestrator 接手執行多維度審查。
> 各 Reviewer subagent 只能看到 MR diff，不可存取 analyze.md / implement.md / test.md，
> 確保每個維度的評審視角獨立。

### 架構設計

```
Issue Review Orchestrator
│  輸入：MR ID（由 Issue Fixing 交接）
│
├── spawn → Code Reviewer subagent
│     輸入：原始 issue + MR diff（從平台撈）
│     輸出：code-review.md（品質評分 + 評論）
│     └── 評論寫回平台 MR
│
├── spawn → UAT Runner subagent
│     輸入：原始 issue + 修復後 diff
│     工具：chrome-devtools MCP（在 dev server 上執行驗收操作）
│     輸出：uat.md (PASS / FAIL + screenshots)
│     └── 評論寫回平台 MR
│
├── [條件式] spawn → Security Reviewer subagent
│     觸發條件：issue 或 diff 含 auth / api / token / permission / data 等關鍵字
│     輸入：MR diff
│     輸出：security.md
│     └── 評論寫回平台 MR
│
└── [條件式] spawn → Performance Reviewer subagent
      觸發條件：issue 或 diff 含 render / load / scroll / animation / bundle 等關鍵字
      輸入：MR diff
      輸出：performance.md
      └── 評論寫回平台 MR

最終判決（Orchestrator 彙整）：
  全部通過 → APPROVED → MR 標記 approved，等待人類 merge
  任一失敗 → REQUEST CHANGES → 回饋 Issue Fixing Orchestrator → retry
```

### 三組 Orchestrator-Worker 全局關係

```
Layer 0：Issue Discovery Orchestrator（time-driven，長駐）
  └── 發現 issue → 建立 issue record → 觸發 ↓

Layer 1：Issue Fixing Orchestrator（task-driven）
  Analyzer → [Designer] → Implementer → Tester
  └── PASS → push branch + 建 MR → 通知 ↓

Layer 2：Issue Review Orchestrator（event-driven，MR ID 觸發）
  Code Reviewer + UAT Runner + [Security Reviewer] + [Performance Reviewer]
  └── APPROVED → 等待人類 merge
  └── REQUEST CHANGES → 回饋 Layer 1 retry
```

### 需要做的事

- [ ] 新增 `engine/review_orchestrator.py`：Issue Review 主控邏輯
- [ ] Code Reviewer subagent：從平台撈 MR diff，評論寫回 MR
- [ ] UAT Runner subagent：整合 chrome-devtools MCP 執行驗收操作
- [ ] Security Reviewer subagent（條件式）：關鍵字 trigger 規則
- [ ] Performance Reviewer subagent（條件式）：Lighthouse / bundle size 基準
- [ ] `config.yaml` 新增 `review` 區塊：`enabled`、各 reviewer 的 `enabled` flag
- [ ] Issue Fixing → Issue Review 交接介面設計（MR ID + 原始 issue 的傳遞方式）
- [ ] 最終判決邏輯：全部通過才 APPROVE，否則 REQUEST CHANGES + 回饋 retry

---

## 階段 5.5：Comment-driven Retry — 人類 Review 回饋閉環（規劃中）

> **背景**：Issue Review 完成初審後，人類仍可能在 MR 上留下修改意見。
> 與其讓人類自己追蹤並手動重啟流程，不如讓 agent 監聽 MR comment 事件，
> 自動將人類的 review 意見轉化為新一輪 Implementer 任務，形成完整的 async 回饋閉環。

### 觸發機制

**推薦：CI/CD webhook 觸發（不需常駐 server）**

```
人類在 MR 留 comment
  ├── GitHub: pull_request_review_comment 事件 → GitHub Actions
  └── GitLab: Note Hook（MR 新增評論）→ GitLab CI
      └── 執行 agent-fix respond-comment --mr <id>
```

**備選：webhook listener（常駐 server）**
- agent-fix 需內建 HTTP endpoint 接收 webhook
- 適合 CI/CD 環境受限時，但多了維運成本

### 執行流程

```
webhook 觸發（人類新增 comment）
├── 撈 MR 上所有 unresolved 人類 comment
│   ↑ 依 author ID 過濾，排除 AI Reviewer bot 自己的評論（防無限迴圈）
├── spawn Implementer subagent
│   ├── 輸入：原始 issue + 當前 MR diff + unresolved comment 清單
│   └── 嘗試解決 comment 指出的問題，push new commit 到同一 branch
│       ↑ MR 自動更新，不需重建
├── spawn AI Reviewer 重新 review 新 diff
│   └── review 結果寫回 MR（同 Stage 5 流程）
└── 人類確認 comment resolved → 做最終 merge 決策
```

### 設計細節

| 項目 | 設計決策 |
|------|---------|
| 觸發範圍 | 預設只回應 unresolved threads；已 resolved 的 comment 略過 |
| 觸發關鍵字 | 可選：所有 comment 都觸發 vs 需要寫 `/ai-fix` 才觸發（config 控制）|
| 防迴圈 | 依 bot account author ID 過濾，AI Reviewer 的評論不觸發 retry |
| 對話回合上限 | config 可設最大輪數（預設 3），超過則通知人類需手動處理 |
| 平台相容 | GitHub（`pull_request_review_comment`）/ GitLab（Note Hook）皆支援 |

### 需要做的事

- [ ] `config.yaml` 新增 `comment_retry` 區塊：`enabled`、`trigger_keyword`、`max_rounds`
- [ ] 新增 CLI 指令 `agent-fix respond-comment --mr <id> [--platform github|gitlab]`
- [ ] 撈 unresolved comment 邏輯（過濾 bot author、過濾 resolved threads）
- [ ] Implementer subagent 接受 comment 清單作為額外輸入
- [ ] CI/CD 範本：提供 GitHub Actions workflow 與 GitLab CI job 範例供使用者複製貼上
- [ ] 對話輪數計數與上限通知

---

## 階段 6：Mock Reproduction — 備用重現手法（規劃中）

> **背景**：瀏覽器重現依賴真實環境（登入、session、dev server），在 AI 操作場景下
> 容易因環境因素失敗（如未登入導致 API 4xx）。需要一種不依賴真實環境的備用重現手法，
> 透過 mock 隔離依賴、模擬操作步驟，以 TDD 方式證明 bug 存在：
> 先確認 test FAIL（bug 重現），修復後確認 test PASS（bug 消失）。

### 定位

**不是瀏覽器重現的替代，而是同等地位的另一種重現方式**，由 issue 特性決定使用哪種：

| Issue 特性 | 優先手法 |
|-----------|---------|
| 需要真實 session / 登入 / SSE / WebSocket | Browser Reproduction |
| 純元件行為（props → output）| Mock Reproduction |
| 元件互動（click → state 變化）| Mock Reproduction（穩定）或 Browser |
| 導航 / 路由跳轉 | Browser Reproduction |

### 前置條件

- 目標專案需有 test infra（Jest / Vitest + @testing-library/react + msw）
- `config.yaml` 新增 `reproduction.mock.enabled`，無 test infra 的專案設為 false

### 架構設計

```
reproduce step
  ├── Stage 1：Browser Reproduction（chrome-devtools MCP）
  │     └── 成功 → confirmed，繼續根因分析
  │     └── 失敗（環境因素）→ 記錄問題 → 嘗試 Stage 2
  └── Stage 2：Mock Reproduction
        └── AI 產出 per-issue test file（issues/reproductions/<issue-id>.test.tsx）
        └── 跑一次確認 FAIL（bug 重現）→ confirmed，繼續根因分析
        └── 無法寫出有效 mock test → need_more_info，停止
```

### Mock Test 規範

- **位置**：`issues/reproductions/<issue-id>.test.tsx`（per-issue，隨 issue 生滅）
- **護欄**：test 必須先跑一次確認 FAIL，否則視為無效（防止 false green）
- **可選升級**：bug 修復後，有意義的 test 可移入專案的 `__tests__/` 作為 regression test

### 需要做的事

**前置**
- [ ] 確認目標專案 test infra 就緒（Jest / Vitest + RTL + msw）
- [ ] `config.yaml` 新增 `reproduction` 區塊：`mock.enabled`、`mock.runner`（jest | vitest）

**Skill**
- [ ] 新增 `reproduce-via-mock` skill（獨立 SKILL.md）
- [ ] 說明如何 mock store（Zustand）、API（msw）、router（next/navigation）
- [ ] 說明「先確認 FAIL 再繼續」的護欄機制
- [ ] `bugfix-analyze` Step 0 加入 reproduction 方式選擇邏輯

**Workflow**
- [ ] `run_typescript_check` 等 quality check 工具補充 mock test runner 指令

---

## 階段 7：並行執行 — Git Worktree（v3.3，規劃中）

- [ ] 每個 issue 建立獨立 git worktree（temp branch）
- [ ] `asyncio.gather` 並行執行 `_execute_workflow()`（可設 max_workers）
- [ ] PASS 後 merge worktree；FAIL 後 discard
- [ ] Config：`batch.parallel: true`、`batch.max_workers: 3`

## 階段 8：Retro 機制 — Skill 持續進化（規劃中）

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

## 階段 9：整合 behavior-validation Skill（待實作）

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

## 階段 10：獨立 Plugin（可選，待架構穩定後進行）

- [ ] 將通用 skills 包裝為 `.claude-plugin/` 格式
- [ ] 建立 `plugin.json`、`marketplace.json`
- [ ] 發佈到 Claude Code marketplace 或內部分享
- [ ] 各專案透過 `claude plugin add` 安裝

---

## 階段 11：Issue Discovery Layer — 主動發現問題（規劃中）

> **背景**：目前 agent-fix 是被動的——等使用者提供 issue 清單才啟動修復。
> Issue Discovery Layer 作為 Orchestrator 的上層，負責主動掃描或探索問題，
> 再餵給 Orchestrator 觸發修復流程，形成完整的自動化閉環。
>
> 此層與 Orchestrator 是**平行存在的獨立系統**，透過 issue record 介面交接，
> 不是 Orchestrator 的子角色，也不適合由 Orchestrator 兼任（生命週期與職責不同）。

### 層級關係

```
Layer 0：Issue Discovery（time-driven，長駐，主動發現）
  ├── Issue Poller      — 定時掃描已知來源有沒有新 issue
  ├── Regression Runner — 定時對 main branch 跑回歸測試
  └── Exploratory Agent — LLM 主動操作 UI，探索潛在 bug
          │
          │ 發現問題 → 建立 issue record（標準格式）
          ▼
Layer 1：Orchestrator（task-driven，有料才啟動，協調修復）
  └── 現有 Stage 5 架構
```

### 三個子角色

**Issue Poller**（Python scheduler，不需要 LLM）
- `agent-fix watch` 指令，定時呼叫 `IssueSourceAdapter.list_all()` 掃描新 issue
- 發現新 issue → 自動觸發 `run_batch_workflow()`
- 現有 IssueSourceAdapter 抽象幾乎現成可用

**Regression Runner**（Python + CI/CD，不需要 LLM）
- 對 main branch 定時跑 regression test（可接 CI/CD 觸發）
- 測試失敗 → 自動建立 issue record → 丟給 Orchestrator

**Exploratory Agent**（LLM agent，主動探索）
- 獨立 LLM session，用 Playwright 操作 UI 主動尋找潛在 bug
- 發現問題 → 格式化為標準 issue record → 丟給 Orchestrator
- 與 Orchestrator 完全解耦，透過 issue record 介面交接

### 需要做的事

- [ ] 設計 issue record 標準格式（Layer 0 → Layer 1 交接介面）
- [ ] 新增 `agent-fix watch` 指令（Issue Poller，定時掃描 + 觸發）
- [ ] Regression Runner：CI/CD 測試失敗 → 自動建立 issue record
- [ ] Exploratory Agent：Playwright-based LLM session，主動發現 UI bug
- [ ] Layer 0 觸發頻率與排程配置（`config.yaml` 新增 `discovery` 區塊）

---

## 工具替換記錄

| 原工具                  | 新工具                        | 原因                              |
| ----------------------- | ----------------------------- | --------------------------------- |
| Pydantic models         | Markdown 結構化輸出           | 不跨 session 傳遞，不需要嚴格型別 |
| LangGraph StateGraph    | Python 迴圈 + skill loader    | 序列工作流不需要 graph            |
| GitHub Copilot SDK only | 多 SDK Adapter                | 可切換 Copilot / Claude / OpenAI  |
| module-level init       | `engine/workflow.py` 延遲載入 | 避免 import 時 sys.exit           |

---

## AGENT.md — 行為契約使用場景

> AGENT.md 定義 agent 在碰到障礙時的 **problem-solving 思維協議**，
> 與 Karpathy Guidelines（coding 行為）互補，一起作為所有 phase 的底層人格層。

### 場景 1：Orchestrator-Worker 架構

```
┌──────────────────────────────────────────────────────────────────┐
│                      Orchestrator Agent                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ System Prompt:                                              │  │
│  │   • Karpathy Guidelines       ← 通用 coding 規範           │  │
│  │   • AGENT.md                  ← problem-solving 契約       │  │
│  │   • Orchestrator SKILL.md     ← 拆派任務 / 整合結果        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Issue 進來 → 拆解 → 派發子任務                                  │
└────┬──────────┬──────────┬──────────┬──────────┬─────────────────┘
     │          │          │          │          │
     ▼          ▼          ▼          ▼          ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │Analyzer│ │Designer│ │ Fixer  │ │ Tester │ │Reviewer│
 │ Worker │ │ Worker │ │ Worker │ │ Worker │ │ Worker │
 └────────┘ └────────┘ └────────┘ └────────┘ └────────┘

  每個 Worker 的 system prompt 都包含：
    ┌───────────────────────────────────┐
    │ Karpathy Guidelines   (共用)      │  ← coding 行為規範
    │ AGENT.md              (共用)      │  ← problem-solving 規範
    │ Worker-specific SKILL (角色專屬)  │  ← 各 phase 流程
    └───────────────────────────────────┘
```

**好處**：
- 5 種 Worker 不需要各自定義「碰到牆怎麼辦」
- Orchestrator 收到的 worker 結果格式統一（`[tested]` / `[inferred]` 標籤一致）
- 加新 Worker 角色時只需寫該角色的 SKILL.md，行為規範自動繼承

---

### 場景 2：Claude Plugin 化（Stage 10）

```
your-bugfix-plugin/
├── .claude-plugin/
│   └── plugin.json           ← plugin metadata
├── CLAUDE.md                 ← Karpathy Guidelines（plugin 安裝後注入 system prompt）
├── AGENT.md                  ← problem-solving 契約（同上自動注入）
└── skills/
    ├── bugfix-analyze/SKILL.md
    ├── bugfix-implement/SKILL.md
    ├── bugfix-test/SKILL.md
    └── bugfix-orchestrate/SKILL.md
```

**運作方式**：

```
使用者: /skill bugfix-analyze CHATAPP-5339
                  │
                  ▼
┌──────────────────────────────────────────────────────────┐
│ Claude 載入 plugin                                        │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Auto-loaded into system context:                    │  │
│ │   1. CLAUDE.md  (Karpathy Guidelines)               │  │
│ │   2. AGENT.md   (problem-solving 契約)              │  │
│ └─────────────────────────────────────────────────────┘  │
│                          ↓                                │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Triggered skill: bugfix-analyze/SKILL.md            │  │
│ └─────────────────────────────────────────────────────┘  │
│                          ↓                                │
│           Claude 執行，遵守底層行為規範 + phase 流程      │
└──────────────────────────────────────────────────────────┘
```

**好處**：
- 不依賴 `workflow.py` 也能單獨跑（直接在 Claude Code / Claude Desktop 使用）
- 別人安裝 plugin 後自動繼承行為規範
- 可宣告 `dependencies: ["karpathy-guidelines"]` 疊加 Karpathy 層，不需重複定義

---

### 三層人類介入模型

```
Layer 0：Agent 自處（AGENT.md 定義範圍）
  碰到障礙 → tool inventory → 嘗試 → 記錄 → 繼續
  ↓ 自處失敗（confidence < 0.6 或 N 次 retry 都 FAIL）

Layer 1：In-flight Checkpoint（workflow.py 觸發，同步 blocking）
  暫停 workflow → 發通知 → 等人類補充 context → 繼續
  ↓ checkpoint 通過或未觸發

Layer 2：MR Review（非同步 non-blocking，人類最終審核）
  自動 commit & push → 自動開 MR → 人類 review → 留 comment
  → Agent 接收 comment → 修正 → push 新 commit → 人類 merge
```

---

## 相關連結

- **agent-bugfix**（公司版）：GitLab 內部
- **GitHub**：`https://github.com/noni2she/agent-fix`
