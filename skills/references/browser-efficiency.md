# 瀏覽器工具使用效率規則

**🔋 Token 節省規則（所有步驟皆適用）**

1. **snapshot 去重**：同一頁面狀態只 `take_snapshot` 一次。已有 snapshot 後，後續操作（click / fill）直接用 snapshot 裡的 ref（如 `uid=N_M`），**【嚴格禁止】每次 click / fill 後立即再次 `take_snapshot`**。**只有在頁面內容因操作而發生明顯變化時**（如導航到新頁、dialog 開啟/關閉、列表刷新）才執行新的 `take_snapshot`。

2. **console 只查 error**：呼叫 `list_console_messages` 時只看 `type=error` 的項目，忽略 warning / log / info。找到 error 後直接記錄，不要遍歷所有訊息。

3. **network 只查失敗 API**：呼叫 `list_network_requests` 時只關注 4xx / 5xx 的請求。`get_network_request` 只在需要看 request / response body 時才呼叫，不要對每個 request 都呼叫一遍。
