# Step 0 瀏覽器重現程序

**職責**：透過瀏覽器親自操作出 `actual` 描述的錯誤現象。重現成功後截圖存檔，才進入 RCA。

---

## Step 0.1：確認登入狀態

```
1. navigate_page → Dev server URL（如 http://localhost:3001）
2. take_screenshot → 確認是否已登入
   - 若已登入（看到主頁/用戶資訊）→ 直接跳到 Step 0.3
   - 若未登入 → Step 0.2
```

## Step 0.2：執行登入（需要時）

參考 `auth-flow` skill 或 Project Context 的 Auth Config 執行登入：

```
常見流程（依 auth config）：
1. click → login trigger button（如 "button.bg-green-500"）
2. click → 登入方式選擇（如 "text=使用手机号继续"）
3. pre_fill_actions（如國家選擇）
4. fill → username_selector + 帳號
5. fill → password_selector + 密碼
6. click → submit_selector
7. take_screenshot → 確認登入成功
```

## Step 0.3：導航到問題頁面

```
1. navigate_page → 問題發生的 URL
2. take_screenshot → 確認頁面載入（用 take_snapshot 只在需要查看 DOM 元素時）
3. 若頁面需要等待 → wait_for selector/timeout
```

## Step 0.4：重現操作步驟

依照 Issue 的 `reproduction_steps` 逐步操作：

```
- 用 click / fill / press_key 執行操作
- 每個「關鍵狀態變化」後 take_screenshot（不需要每步都截）
- 關鍵狀態：dialog 開啟/關閉、錯誤訊息出現、頁面導航
- 觀察 console errors：list_console_messages（只看 type=error）
- 觀察 API 失敗：list_network_requests（只看 4xx/5xx）
```

## Step 0.5：截圖存檔

```
重現成功（看到 actual 描述的錯誤）：
  → take_screenshot → 存為 <screenshot_dir>/reproduction.png

重現失敗（操作完畢但看不到錯誤）：
  → take_screenshot → 存為 <screenshot_dir>/reproduction-failed.png
  → 在報告的 Browser Reproduction Issues 欄位記錄失敗原因
  → 繼續進行靜態分析（不要因重現失敗而放棄 RCA）
```

---

## 注意事項

- **Step 0 只觀察現象**，不在此階段做程式碼追蹤或根因推理
- **screenshot_dir** 由 task prompt 提供（絕對路徑）
- 若頁面有 loading state，用 `wait_for` 等待內容出現再截圖
- 若遇到 overlay/modal 擋住操作，先 dismiss 或等待消失
- console errors 和 network 4xx 是佐證材料，記錄在報告中
