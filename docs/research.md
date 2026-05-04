# Research Notes — LLM Agent 步驟遵從性

> 本文件記錄設計 agent-fix 架構過程中，針對「LLM 為何不遵從規範步驟」所做的理論探討與社群研究，以及對應的設計決策依據。

---

## 核心問題

在 bugfix-analyze 階段，Analyzer subagent 需要完成兩個性質不同的任務：

1. **重現問題**（Step 0）：操作瀏覽器、觀察行為、記錄證據——純粹的**實證觀察**模式
2. **分析根因**（Steps 1–4）：閱讀程式碼、推理歸因、輸出報告——**推理歸納**模式

在同一個 context 裡，LLM 讀完完整的 SKILL.md 後就知道最終目標是輸出 `analyze.md`（含 `root_cause_file`、`confidence`、`suggested_fix`）。這個終點目標會對中間步驟產生**向後壓力（backward pressure）**——LLM 傾向優化走向終點，而非嚴格遵守中途每個步驟的要求。

實際觀察到的失敗模式：
- AI 先讀程式碼再做瀏覽器重現（顛倒順序）
- 重現遇到障礙（如需要上傳檔案）時，合理化跳過，直接走靜態分析
- 從 issue 附件截圖「看到」預期中的欄位名稱，而非實際觀察到的值（confirmation bias）

---

## 社群對應概念

### Context Rot（注意力稀釋）

社群主流討論的命名是 **Progressive Disclosure（漸進式揭露）**，主要動機有兩個：

1. **Token 節省**：只在需要時載入相關 context
2. **Context Rot / 注意力稀釋**：context 太大，LLM 會忽略其中的關鍵細節

第二點與我們的場景高度吻合：

> Analyze 階段同時包含「重現步驟」和「分析步驟」，LLM 的注意力在趨向最終輸出（analyze.md）的過程中，會稀釋對重現細節的關注，導致碰到重現障礙就傾向跳過，因為跳過不妨礙它走向終點目標。

這不只是 context 太大的問題，而是**不同認知模式的目標互相干擾**。

**參考資料**：
- [Progressive Disclosure: the technique that helps control context and tokens in AI agents](https://medium.com/@martia_es/progressive-disclosure-the-technique-that-helps-control-context-and-tokens-in-ai-agents-8d6108b09289)
- [Optimizing AI Agents with Progressive Disclosure](https://ardalis.com/optimizing-ai-agents-with-progressive-disclosure/)

### Goal Drift（目標漂移）

學術研究確認了這個底層行為問題：

- **[Evaluating Goal Drift in Language Model Agents](https://arxiv.org/html/2505.02709v1)**：模型在暴露於衝突指令時，會偏離 system-level 目標
- **[Many-Tier Instruction Hierarchy in LLM Agents](https://arxiv.org/html/2604.09443v3)**：frontier model 在 12 層指令衝突場景下失敗率高達 60%
- **[How Do LLMs Fail In Agentic Scenarios?](https://arxiv.org/pdf/2512.07497)**：記錄了 constraint handling 和 multi-step reasoning 的系統性失敗模式

---

## 設計回應：Progressive Disclosure in Orchestrator

我們稱之為 **Gated Context Reveal**，本質上是 Progressive Disclosure 在 Orchestrator-Worker 架構中的具體實作形式。

### 機制

Orchestrator 不一次送出完整 SKILL.md，而是分段揭露：

```
Turn 1：只送 Step 0.0（能力前置檢查）指令
         → LLM 輸出能力前置表
         → Orchestrator 驗證格式

Turn 2：只送 Step 0.1–0.4（瀏覽器重現）指令
         → LLM 此時看不到 Steps 1–4，唯一目標是「觀察並記錄」
         → Orchestrator 驗證：截圖存在？network log 存在？
         → 驗證不通過 → retry 僅此 turn，不重跑 Turn 1

Turn 3：才送 Steps 1–4（RCA）指令
         → LLM 以前兩輪的真實觀察為基礎做推理
```

### 關鍵性質

- **移除 backward pressure**：LLM 在 Turn 2 執行重現時，看不到 Steps 1–4，無終點目標可以合理化跳過
- **Step-level retry**：Orchestrator 在步驟邊界驗證，失敗只 retry 當前 turn，不重跑整個 phase
- **Retry 有效性**：重跑 Turn 2 時 LLM 仍然沒有終點目標，修正原因而非重複同樣的合理化

### Token 成本分析

Gated Reveal **不節省** Analyze 階段的 token（對話歷史跨輪累積，總量相近）。
真正的 token 帳要算整條 pipeline：

| 場景 | Token 成本 |
|------|-----------|
| 原始方式 + analyze 品質差 → implement 錯誤 → test FAIL → retry | 最高（下游全浪費）|
| Gated Reveal + analyze 品質穩定 → implement 準確 → test PASS | Analyze 略貴，下游浪費大幅減少 |

### 和原始「Orchestrator 驗證 analyze.md」的差異

原始方式 Orchestrator 在 analyze.md 產出後也會驗證，但：
- 驗證失敗 → retry 整個 analyze phase
- Retry 後 LLM 面對同樣完整 context 和終點目標 → 同樣理由跳過重現的機率依然存在

Gated Reveal 的 retry 有效是因為**結構性地移除了 goal contamination**，不只是重跑一次希望結果不同。

---

## 框架參考

**LangGraph**（LangChain）是目前最接近實作此概念的框架：
- State graph + checkpoint 機制
- 每個 node 只看到對它定義的 state
- 執行完才把結果寫入 state 供下一個 node 使用

與 agent-fix 的差異：LangGraph 的 context 隔離是 state-based（node 看到什麼 state 欄位），agent-fix 的設計是 instruction-based（Orchestrator 控制送什麼指令）。兩者精神一致，實作路徑不同。

---

## 適用範圍

Gated Context Reveal 在 Analyze 階段最為關鍵（兩種認知模式衝突最大）。
Implement 和 Test 也可能受益，但優先順序次之：

| Phase | 主要認知模式衝突 | 優先程度 |
|-------|----------------|---------|
| Analyze | 實證觀察 vs. 推理歸因 | 🔴 高 |
| Implement | 閱讀 analyze.md vs. 寫程式 | 🟡 中 |
| Test | 執行驗證 vs. 宣告結果 | 🟡 中 |

---

*最後更新：2026-05-04*
*來源：agent-fix 架構設計討論 + 社群研究*
