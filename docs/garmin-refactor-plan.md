# Garmin 重構計畫書

> 2026-07-03 由使用者口頭認可方向。背景：Strava API 不再支援免費用戶，
> 改接 Garmin Connect，並順勢納入健康數據（睡眠/HRV/Body Battery 等）。
> 執行本計畫前先讀 CLAUDE.md 紅線與 .claude/rules/dispatch.md。
> 標註【查證】的段落：實作時先用研究模板確認最新 API，不要直接信本文件
> ——garminconnect 是非官方套件，介面會變。

## 技術選型（已定案，不要重新評估）

- 套件：`garminconnect`（PyPI，底層 `garth` 負責登入與 token）。
- 理由：Garmin 官方 API 只給企業；此套件是社群事實標準、可拿到健康數據。
- 已知風險：非官方、Garmin 改版可能短暫失效。壞掉時的處置見文末。

## 模組對照

| 現有 | 重構後 | 動作 |
|---|---|---|
| `auth_manager.py` + `get_data.py` | `login_setup.py`（一次性登入+匯出 token） | 取代後刪除舊檔 |
| `strava_client.py` | `garmin_client.py` | 取代後刪除舊檔 |
| （無） | `wellness_client.py` | 新增 |
| `ai_coach.py` | 保留，prompt 擴充健康上下文 | 修改 |
| `discord_notifier.py` | 保留，加健康摘要區塊 | 小改 |
| `main.py` | 環境變數與流程對接 | 修改 |
| `processed_ids.txt` 機制 | 沿用（Garmin activityId 一樣唯一） | 不動 |

## 認證設計（與 Strava 差異最大處，先做這裡）

1. `login_setup.py`：本機互動執行一次。用 Garmin 帳密（支援 MFA）登入，
   garth 把 OAuth token 存到本機目錄；再以 `garth.Client.dumps()`（或
   garminconnect 的 `garmin.garth.dumps()`）序列化成 base64 字串印出，
   供使用者存進 GitHub secret `GARMINTOKENS`。【查證：dumps/loads 的
   最新呼叫方式】
2. 執行期（`garmin_client.py`）：優先從環境變數 `GARMINTOKENS` 還原登入；
   本機開發 fallback 到 token 目錄。**不在任何自動化環境用帳密登入**
   （雲端 IP 會觸發 Garmin 風控），帳密只存在於本機一次性設定。
3. token 效期約一年。過期的表徵是 401/需要重新登入 → 程式印出明確訊息
   「請重跑 login_setup.py 並更新 GARMINTOKENS secret」後退出，不要自動重試。

## 資料抓取與欄位對應

- 活動列表：`garmin.get_activities(0, 10)`；騎車過濾用
  `activityType.typeKey ∈ {cycling, road_biking, virtual_ride, indoor_cycling,
  mountain_biking, gravel_cycling}`【查證：typeKey 完整清單】。
- 清洗後的中文欄位名**維持與現版相同**（`距離_km`、`平均心率_bpm`⋯），
  這樣 ai_coach 與 discord_notifier 幾乎不用改。對應：

| 清洗後欄位 | Garmin 來源欄位 | 換算 |
|---|---|---|
| 距離_km | `distance`（公尺） | /1000 |
| 移動時間_min | `movingDuration`（秒） | /60 |
| 總經過時間_min | `duration`（秒） | /60 |
| 平均/最大心率_bpm | `averageHR` / `maxHR` | — |
| 平均/最大功率_W | `avgPower` / `maxPower` | — |
| 標準化功率_NP_W | `normPower` | — |
| 平均踏頻_rpm | `averageBikingCadenceInRevPerMinute` | — |
| 總爬升_m | `elevationGain` | — |
| （取代 Suffer_Score）訓練負荷 | `activityTrainingLoad` | — |
| （新增）有氧/無氧訓練效果 | `aerobicTrainingEffect` / `anaerobicTrainingEffect` | — |

- 分段：`get_activity_splits(activity_id)`【查證：回傳結構】。
- 所有欄位用 `.get()` 取值容忍缺漏（室內騎乘常缺功率/GPS 欄位）。

## 健康數據（wellness_client.py）

抓「活動當天」的：`get_sleep_data`（睡眠時數與分期）、`get_hrv_data`（HRV
狀態）、`get_body_battery`、`get_stress_data`、`get_training_readiness`、
`get_training_status`。【查證：各方法名與日期參數格式】
清洗成一個扁平 dict（中文鍵名，同活動資料風格），缺哪項就填 None，
**任何一項抓失敗都不得中斷活動分析主流程**（log warning 後繼續）。

## AI 教練修改

- `analyze()`：user message 附上健康 dict，system prompt 加一段「結合學員
  當日恢復狀態（睡眠、HRV、Body Battery）評估這次訓練是否恰當」。
- `generate_training_plan()`：輸入加 Training Status/Readiness，規則：
  readiness 低或 status 為 Overreaching 時，Day +1 必須是休息或 Z1。
- 教練人設 prompt（UAE 車隊總監）**不要動**——那是使用者調過的品味產物。

## CI（coach.yml）修改

- Secrets：移除 `STRAVA_CLIENT_ID`、`STRAVA_CLIENT_SECRET`、`TOKENS_JSON`；
  新增 `GARMINTOKENS`。`OPENAI_API_KEY`、`DISCORD_WEBHOOK_URL` 不變。
- 拔掉「Update TOKENS_JSON secret」步驟與 `GH_PAT` 依賴（token 一年效期，
  不需要每小時回寫）。完成後提醒使用者可撤銷 GH_PAT。
- `processed_ids.txt` commit 步驟沿用。

## 實作順序（每步含驗收，逐步派工）

1. **smoke test 先行**：`tests/test_clean.py`——假 Garmin activity dict 進
   清洗函式，斷言中文欄位與換算。驗收：`python -m pytest tests/` 綠。
   （requirements 加 pytest，僅開發用）
2. `login_setup.py` + `garmin_client.py` 認證與活動抓取。驗收：本機真登入
   成功列出最近 10 筆活動（需要使用者在場提供帳密，這步排在使用者有空時）。
3. 清洗函式 + 對接 `main.py`（環境變數改 `GARMINTOKENS`）。驗收：smoke test
   綠 + 假資料 end-to-end 跑到 Discord 發送前一步（mock notifier）。
4. `wellness_client.py` + ai_coach prompt 擴充。驗收：健康 dict 出現在
   prompt；單項抓取失敗不中斷主流程（以假異常驗證）。
5. coach.yml 與 `.env.example`、README 更新；刪除 strava_client.py、
   auth_manager.py、get_data.py。驗收：repo 內 grep 不到 "strava"
   （README 的歷史說明除外）。

## garminconnect 壞掉時的處置（給未來 session）

症狀通常是登入 4xx 或方法丟例外。處置順序：(1) 查該套件 GitHub issues 是否
已知問題；(2) `pip install -U garminconnect garth` 升級重試一次；(3) 已知
問題未修 → 鎖版本等待，並發 Discord/總結告知使用者暫停原因。不要嘗試自己
逆向 Garmin API 端點。
