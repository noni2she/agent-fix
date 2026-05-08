# UX 方案評估

**執行步驟：**

1. 列舉 ≥ 2 種候選修復方案（functional 上都能解決 bug）
2. 依問題類型，用 `search_files` grep `../assets/ux-guidelines.csv` 篩選相關規則
   （資料來源：[UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)，MIT License）：

   | 問題類型 | grep Category |
   |---------|--------------|
   | layout / scroll / modal / overflow | `Layout` |
   | 按鈕 / 狀態回饋 / 點擊互動 | `Interaction` |
   | 手機觸控 / touch target | `Touch` |
   | 表單 / input / 驗證 | `Forms` |
   | 無障礙 / 對比度 / ARIA | `Accessibility` |
   | 動畫 / transition | `Animation` |
   | 導航 / 路由 | `Navigation` |

3. 對每個候選方案，對照 Do / Don't / Severity 欄位評分
4. 選擇最符合 UX 規則的方案作為最終 `Suggested Fix`
5. 在報告中記錄 `Needs Design Phase`、`Candidate Solutions` 與選擇理由

> **注意**：`Needs Design Phase: true` 是為 Orchestrator-Worker 架構預留的 flag。
> 屆時此步驟將拆出為獨立 Designer subagent，UX 評估邏輯不變，只是執行角色分離。
