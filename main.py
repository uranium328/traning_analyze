"""
AI 虛擬自行車教練 — 主程式

執行流程：
  1. 讀取環境變數，初始化各模組
  2. 以還原的 Garmin token 登入，取得最新活動，過濾已處理的
  3. 對每筆新的騎車活動：清洗 → 呼叫 LLM 分析 → 推播 Discord → 標記已處理

設計為可由 Cron Job / GitHub Actions 每小時定期執行。

需要的環境變數（複製 .env.example 為 .env 並填入）：
  GARMINTOKENS          — 本機 login_setup.py 匯出的 base64 token（CI 用 secret）
  OPENAI_API_KEY        — OpenAI API Key
  DISCORD_WEBHOOK_URL   — Discord Webhook URL

前置條件：
  - 先在本機執行 login_setup.py 取得 GARMINTOKENS（token 效期約一年）
  - pip install -r requirements.txt
  - 本機開發若未設 GARMINTOKENS，會 fallback 到 ~/.garminconnect token 目錄
"""

import os
import sys
import logging

# 優先載入 .env 檔（本機開發用，GitHub Actions 上設 Secrets 即可）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 若未安裝 python-dotenv，依賴系統環境變數

from garmin_client     import GarminClient, create_authenticated_garmin, is_cycling_type
from wellness_client   import WellnessClient
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
    garmin: GarminClient,
    coach: AICoach,
    notifier: DiscordNotifier,
    wellness: WellnessClient,
) -> None:
    """
    處理單筆新活動的完整流程：
    抓取分段 → 清洗 → 抓當日恢復數據 → AI 分析 → Discord 推播 → 標記已處理
    （Garmin 的 activity summary 已含分析所需全部欄位，不需另抓 detail。）
    """
    activity_id   = activity_summary.get("activityId")
    activity_name = activity_summary.get("activityName", "未命名")
    logger.info(f"── 開始處理活動：「{activity_name}」(ID: {activity_id}) ──")

    # 1. 抓取分段（best-effort，失敗回 None 不中斷）
    splits_raw = garmin.fetch_activity_splits(activity_id)

    # 2. 清洗資料（濾掉無用欄位，換算單位，維持中文欄位契約）
    cleaned = garmin.clean_activity_data(activity_summary, splits_raw)
    logger.info(
        f"資料清洗完成：{cleaned['距離_km']} km，"
        f"移動時間 {cleaned['移動時間_min']} 分鐘，"
        f"心率 {cleaned['平均心率_bpm']} bpm"
    )

    # 2.5 抓當日恢復數據（best-effort，任一項失敗不中斷；無資料回 {}）
    start_local   = activity_summary.get("startTimeLocal") or ""
    cdate         = start_local[:10] if len(start_local) >= 10 else None
    wellness_data = wellness.fetch_wellness(cdate) if cdate else {}
    if wellness_data:
        logger.info(f"已取得當日恢復數據 {len(wellness_data)} 項。")

    # 3. 呼叫 LLM 生成訓練分析報告（附恢復數據）
    ai_report = coach.analyze(cleaned, wellness_data)

    # 4. 根據今日數據與分析，生成接下來 4 天訓練計畫（附恢復數據）
    training_plan = coach.generate_training_plan(cleaned, ai_report, wellness_data)

    # 5. 發送 Discord 通知（分析報告 + 訓練計畫 + 恢復摘要）
    notifier.send(
        cleaned_data=cleaned,
        ai_report=ai_report,
        training_plan=training_plan,
        wellness_data=wellness_data,
    )

    # 6. 標記為已處理，避免下次重複分析
    garmin.mark_as_processed(activity_id)
    logger.info(f"活動 {activity_id} 處理完畢。")


def main() -> None:
    logger.info("===== AI 虛擬自行車教練啟動 =====")

    # ── 讀取環境變數 ────────────────────────────────────────────────────────
    openai_api_key      = _require_env("OPENAI_API_KEY")
    discord_webhook_url = _require_env("DISCORD_WEBHOOK_URL")

    # ── 建立 Garmin 連線（token 還原，不用帳密）─────────────────────────────
    try:
        garmin_api = create_authenticated_garmin()
    except Exception as e:
        logger.error(f"Garmin 登入失敗（token 可能已過期或未設定）：{e}")
        logger.error("請在本機重跑 login_setup.py 並更新 GitHub secret GARMINTOKENS。")
        sys.exit(1)

    # ── 初始化各模組 ─────────────────────────────────────────────────────────
    garmin   = GarminClient(garmin_api)
    wellness = WellnessClient(garmin_api)
    coach    = AICoach(openai_api_key)
    notifier = DiscordNotifier(discord_webhook_url)

    # ── 取得尚未分析的新活動 ─────────────────────────────────────────────────
    try:
        new_activities = garmin.fetch_new_activities(limit=10)
    except Exception as e:
        logger.error(f"取得 Garmin 活動列表失敗：{e}")
        sys.exit(1)

    if not new_activities:
        logger.info("沒有新的活動，本次執行結束。")
        return

    # ── 逐筆處理（由舊到新，確保按時間順序分析）──────────────────────────
    # Garmin API 回傳順序為由新到舊，reverse 後從最舊的開始處理
    for activity_summary in reversed(new_activities):
        activity_id   = activity_summary.get("activityId", "未知")
        activity_name = activity_summary.get("activityName", "未命名")
        type_key      = (activity_summary.get("activityType") or {}).get("typeKey")

        # 非騎車活動：寫入 processed_ids.txt 後跳過，避免下次重複出現
        if not is_cycling_type(type_key):
            logger.info(
                f"略過非騎車活動：「{activity_name}」(ID: {activity_id}, 類型: {type_key})，已標記為已處理。"
            )
            garmin.mark_as_processed(activity_id)
            continue

        try:
            process_activity(activity_summary, garmin, coach, notifier, wellness)
        except Exception as e:
            logger.error(f"處理活動 {activity_id} 時發生錯誤，跳過此筆：{e}", exc_info=True)
            # 錯誤時不標記為已處理，讓下次執行時重試
            continue

    logger.info("===== 本次執行完畢 =====")


if __name__ == "__main__":
    main()
