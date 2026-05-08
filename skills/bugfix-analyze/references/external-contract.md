# 外部契約檢查（External Contract Discipline）

當你準備建議的修復方向涉及「改變程式碼解讀外部 API response / 第三方資料 / 後端事件的方式」時，先執行此步驟。

**觸發條件**（符合任一即執行）：
- 修復會改變讀取的 response 欄位名稱
- 修復會修改判斷「成功 / 失敗 / 異常」的條件
- 修復假設外部回傳的格式、列舉值或順序
- **issue 描述「功能 X 應該攔截 / 阻擋 Y，但沒有攔截」** → 必須先確認現有的攔截邏輯是否真的執行，以及其回傳的實際結果，再決定是「前端缺檢查」還是「API 行為錯誤」

> **「缺少前端檢查」與「API 回傳錯誤」的診斷差異**：
> - 若 network tab 顯示 API **從未被呼叫** → 確實是前端缺少觸發
> - 若 network tab 顯示 API **已被呼叫但回傳不符預期結果** → bug 在 API，不在前端，不應新增冗餘的前端檢查來「繞過」問題
> - **沒有瀏覽器重現，無法區分這兩種情況 → 必須先跑 Step 0**

## 驗證契約

依序嘗試，找到任一佐證即可繼續：

| 驗證方式 | 通過條件 |
|---------|---------|
| API 文件 | Project Context / repo 內找到對應 API 文件，欄位定義與修復方向一致 |
| 瀏覽器實測 | 本次 Step 0 中親自觀察到的 network tab response，確認欄位真實樣貌。⚠️ **Issue 附件截圖不算**「瀏覽器實測」—— reporter 的截圖不等於你親自取得的 network response |
| 直接呼叫 API | 瀏覽器重現失敗時的替代方案：用 `evaluate_script` 執行 `fetch` 或用 bash `curl` 直接呼叫對應 endpoint，取得真實 response body。佐證等級等同「瀏覽器實測」 |
| 同一 API 的其他呼叫端 | codebase 內其他地方對同一 API 的用法可作為間接佐證 |

**三個都無法驗證 → 不可修改契約相關程式碼 → Confidence Score 強制扣 0.40，輸出 `need_more_info`**

## 「程式碼看起來是對的」也是有效結論

若靜態分析顯示前端程式碼邏輯與契約一致，但 issue 描述顯示功能仍失常：

- **不要為了「找到能改的地方」而幻覺式修改**（例如：改欄位名、加防禦性條件）
- 結論應為：bug 不在前端，可能在 API / 後端 / 資料來源
- 輸出 `need_more_info`，並在 `Browser Reproduction Issues` 欄位標註：
  ```
  Frontend code aligns with observed/documented API contract.
  Symptom suggests issue may be in: <API endpoint / backend service>
  Recommend investigating: <具體建議，如「check why /api/profanity-check returns is_profane=false for known profane input」>
  ```
