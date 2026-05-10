# 瀏覽器工具使用效率規則

**🔋 Token 節省規則（所有步驟皆適用）**

1. **snapshot vs screenshot 用途區分**：
   - `take_snapshot`：用於**查看 DOM 結構**（取得 selector ref、確認元素存在）。同一頁面狀態只呼叫一次。已有 snapshot 後，後續 click / fill 直接用 snapshot 裡的 ref（如 `uid=N_M`），**【嚴格禁止】每次 click / fill 後立即再次 `take_snapshot`**。
   - `take_screenshot`：用於**視覺確認與存檔**（登入成功確認、重現截圖 reproduction.png、錯誤現象記錄）。**不要用 take_screenshot 做 DOM 查詢**。
   - **只有在頁面內容因操作發生明顯變化時**（導航到新頁、dialog 開啟/關閉、列表刷新）才重新呼叫對應工具。

2. **console 只查 error**：呼叫 `list_console_messages` 時只看 `type=error` 的項目，忽略 warning / log / info。找到 error 後直接記錄，不要遍歷所有訊息。

3. **network 只查失敗 API**：呼叫 `list_network_requests` 時只關注 4xx / 5xx 的請求。`get_network_request` 只在需要看 request / response body 時才呼叫，不要對每個 request 都呼叫一遍。
