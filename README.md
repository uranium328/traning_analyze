# AI Cycling Coach

自動化自行車訓練分析系統。透過 GitHub Actions 每小時定期檢查 Garmin Connect 是否有新的騎乘紀錄，若有則抓取活動與當日恢復數據（睡眠、HRV、Body Battery、壓力、訓練準備度／狀態），呼叫 GPT-4o 生成訓練分析報告與後續訓練計畫，並以 Discord Webhook 推播通知。

> 註：本專案原以 Strava 為資料源，2026-07 起改接 Garmin Connect（Strava 已不再支援免費 API 用戶），並順勢納入健康／恢復數據。

## 系統架構

```
main.py                  主流程編排
garmin_client.py         Garmin 活動抓取與清洗（含 token 還原登入）
wellness_client.py       Garmin 健康／恢復數據抓取與清洗
login_setup.py           一次性本機登入，匯出 Garmin token（只需執行一次）
ai_coach.py              GPT-4o 訓練分析與計畫生成
discord_notifier.py      Discord Webhook 推播
```

執行流程：

1. 以還原的 Garmin token 登入，取得最新活動列表
2. 比對 `processed_ids.txt`，過濾已分析的活動
3. 非騎車類型（跑步、游泳等）直接標記為已處理並跳過
4. 對每筆新騎乘活動：清洗數據 → 抓當日恢復數據 → GPT-4o 分析 → 生成後續訓練計畫 → 推播 Discord
5. 將已處理的 activity ID 寫入 `processed_ids.txt`

## 環境需求

- Python 3.12+（`garminconnect` 0.3.6 要求 >= 3.12）
- 套件：`requests`, `openai`, `python-dotenv`, `garminconnect`（`pytest` 僅開發用）

```bash
pip install -r requirements.txt
```

## 首次設定（本機）

**1. 取得 Garmin token**

在本機執行一次（需要你的 Garmin 帳號 email 與密碼，支援 MFA）：

```bash
python login_setup.py
```

登入成功後會印出一串 base64 token。這串等同你的 Garmin 登入憑證，**切勿外流或 commit**。token 效期約一年，過期時主程式會提示再重跑本步驟。

**2. 設定環境變數**

複製 `.env.example` 為 `.env` 並填入：

```
GARMINTOKENS=上一步印出的_base64_token
OPENAI_API_KEY=your_openai_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

**3. 執行**

```bash
python main.py
```

（本機若未設 `GARMINTOKENS`，會 fallback 嘗試讀取 `~/.garminconnect` token 目錄。）

## 測試

```bash
python -m pytest tests/
```

以假資料驗證清洗函式、恢復數據容錯與主流程串接，不需真實帳號或網路。

## GitHub Actions 自動化部署

Workflow 設定於 `.github/workflows/coach.yml`，每小時整點自動執行。

**需要在 Repository Secrets 設定以下三個值：**

| Secret | 說明 |
|---|---|
| `GARMINTOKENS` | `login_setup.py` 匯出的 base64 token（效期約一年） |
| `OPENAI_API_KEY` | OpenAI API Key |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |

**上傳 token：**

```bash
python login_setup.py            # 本機執行，複製印出的 base64 字串
gh secret set GARMINTOKENS       # 貼上並 Enter（或用 --body 傳入）
```

**狀態持久化機制：**

- Garmin token 效期約一年，執行期不需回寫；過期再重跑 `login_setup.py` 更新 secret 即可（不再需要 `GH_PAT`）。
- `processed_ids.txt`：每次執行結束後自動 commit 回 repo。

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `~/.garminconnect/` | 本機 Garmin token 目錄（不進 git；CI 用 `GARMINTOKENS` secret 取代） |
| `processed_ids.txt` | 已分析的 Garmin activity ID 清單（進 git） |
| `.env` | 本機環境變數（不進 git） |
| `.env.example` | 環境變數範本 |

## Discord 通知格式

每次分析完成後推播數個 Embed：

1. **訓練分析報告**：包含活動摘要數據（距離、時間、心率、功率、訓練負荷、訓練效果等）與 GPT-4o 生成的三段式分析（訓練性質、代謝功率解析、恢復戰略）
2. **當日恢復狀態**（若當日有 Garmin 健康數據）：睡眠、HRV、Body Battery、壓力、訓練準備度等摘要
3. **後續訓練計畫**：根據本次訓練負荷與恢復狀態，生成接下來 4 天的訓練安排
