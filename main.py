"""
AI 虛擬自行車教練 — 主程式

執行流程：
  1. 讀取環境變數，初始化各模組
  2. 向 Strava 取得最新活動，過濾已處理的
  3. 對每筆新活動：抓取詳情 → 清洗 → 呼叫 Claude 分析 → 推播 Discord → 標記已處理

設計為可由 Cron Job / GitHub Actions 每小時定期執行。

需要的環境變數（複製 .env.example 為 .env 並填入）：
  STRAVA_CLIENT_ID      — Strava 應用程式 Client ID
  STRAVA_CLIENT_SECRET  — Strava 應用程式 Client Secret
  OPENAI_API_KEY        — OpenAI API Key
  DISCORD_WEBHOOK_URL   — Discord Webhook URL

前置條件：
  - 先執行 get_data.py 取得初始 Token，產生 tokens.json
  - pip install requests anthropic python-dotenv
"""

import os
import sys
import logging
from typing import Optional

# 優先載入 .env 檔（本機開發用，GitHub Actions 上設 Secrets 即可）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 若未安裝 python-dotenv，依賴系統環境變數

from auth_manager      import AuthManager
from strava_client     import StravaClient
from ai_coach          import AICoach
from discord_notifier  import DiscordNotifier

# ── 日誌設定 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ── 環境變數讀取 ─────────────────────────────────────────────────────────────

def _require_env(key: str) -> str:
    """讀取必要環境變數；缺少時終止程式並提示使用者。"""
    value = os.environ.get(key, "").strip()
    if not value:
        logger.error(f"缺少必要環境變數：{key}。請確認 .env 或系統環境變數已正確設定。")
        sys.exit(1)
    return value


# ── 核心流程 ─────────────────────────────────────────────────────────────────

def process_activity(
    activity_summary: dict,
    strava: StravaClient,
    coach: AICoach,
    notifier: DiscordNotifier,
) -> None:
    """
    處理單筆新活動的完整流程：
    抓取詳情 → 清洗 → AI 分析 → Discord 推播 → 標記已處理
    """
    activity_id   = activity_summary["id"]
    activity_name = activity_summary.get("name", "未命名")
    logger.info(f"── 開始處理活動：「{activity_name}」(ID: {activity_id}) ──")

    # 1. 抓取完整詳情
    raw_detail = strava.fetch_activity_detail(activity_id)

    # 2. 清洗資料（濾掉地圖軌跡、裝備等無用欄位）
    cleaned = strava.clean_activity_data(raw_detail)
    logger.info(
        f"資料清洗完成：{cleaned['距離_km']} km，"
        f"移動時間 {cleaned['移動時間_min']} 分鐘，"
        f"心率 {cleaned['平均心率_bpm']} bpm"
    )

    # 3. 呼叫 Claude 生成訓練分析報告
    ai_report = coach.analyze(cleaned)

    # 4. 發送 Discord 通知
    notifier.send(cleaned_data=cleaned, ai_report=ai_report)

    # 5. 標記為已處理，避免下次重複分析
    strava.mark_as_processed(activity_id)
    logger.info(f"活動 {activity_id} 處理完畢。")


def main() -> None:
    logger.info("===== AI 虛擬自行車教練啟動 =====")

    # ── 讀取環境變數 ────────────────────────────────────────────────────────
    strava_client_id     = _require_env("STRAVA_CLIENT_ID")
    strava_client_secret = _require_env("STRAVA_CLIENT_SECRET")
    openai_api_key       = _require_env("OPENAI_API_KEY")
    discord_webhook_url  = _require_env("DISCORD_WEBHOOK_URL")

    # ── 初始化各模組 ─────────────────────────────────────────────────────────
    try:
        auth     = AuthManager(strava_client_id, strava_client_secret)
        strava   = StravaClient(auth)
        coach    = AICoach(openai_api_key)
        notifier = DiscordNotifier(discord_webhook_url)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    # ── 取得尚未分析的新活動 ─────────────────────────────────────────────────
    try:
        new_activities = strava.fetch_new_activities(per_page=10)
    except Exception as e:
        logger.error(f"取得 Strava 活動列表失敗：{e}")
        sys.exit(1)

    if not new_activities:
        logger.info("沒有新的活動，本次執行結束。")
        return

    # ── 逐筆處理（由舊到新，確保按時間順序分析）──────────────────────────
    # Strava API 回傳順序為由新到舊，reverse 後從最舊的開始處理
    for activity_summary in reversed(new_activities):
        try:
            process_activity(activity_summary, strava, coach, notifier)
        except Exception as e:
            activity_id = activity_summary.get("id", "未知")
            logger.error(f"處理活動 {activity_id} 時發生錯誤，跳過此筆：{e}", exc_info=True)
            # 不標記為已處理，讓下次執行時重試
            continue

    logger.info("===== 本次執行完畢 =====")


if __name__ == "__main__":
    main()
