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

## 階段 5：整合 behavior-validation Skill（待實作）

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

## 階段 6：獨立 Plugin（可選，待架構穩定後進行）

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
