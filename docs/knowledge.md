# Agent-Fix 開發累積知識

> 從 agent-fix v1 → v4 自建 harness/adapter 過程累積的工程知識。本檔目的：
> 在「依附 managed runtime」之前，把這段時間繳的學費結晶下來，避免知識隨 code 刪除而流失。

## 1. Harness Engineering 基礎

### Guides × Sensors 框架
LLM agent 的可靠性來自兩條軸線並用：

- **Guides（提示式約束）**：寫在 system prompt 裡的規則（「最多用 5 次 evaluate_script」）。
  優點：表達自然、修改成本低。缺點：**統計性 enforcement**，會 decay。
- **Sensors（程式碼強制）**：在 tool dispatch 層攔截、計數、拒絕（`check_tool_blocked()`）。
  優點：**確定性 enforcement**，100% 可控。缺點：規則散落程式碼，難快速調整。

**判準**：規則違反的後果嚴重（context 爆掉、timeout、無限迴圈）→ 必須是 Sensor。
規則只是品味偏好（語氣、格式）→ Guide 即可。

### Constraint Decay 現象
Prompt 裡寫了 5 條規則，LLM 在第 20 次 tool call 後仍記得的可能只剩 2 條。
**Omission constraints（「不要做 X」）比 commitment constraints（「請做 Y」）decay 更快**，
因為 LLM 在生成時很難主動回想「我承諾過不做什麼」。

### Positive Prompt Injection
當 Sensor 攔截違規時，不要只回傳「❌ 禁止」，而是直接在錯誤訊息裡**告訴 LLM 接下來該做什麼**：

```
🚨 evaluate_script 已達 5 次上限。立即停止所有工具呼叫，輸出 Evidence Package：
observed: <實際行為>
objective_signals: <console 錯誤 / network 4xx-5xx>
instability_flags: <none / 列出>
reproduce_confidence: <0.0-1.0>
```

把「禁止」轉成「下一步指令」，LLM 才不會在原地打轉。

---

## 2. SDK Harness 行為差異（踩坑紀錄）

三個 SDK 都有 production-grade harness，但 agentic loop 的設計不同：

| SDK | Loop 擁有者 | 中途注入指令 | 事件模型 |
|---|---|---|---|
| Claude Agent SDK | 你（無狀態 API，自己跑 loop） | ✅ 在下一輪 `messages.create()` 之前注入 user message | Pull |
| OpenAI Agents SDK | 你（呼叫 `Runner.run_streamed()`）| ✅ `result.to_input_list()` 後附加，下次 run 帶入 | Pull-stream |
| Copilot SDK | SDK 內部 | ❌ 內部 loop 不讀 `pending_messages`，必須在 `session.send()` 之前拼進 message | Push（事件驅動） |

### 關鍵教訓
1. **跨 SDK 的「中途指令」要在 tool handler 攔截，不能靠 prompt 累積**
   `pending_messages` 機制對 Claude/OpenAI 有效，對 Copilot 失效。
   正確做法：把規則放在 `harness.py` 的 `check_tool_blocked()`，在 MCP handler / tool invoke 時返回錯誤訊息 — 三個 SDK 都會把 tool result 丟回給 LLM，這是唯一跨 SDK 都讀得到的注入點。

2. **async tool call 需要顯式 timeout**
   `MCPClientManager.call_tool_sync` 內建 30s timeout（`run_coroutine_threadsafe.result(timeout=30)`），
   但 `call_tool` async 版**沒有 timeout**。當 MCP server 卡住時，async 呼叫會無限阻塞 event loop。
   修法：`await asyncio.wait_for(session.call_tool(name, args), timeout=30)`。
   這個 bug 之前沒爆是因為 RCA 階段 `mcp_manager=None`，加上 phase-aware MCP filter 後才暴露。

3. **Token budget 各 SDK 都內建，不要自己再做一套**
   `agent_runner.py` 裡的 `_handle_tool_limit_warning` 系統（25/35/45 三段警告）
   是「LLM 自己看 prompt 知道剩多少」的設計 — 但其實 SDK 都會給 token usage event。
   下次該用 SDK 提供的 event 直接報告，不要自己 count。

---

## 3. MCP 整合知識

### 基本模式
```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(command=cmd, args=args)
cm = stdio_client(server_params, errlog=open("/dev/null", "w"))
read, write = await cm.__aenter__()
session = ClientSession(read, write)
await session.__aenter__()
await session.initialize()
tools_result = await session.list_tools()
```

### Tool 名稱格式
MCP server 回報的 tool name 是 **bare name**（`take_screenshot`、`read_file`），
沒有 `mcp__<server>__` 前綴。前綴是 Claude Code / 其他 client 自己加的展示名稱。
**自寫 MCP client 時不要假設前綴存在**。

### Phase-aware tool filtering
讓不同 phase 看到不同的 MCP server tools（REPRODUCE 只看 chrome-devtools、RCA 只看 Serena）：
1. 在 `_tool_info[tool.name]` 加 `"server": name` tag 紀錄來源
2. 寫一個 `_FilteredMCPView` 包 manager，過濾 `info.get("server") in allowed_servers`
3. Schema 取得函式（`get_tool_schema_for_claude` 等）只回傳 allowed 的，LLM 就看不到不該用的

**這個概念可以保留為 declarative config**（YAML：`phases.reproduce.mcp_servers: [chrome-devtools]`），
不一定要自寫 view class。

---

## 4. 三個 SDK 的事件標準化

不同 SDK 有不同的原生事件，要 normalize 成統一 `AgentEvent`：

| 標準事件 | Claude | OpenAI | Copilot |
|---|---|---|---|
| `message` | 從 `response.content[].text` 抽 | `event.name == "message_output_created"` → `ItemHelpers.text_message_output(item)` | `SessionEventType.ASSISTANT_MESSAGE` → `data.content` |
| `tool_start` | `block.type == "tool_use"` → `block.name` | `event.name == "tool_called"` → `item.function or item.name` | `SessionEventType.TOOL_EXECUTION_START` → `data.tool_name`（**注意：別跟 `EXTERNAL_TOOL_REQUESTED` 雙重計數**） |
| `usage` | `response.usage.input_tokens / output_tokens` | `result.usage.input_tokens / output_tokens` | `SessionEventType.ASSISTANT_USAGE` → 多種命名（`prompt_tokens` or `input_tokens`） |
| `idle` | stop_reason in ("end_turn", "max_tokens") | stream 結束 | `SessionEventType.SESSION_IDLE` |

**教訓**：每個 SDK 都會擴充新事件類型（Copilot SDK 升級會新增 `SessionEventType` 成員），
事件 dispatch 用 if/elif 比 dict 安全（dict 對未知 enum 會 KeyError）。

---

## 5. Behavior Validation 設計教訓

### 「不要當 REPL 用」
agent 寫一個 scenario → 失敗 → 改 selector → 再跑 — 這是 REPL 探索模式，不是驗證模式。
**用 view/bash/Read 探索頁面結構，scenario 寫對才呼叫 `run_behavior_validation`**。
解法：在 harness 加 `run_behavior_validation` 上限 3 次，逼 agent 先準備再執行。

### 真實使用者輸入模擬
React controlled input 對 `page.fill()` 反應不可靠（某些 react-hook-form 版本不觸發 onChange）。
正確做法：
```python
await page.click(selector)
await page.keyboard.type(value)
await page.press(selector, "Tab")  # blur 觸發 onBlur validation
await page.wait_for_selector(f"{submit}:not([disabled])", timeout=8000)
await page.click(submit)
```

### Auth state caching
登入是最慢、最易失敗的步驟。`page.context.storage_state(path=...)` 把 cookies + localStorage 序列化，
下次 `browser.new_context(storage_state=...)` 直接 restore。TTL（如 24h）後重新登入。
**沒這個機制，每個 issue 都重登一次 → 加總 timeout 風險爆增**。

### `set_files` 繞過 OS file picker
有些頁面要先上傳檔案才會渲染目標元件（例如 `pendingFiles` 為空就 redirect 回首頁）。
Playwright 的 `locator.set_input_files([path])` 直接設定 `<input type=file>` 的 files，
不用觸發 OS 原生 file picker。**這是行為驗證能跑到「上傳後的狀態」的關鍵 action**。

---

## 6. Workflow 設計：Orchestrator-Worker + Judge Pattern

### 為什麼分階段
單一 LLM session 跑 60 個 tool call → context 累積、token 暴增、規則 decay。
切成 phase（analyze / implement / test），每個 phase 獨立 session：
- 每個 phase 工具上限獨立計算
- Context 重新乾淨
- 失敗 retry 只重跑該 phase

### Judge Pattern
phase 結束後不立刻進下一個 phase，先讓 Orchestrator LLM **語義判斷**：
```
PROCEED       — phase 產出符合預期，繼續
RETRY         — phase 沒到位但有改善希望，重跑同一個 phase
NEED_MORE_INFO — issue 描述不夠，標 already_fixed / need_more_info 退出
CHECKPOINT    — 需要人類介入
```

判斷依據是 phase 產出的 artifact（`analyze.md`、`implement.md`、`test.md`）+ AGENTS.md 行為契約。

### Progressive Disclosure (Gated Context Reveal)
analyze phase 不一次給所有指令，分兩段：
- **Gate REPRODUCE**：先給 Step 0（瀏覽器重現）→ 拿到 Evidence Package
- **Gate RCA**：通過後才給 Steps 1-5（根源分析 + 報告）

每個 gate 收的 context 是「完成這個 step 的最小集」，token 大幅節省。

### Artifact 流轉
phase 之間靠 markdown 報告傳遞資訊，不靠 in-memory state：
```
analyze.md → implement.md → test.md → test-retry-N.md
```
好處：可恢復（中斷後從報告繼續）、可審計（人類可讀）、跨 session 安全。

---

## 7. 業界生態與決策觀念

### Claude Code vs Claude Agent SDK
- **Claude Code** = 完整產品（CLI / VSCode / 桌面 / 瀏覽器），人類互動驅動
- **Claude Agent SDK** = 從 Claude Code 抽出的引擎，程式驅動。2026/03 之前叫做「Claude Code SDK」
- 兩者**共用同一個 harness**，差別只是介面

### agentskills.io 標準
原本是 Anthropic 的 SKILL.md 格式，2026 年開源化為 `agentskills.io` 標準。
**35+ 個 agent 平台採用同一格式**：Claude Code、Cursor、Copilot、Codex、Hermes、Gemini CLI、OpenHands、Goose、Letta…
意思是：**skill 內容是跨平台保值資產，runtime 換不影響 skill**。

格式：
```
my-skill/
├── SKILL.md          # YAML frontmatter (name + description) + markdown 本體
├── scripts/          # 可選
├── references/       # 可選
└── assets/           # 可選
```

### Cursor 的 Harness 觀念
業界 2026 年共識：**Agent = Model + Harness**，且 **harness 才是產品本體**。
頂尖 coding agents（Claude Code / Cursor / Codex / Aider / Cline）的 harness 彼此差異 > 底層模型差異。
這代表自建 agent 的差異化空間，**主要在 harness 設計、不在底層 LLM**。

### Build vs Buy 思考
- 一次性任務 → 用 SDK 寫 script
- 重複性高、流程穩定、非核心競爭力 → **用大廠 framework 包領域邏輯**（你的位置）
- 重複性高、流程是公司核心競爭力 → 深度自建（Cursor 規模）

42% 的公司在 2024 年放棄自建 AI agent，主要原因是低估了 harness 投入成本。

---

## 8. 個人決策反思

### 「自建 harness」vs 「應用服務」是兩件事
過程中混淆了兩個目標：
- 「我想證明我能做出 agent」→ 動機是技能展示
- 「我想做 bug-fixing 自動化服務」→ 動機是產品/工具

這兩個目標的最佳路徑不同：
- 技能展示 → 寫個 minimal agent 跑通就好，**不要鋪設施**
- 應用服務 → **依附 managed harness，把心力放在領域層**（skill / edge case / 整合）

混淆的代價：花 6000 行寫 engine/，其中 1700 行是 SDK 重造輪子。

### 護城河時間軸
| 護城河類型 | 對手追平所需時間 |
|---|---|
| Workflow 設計（phase 切分、gate 規則） | 1-2 個月 |
| Skill prompt + tool 切分 + 上限規則 | 3-6 個月 |
| 特定專案的 reproduction 知識 + auth flow | 1 年+ |
| 失敗案例 dataset | 持續累積，無法跳過 |
| 內部 issue / PR / GitLab 整合 wiring | 看權限，外部拿不到 |

**「自建 harness」不在這個表上** — 因為業界已經有 3 個成熟 harness，自建的價值已經被產品化收割。

### SDK Signal vs 自建 Signal
在履歷上：
- 「我用了 Claude Agent SDK / Hermes Agent 做出 X 服務」→ **能 collaborate** 的訊號
- 「我自己刻了一個 agent」→ 在 2026 年的市場上是**重造輪子**的訊號

前者讓你能跟 framework 維護者用同一個語言對話，這是更高階的能力。
