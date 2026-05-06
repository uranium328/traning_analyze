# AI Cycling Coach

自動化自行車訓練分析系統。透過 GitHub Actions 每小時定期檢查 Strava 是否有新的騎乘紀錄，若有則抓取數據、呼叫 GPT-4o 生成訓練分析報告與後續訓練計畫，並以 Discord Webhook 推播通知。

## 系統架構

```
main.py                  主流程編排
auth_manager.py          Strava OAuth Token 管理（自動刷新）
strava_client.py         活動數據抓取與清洗
ai_coach.py              GPT-4o 訓練分析與計畫生成
discord_notifier.py      Discord Webhook 推播
get_data.py              首次授權腳本（只需執行一次）
```

執行流程：

1. 向 Strava 取得最新活動列表
2. 比對 `processed_ids.txt`，過濾已分析的活動
3. 非騎車類型（跑步、游泳等）直接標記為已處理並跳過
4. 對每筆新騎乘活動：抓取詳情 → 清洗數據 → GPT-4o 分析 → 生成後續訓練計畫 → 推播 Discord
5. 將已處理的 activity ID 寫入 `processed_ids.txt`

## 環境需求

- Python 3.11+
- 套件：`requests`, `openai`, `python-dotenv`

```bash
pip install -r requirements.txt
```

## 首次設定（本機）

**1. 取得 Strava API 憑證**

前往 [strava.com/settings/api](https://www.strava.com/settings/api) 建立應用程式，取得 Client ID 與 Client Secret。

**2. 設定環境變數**

複製 `.env.example` 為 `.env` 並填入：

```
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
OPENAI_API_KEY=your_openai_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

**3. 取得初始 Strava Token**

用瀏覽器打開以下 URL（替換 `YOUR_CLIENT_ID`），在 Strava 授權後從跳轉網址取得 `code` 參數：

```
https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost&response_type=code&scope=activity:read_all
```

將取得的 code 設為環境變數 `STRAVA_AUTHORIZATION_CODE`，然後執行：

```bash
python get_data.py
```

成功後會產生 `tokens.json`，之後由 `AuthManager` 自動管理 Token 刷新。

**4. 執行**

```bash
python main.py
```

## GitHub Actions 自動化部署

Workflow 設定於 `.github/workflows/coach.yml`，每小時整點自動執行。

**需要在 Repository Secrets 設定以下六個值：**

| Secret | 說明 |
|---|---|
| `STRAVA_CLIENT_ID` | Strava 應用程式 Client ID |
| `STRAVA_CLIENT_SECRET` | Strava 應用程式 Client Secret |
| `OPENAI_API_KEY` | OpenAI API Key |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |
| `TOKENS_JSON` | `tokens.json` 的完整 JSON 內容 |
| `GH_PAT` | Personal Access Token（Classic，需 `repo` scope，可設 No expiration） |

**上傳初始 Token：**

```bash
gh secret set TOKENS_JSON < tokens.json
```

**狀態持久化機制：**

- `tokens.json`：每次執行結束後，若 Token 有刷新，workflow 會自動更新 `TOKENS_JSON` secret
- `processed_ids.txt`：每次執行結束後自動 commit 回 repo

## 檔案說明

| 檔案 | 說明 |
|---|---|
| `tokens.json` | Strava OAuth Token（不進 git，透過 Secret 管理） |
| `processed_ids.txt` | 已分析的 Strava activity ID 清單（進 git） |
| `.env` | 本機環境變數（不進 git） |
| `.env.example` | 環境變數範本 |

## Discord 通知格式

每次分析完成後推播兩個 Embed：

1. **訓練分析報告**：包含活動摘要數據（距離、時間、心率、功率等）與 GPT-4o 生成的三段式分析（訓練性質、代謝功率解析、恢復戰略）
2. **後續訓練計畫**：根據本次訓練負荷，生成接下來 4 天的訓練安排
