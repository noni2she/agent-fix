# Architecture — v3.1 (Skill-Based + SDK Adapter)

> 最後更新：2026-04-09

## 設計理念

v3.1 在 v3.0 Skill-Based 架構上加入 **SDK Adapter 層**，讓底層 AI SDK 可無痛抽換。

**Project context 由 `config.yaml` 動態生成**，支援任意專案——無需修改 skills，只需提供對應的配置檔案即可。

```
┌─────────────────────────────────────────────────┐
│  main.py — Python loop                          │
│  config.yaml 驅動，load_project_context() 生成  │
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│  engine/                                        │
│  config.py        — Pydantic YAML 驗證          │
│  project_spec.py  — TACTICAL 判斷邏輯            │
│  skill_loader.py  — 讀取 SKILL.md               │
│  agent_runner.py  — Session 管理（adapter 無關） │
│  tools.py         — 自訂業務工具                │
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│  engine/adapters/                               │
│  base.py          — AgentEvent/Session/Adapter  │
│  copilot_adapter  — GitHub Copilot SDK          │
│  claude_adapter   — Anthropic Claude SDK        │
│  openai_adapter   — OpenAI Agents SDK           │
└─────────────────────────────────────────────────┘
```

## Config-Driven Project Context

`load_project_context()` 從 `ProjectConfig` 動態生成 Markdown，注入每個 phase prompt：

```python
# config.yaml → ProjectConfig → load_project_context() → Markdown
project_context = load_project_context()
analyze_msg = f"{project_context}{analyze_body}\n\n---\n..."
```

生成內容包含：
- 指令（TypeScript check、ESLint、dev server）
- TACTICAL 判斷條件表格（從 paths + high_risk_keywords 生成）
- 專案結構（monorepo 類型、shared packages/components、isolated modules）

## Session 策略

| Phase | Session | 原因 |
|-------|---------|------|
| analyze + implement | 共用主 session | implement 需要 analyze 讀過的檔案 context |
| test | 每次 fork 新 session | 獨立 context 省 token |
| implement-retry | 回到主 session | 帶失敗回饋 + 完整歷史 |

## Skills 架構

```
bugfix-workflow/skills/   ← 通用流程邏輯（不含專案細節）
  bugfix-analyze/SKILL.md
  bugfix-implement/SKILL.md
  bugfix-test/SKILL.md

config.yaml               ← 專案特定配置（取代 SKILL.md 的專案 context）
```

使用者也可在 `config.skills.directories` 指向自訂 skills 目錄，覆寫預設行為。

## SDK Adapter 設計

只有 `engine/adapters/` 內有 SDK 耦合：

| 耦合點 | 在 adapter 內處理 |
|--------|-----------------|
| Session 建立 | `create_session()` |
| 工具註冊格式 | `build_tools()` |
| 事件監聽 | `CopilotAdapter._normalize_event()` |
| Agentic loop | Claude/OpenAI adapter 自行管理 |
| 訊息發送 | `send()` |

`agent_runner.py`、`tools.py`、`main.py`、skills 全部 SDK 無關。

切換 SDK：
```bash
export SDK_ADAPTER=copilot  # GitHub Copilot SDK（預設）
export SDK_ADAPTER=claude   # anthropic>=0.40.0
export SDK_ADAPTER=openai   # openai-agents>=0.0.3
```

## 工具上限

| Phase | 上限 | 警告點 |
|-------|------|--------|
| analyze | 50 | 25, 35, 45 |
| implement | 30 | 15, 22, 27 |
| test | 40 | 20, 30, 35 |

警告透過 `session.pending_messages` 注入（Claude/OpenAI 安全），不中斷正在執行的 loop。

## 模組職責

| 模組 | 職責 |
|------|------|
| `main.py` | 載入 config、skills，執行 Python loop，路由決策 |
| `config.py` | YAML 驗證（Pydantic），模板變數替換 |
| `project_spec.py` | 基於 config 計算 TACTICAL 條件 |
| `skill_loader.py` | 讀取 SKILL.md，解析 frontmatter + body |
| `agent_runner.py` | Session 管理，工具上限警告，執行統計 |
| `tools.py` | 3 個自訂工具（tsc/eslint/tech debt），讀 config 指令 |
| `adapters/` | SDK 適配層，標準化 AgentEvent |
