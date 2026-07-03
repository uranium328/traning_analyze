"""
GarminClient — Garmin Connect 活動數據抓取與清洗

負責：
- 用還原的 OAuth token 建立已登入的 Garmin 連線（自動化環境不用帳密）
- 取得最新活動列表，比對 processed_ids.txt 過濾已分析的活動
- 將 Garmin 活動 summary 清洗為只含分析所需欄位的精簡結構（中文欄位名沿用舊版，
  讓 ai_coach / discord_notifier 幾乎不用改）
- 分段（splits）為 best-effort 增補，失敗不中斷主流程

備註（2026-07 資料源重構：改接 Garmin Connect）：
- 認證改用 garminconnect 0.3.6：garth 已 deprecated，改自研 auth engine；
  Garmin 物件無 .garth，token 序列化走 garmin.client.dumps()（見 login_setup.py）。
- get_activities() 的 summary 就含全部所需欄位，不需再呼叫 get_activity() detail。
- 以下三處在重構規劃階段查無官方出處，採防禦性寫法，待本機真登入後校正：
  騎乘踏頻欄位名、細分騎車 typeKey 完整清單、get_activity_splits() 回傳結構。
"""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROCESSED_IDS_FILE = Path("processed_ids.txt")

# 騎車 typeKey：以下為已知/常見值；官方完整清單未查證（屬性檔被 Cloudflare 擋），
# 故除白名單外再加寬鬆子字串比對容錯。真登入後可用 get_activity_types() 校正常數。
CYCLING_TYPE_KEYS = {
    "cycling", "road_biking", "mountain_biking", "gravel_cycling",
    "indoor_cycling", "virtual_ride", "cyclocross", "track_cycling",
    "recumbent_cycling", "e_bike_fitness", "e_bike_mountain",
}


def is_cycling_type(type_key: Optional[str]) -> bool:
    """判斷活動 typeKey 是否為騎車類。白名單 + 寬鬆子字串比對容錯。"""
    if not type_key:
        return False
    tk = str(type_key).lower()
    return tk in CYCLING_TYPE_KEYS or "cycl" in tk or "bik" in tk


def create_authenticated_garmin():
    """
    建立已登入的 Garmin 連線。
    優先序：環境變數 GARMINTOKENS（base64 的 token JSON）→ 本機 token 目錄。
    絕不在此用帳密登入（雲端 IP 會觸發 Garmin 風控）；帳密只在 login_setup.py。
    token 過期時 garminconnect 會丟例外，由呼叫端捕捉並提示重跑 login_setup.py。
    """
    from garminconnect import Garmin  # lazy import：清洗邏輯與 smoke test 不需載入 SDK

    garmin = Garmin()
    token_b64 = os.environ.get("GARMINTOKENS", "").strip()
    if token_b64:
        token_json = base64.b64decode(token_b64).decode("utf-8")
        garmin.login(token_json)  # 字串長度 > 512 → 走 client.loads(token) 分支
        logger.info("已用 GARMINTOKENS 環境變數還原 Garmin 登入。")
        return garmin

    tokenstore = os.path.expanduser(
        os.environ.get("GARMINTOKENS_DIR", "~/.garminconnect")
    )
    garmin.login(tokenstore)  # 目錄/檔案不存在會丟例外
    logger.info(f"已用本機 token 目錄還原 Garmin 登入：{tokenstore}")
    return garmin


class GarminClient:
    def __init__(self, garmin):
        """garmin：已登入的 garminconnect.Garmin 實例（見 create_authenticated_garmin）。"""
        self.garmin = garmin

    # ── processed_ids 狀態（格式與舊版相同，一行一個 id）──────────────────

    def _load_processed_ids(self) -> set[str]:
        if not PROCESSED_IDS_FILE.exists():
            return set()
        return set(PROCESSED_IDS_FILE.read_text(encoding="utf-8").splitlines())

    def _save_processed_id(self, activity_id) -> None:
        with open(PROCESSED_IDS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{activity_id}\n")

    def mark_as_processed(self, activity_id) -> None:
        """將 activity_id 寫入 processed_ids.txt，避免重複分析。"""
        self._save_processed_id(activity_id)
        logger.info(f"活動 {activity_id} 已標記為已處理。")

    # ── 資料抓取 ──────────────────────────────────────────────────────────

    def fetch_new_activities(self, limit: int = 10) -> list[dict]:
        """
        抓最新 limit 筆活動 summary，濾掉 processed_ids.txt 已分析過的，
        回傳尚未分析的清單（由新到舊，與 Garmin API 原序一致）。
        summary 即含分析所需全部欄位，故不需再呼叫 detail。
        """
        activities = self.garmin.get_activities(0, limit) or []
        processed_ids = self._load_processed_ids()
        new_activities = [
            act for act in activities
            if str(act.get("activityId")) not in processed_ids
        ]
        logger.info(
            f"抓取 {len(activities)} 筆活動，其中 {len(new_activities)} 筆尚未分析。"
        )
        return new_activities

    def fetch_activity_splits(self, activity_id) -> Optional[dict]:
        """
        抓單筆活動分段。best-effort：失敗回 None 而不中斷主流程。
        回傳結構未經官方查證（見檔頭），清洗端以防禦性方式處理。
        """
        try:
            return self.garmin.get_activity_splits(activity_id)
        except Exception as e:
            logger.warning(f"抓取活動 {activity_id} 分段失敗，略過分段：{e}")
            return None

    # ── 資料清洗（純函式，不依賴 SDK，可獨立測試）────────────────────────

    @staticmethod
    def _num(value):
        """僅在是數字（非 bool）時回傳，否則 None，用於容忍缺漏欄位。"""
        if isinstance(value, bool):
            return None
        return value if isinstance(value, (int, float)) else None

    @staticmethod
    def _round_div(value, divisor: float, ndigits: int):
        """數字才做除法與四捨五入；缺漏回 None（不硬填 0，讓下游顯示 N/A）。"""
        n = GarminClient._num(value)
        return round(n / divisor, ndigits) if n is not None else None

    @staticmethod
    def _mps_to_pace(mps) -> str:
        """速度 m/s → 配速字串 '4:35 /km'；無效值回 'N/A'。"""
        n = GarminClient._num(mps)
        if not n or n <= 0:
            return "N/A"
        secs_per_km = 1000 / n
        return f"{int(secs_per_km // 60)}:{int(secs_per_km % 60):02d} /km"

    @staticmethod
    def _clean_splits(splits_raw: Optional[dict]) -> list[dict]:
        """
        清洗分段。Garmin get_activity_splits 回傳結構未查證，採防禦性：
        找不到預期鍵（lapDTOs）就回空 list，不讓主流程出錯。待真登入確認後校正。
        """
        if not splits_raw:
            return []
        laps = splits_raw.get("lapDTOs") or []
        cleaned = []
        for i, lap in enumerate(laps, start=1):
            if not isinstance(lap, dict):
                continue
            cleaned.append({
                "分段":       lap.get("lapIndex", i),
                "距離_m":     GarminClient._round_div(lap.get("distance"), 1, 1),
                "耗時_秒":    GarminClient._num(lap.get("duration")),
                "平均心率":   lap.get("averageHR"),
                "平均功率_W": lap.get("averagePower"),
                "平均配速":   GarminClient._mps_to_pace(lap.get("averageSpeed")),
            })
        return cleaned

    @staticmethod
    def clean_activity_data(activity: dict, splits_raw: Optional[dict] = None) -> dict:
        """
        從 Garmin 活動 summary 萃取分析所需欄位並換算單位。
        中文欄位名沿用舊版（維持與 ai_coach / discord_notifier 的契約）。
        缺漏欄位一律 .get() → None，不拋 KeyError（室內騎乘常缺功率/GPS 欄位）。
          距離: 公尺 → 公里；時間: 秒 → 分鐘。
        訓練負荷取代舊版 Suffer_Score；新增有氧/無氧訓練效果。
        """
        activity_type = activity.get("activityType") or {}
        return {
            "activity_id":     activity.get("activityId"),
            "活動名稱":         activity.get("activityName"),
            "運動類型":         activity_type.get("typeKey"),
            "開始時間":         activity.get("startTimeLocal"),
            "距離_km":         GarminClient._round_div(activity.get("distance"), 1000, 2),
            "總爬升_m":        GarminClient._num(activity.get("elevationGain")),
            "移動時間_min":     GarminClient._round_div(activity.get("movingDuration"), 60, 1),
            "總經過時間_min":   GarminClient._round_div(activity.get("duration"), 60, 1),
            "平均心率_bpm":     activity.get("averageHR"),
            "最大心率_bpm":     activity.get("maxHR"),
            "平均功率_W":       activity.get("avgPower"),
            "最大功率_W":       activity.get("maxPower"),
            "標準化功率_NP_W":  activity.get("normPower"),
            "平均踏頻_rpm":     activity.get("averageBikingCadenceInRevPerMinute"),
            "訓練負荷":         activity.get("activityTrainingLoad"),
            "有氧訓練效果":     activity.get("aerobicTrainingEffect"),
            "無氧訓練效果":     activity.get("anaerobicTrainingEffect"),
            "每公里分段splits": GarminClient._clean_splits(splits_raw),
        }
