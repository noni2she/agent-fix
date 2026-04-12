# Agent Fix — 發展路線

> 最後更新：2026-04-11

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

## 階段 4：Retro 機制 — Skill 持續進化（規劃中）

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

## 階段 5：獨立 Plugin（可選，待架構穩定後進行）

- [ ] 將通用 skills 包裝為 `.claude-plugin/` 格式
- [ ] 建立 `plugin.json`、`marketplace.json`
- [ ] 發佈到 Claude Code marketplace 或內部分享
- [ ] 各專案透過 `claude plugin add` 安裝

---

## 工具替換記錄

| 原工具 | 新工具 | 原因 |
|--------|--------|------|
| Pydantic models | Markdown 結構化輸出 | 不跨 session 傳遞，不需要嚴格型別 |
| LangGraph StateGraph | Python 迴圈 + skill loader | 序列工作流不需要 graph |
| GitHub Copilot SDK only | 多 SDK Adapter | 可切換 Copilot / Claude / OpenAI |
| module-level init | `engine/workflow.py` 延遲載入 | 避免 import 時 sys.exit |

## 相關連結

- **agent-bugfix**（公司版）：GitLab 內部
- **GitHub**：`https://github.com/noni2she/agent-fix`
