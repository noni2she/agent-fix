# 瀏覽器重現程序

#### 0.0 能力前置檢查（在所有瀏覽器操作之前執行）

逐條閱讀 `reproduction_steps`，辨識每個步驟需要的操作能力。對於你不確定是否能執行的操作，掃描**目前 session 中所有可用的工具**（MCP 工具、內建工具、CLI 指令均納入），找有沒有任何工具可以達成相同目的：

- 若找到對應工具 → 記下工具名稱，繼續
- 若找不到 → 將此步驟標記為 ⚠️ high-risk，到達該步驟時若失敗立即觸發 Checkpoint，**不得靜默跳過、不得改走 fallback**

#### 0.1 登入確認（若 Project Context 有 Auth Config）

若 **Project Context** 定義了 `Auth Config`，在任何瀏覽器操作前先確認登入狀態：

1. `list_pages` → 查看目前開啟的 tab 列表
2. `select_page` → 選擇最適合的現有 tab（優先選已在目標 app URL 的 tab，其次選第一個）；**不要呼叫 `new_page`**
3. `navigate_page` → `http://localhost:<port>/`（首頁）
2. `take_screenshot` → 觀察目前頁面
3. 判斷登入狀態：
   - 看到使用者選單 / 頭像 / 個人資訊 → **已登入**，跳到 Step 0.2
   - 看到登入入口（登入按鈕、表單、或被導向登入頁）→ **未登入**，執行下一步
4. 若未登入：
   - 載入 `{Available Skills Directories 第一條}/references/auth-flow.md`
   - 參考 auth-flow skill 的 **Step 1: Email / Phone + Password Login**
   - 登入流程（直接跳轉 URL、modal、multi-step）需自行讀目標專案判斷，不要假設固定路由
   - 使用 Project Context 中 `Auth Config` 的 Username / Password 填寫登入表單
   - ⚠️ 送出後必須等待 post-login 指示元素出現（使用者選單、頭像等），確認頁面跳轉完成後才繼續操作。**不要在送出後立即截圖**，頁面未穩定時會造成長時間等待。

> ⚠️ 若 Project Context 沒有 `Auth Config` 區段，跳過此步驟直接進入 0.2。

#### 0.2 提取驗證依據

從 issue 中提取重現所需資訊：

- `reproduction_steps` — 重現步驟
- `expected` / `actual` — 預期行為 vs 實際行為
- `module` — 問題所在模組
- `comments` — **若 issue 來源是 Jira/Issue Tracker，需檢查 comments**，常包含補充重現條件、環境資訊、reporter 後續發現

#### 0.3 瀏覽器重現（所有問題類型的預設路徑）

**所有 issue 類型（互動類、樣式類、邏輯類）一律先走瀏覽器重現。** 邏輯類雖然根因在程式碼，但通常會在瀏覽器顯示為 console error / network 4xx-5xx / UI 異常，瀏覽器仍是最直接的觀察現場。

> ⚠️ **issue 的附件截圖不等於瀏覽器重現。** 截圖只是 reporter 當下的狀態快照，可能拍到的是正常運作的情況，或是特定條件下才觸發的行為。**必須親自操作，才能看到 network response 的實際內容**（尤其是「功能看起來有做，但回傳結果錯誤」這類場景）。即使 issue 有詳細截圖，Step 0 仍必須執行。

使用 chrome-devtools MCP 工具，依照 `reproduction_steps` 逐步操作：

> ⚠️ **Token 效率原則**：確認頁面狀態時用 `take_snapshot`（accessibility tree，純文字）。`take_screenshot` + `view` 的 base64 截圖 token 消耗極高，**全程只允許呼叫一次 `view`**（步驟 6 的最終截圖）。

1. 確認 dev server 運行中：`curl -s http://localhost:<port> > /dev/null || echo "Dev server not running"`
2. `list_pages` → 查看目前開啟的 tab；`select_page` → 選擇現有 tab（**不要呼叫 `new_page`，全程使用同一個 tab**）
3. `navigate_page` 先導回 **專案首頁**（`http://localhost:<port>/`），確保每個 issue 從同一個乾淨狀態開始（**若 Step 0.1 已登入，此步導航後確認仍保持登入狀態**）
3. 依照 issue 的進入點，`navigate_page` 打開問題頁面
4. 依照 `reproduction_steps` 逐步操作（`click` / `fill` / `press_key` / `navigate_page`）
5. **確認 `actual` 描述的錯誤行為真的出現** → 這是此步驟的核心目標
6. `take_screenshot` 截圖存入截圖目錄下 `reproduction.png`，立即呼叫 `view` 確認截圖內容（**這是全程唯一一次 `view` 呼叫**）
7. `list_console_messages` 找 type=error 的 runtime exception
8. `list_network_requests` 找失敗的 API（4xx / 5xx）
9. 若有必要，`evaluate_script` 驗證 DOM 狀態或 store 值

> ⚠️ **Click 失敗處理**：若同一個 click 連續 2 次未觸發預期結果（dialog 未出現、元素未變更）— 立即停止點擊，用 `evaluate_script` 查明正確觸發方式（hidden input、JS handler），再繼續操作。**不得第 3 次執行相同 click。**

**重現成功的標準**：操作完 `reproduction_steps` 後，觀察到的行為與 `actual` 描述一致（樣式類則為視覺呈現與 `actual` 一致）。

#### 0.3a 重現步驟含媒體播放

當 `reproduction_steps` 包含「播放 / 播放視頻 / play」等操作時：

- **不要嘗試 click 播放按鈕** — 播放器按鈕的 accessible label 不可靠，易誤觸相鄰的返回 / 關閉按鈕
- 改用 `evaluate_script` 直接播放：`document.querySelector('video').play()`
- 確認播放中後再繼續下一個步驟

#### 0.3b 重現需要上傳外部檔案

當 `reproduction_steps` 中包含「上傳影片 / 圖片 / 文件」等操作，且需要實際檔案才能繼續時：

- 載入 `{Available Skills Directories 第一條}/references/upload-flow.md`
- 依 upload-flow skill 的 **Step 0** 判斷所需檔案類型（圖片 / 影片 / 文件）
- 依對應步驟執行上傳並觸發 React synthetic event
- **【嚴格禁止】點擊上傳按鈕後等待 OS 系統檔案對話框** — 系統對話框無法在自動化環境中操作

#### 0.4 重現失敗 fallback（靜態觀察）

當瀏覽器無法重現時——常見原因：未登入 / 權限不足 / 缺少測試資料 / 環境異常 / 頁面跳轉錯誤——執行以下記錄後退回靜態觀察：

1. `take_screenshot` 截圖當前失敗狀態，存入 task prompt 指定的截圖目錄下 `reproduction-failed.png`（**只截這一張**）
2. `list_console_messages` 記錄所有 type=error 的訊息
3. `list_network_requests` 記錄失敗的 API（4xx / 5xx）
4. 將觀察到的阻礙（如「未登入導致 401」、「跳轉到 /login」、「缺少 mock 資料」）記入 `Browser Reproduction Issues`
5. 進入 Step 1 RCA，繼續完整分析——**最終 status 由靜態分析品質決定，不是由重現結果決定**

> 純邏輯問題（無 UI 出口、僅在 unit test 才能觀察）也走此路徑：記錄「無法在瀏覽器觀察」後進入 Step 1。

#### 0.5 根據結果決定後續動作

| 結果 | 後續動作 | Status |
|------|---------|--------|
| **重現成功** | 繼續 Step 1–4 完整分析 | `confirmed`（最終由分析品質決定） |
| **問題已被修正**（操作後 actual 行為消失，符合 expected） | 輸出 `already_fixed` 報告，**停止分析** | `already_fixed` |
| **重現失敗，靜態分析找到明確根因**（confidence > 0.6） | 記錄阻礙 → 繼續 Steps 1–4 → 可輸出 `confirmed` | `confirmed`（於 `Browser Reproduction Issues` 說明無法重現原因） |
| **重現失敗，靜態分析仍無法確定根因**（confidence ≤ 0.6） | 記錄所有已知線索 | `need_more_info` |

**已修正時的報告格式：**

```
### 分析報告

- **Status**: already_fixed
- **Root Cause File**: <修正所在檔案>
- **Root Cause Line**: <修正所在行號>
- **Fix Description**: <說明哪段程式碼已處理此問題>
- **Confidence Score**: <0-1>
```
