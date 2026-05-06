"""
StravaClient — 活動數據抓取與清洗

負責：
- 取得最新活動列表，比對 processed_ids.txt 過濾已分析的活動
- 抓取單筆活動的完整詳情
- 將原始 JSON 清洗為只含分析所需欄位的精簡結構
"""

import logging
import requests
from pathlib import Path
from typing import Optional

from auth_manager import AuthManager

logger = logging.getLogger(__name__)

STRAVA_BASE        = "https://www.strava.com/api/v3"
PROCESSED_IDS_FILE = Path("processed_ids.txt")


class StravaClient:
    def __init__(self, auth_manager: AuthManager):
        self.auth = auth_manager

    # ── 內部工具 ──────────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.auth.get_access_token()}"}

    def _load_processed_ids(self) -> set[str]:
        if not PROCESSED_IDS_FILE.exists():
            return set()
        return set(PROCESSED_IDS_FILE.read_text(encoding="utf-8").splitlines())

    def _save_processed_id(self, activity_id: int) -> None:
        with open(PROCESSED_IDS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{activity_id}\n")

    # ── 資料抓取 ──────────────────────────────────────────────────────────

    def fetch_new_activities(self, per_page: int = 10) -> list[dict]:
        """
        抓取最新活動列表（最多 per_page 筆），
        回傳尚未分析過的活動摘要清單（由新到舊）。
        """
        url    = f"{STRAVA_BASE}/athlete/activities"
        params = {"per_page": per_page}
        resp   = requests.get(url, headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()

        processed_ids  = self._load_processed_ids()
        all_activities = resp.json()
        new_activities = [
            act for act in all_activities
            if str(act["id"]) not in processed_ids
        ]

        logger.info(
            f"抓取 {len(all_activities)} 筆活動，其中 {len(new_activities)} 筆尚未分析。"
        )
        return new_activities

    def fetch_activity_detail(self, activity_id: int) -> dict:
        """抓取單筆活動的完整詳情 JSON。"""
        url  = f"{STRAVA_BASE}/activities/{activity_id}"
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        logger.info(f"已抓取活動 {activity_id} 的詳細數據。")
        return resp.json()

    # ── 資料清洗 ──────────────────────────────────────────────────────────

    @staticmethod
    def _mps_to_pace(mps: Optional[float]) -> str:
        """將速度 m/s 轉換為配速字串，例如 '4:35 /km'。"""
        if not mps or mps <= 0:
            return "N/A"
        secs_per_km = 1000 / mps
        minutes     = int(secs_per_km // 60)
        seconds     = int(secs_per_km % 60)
        return f"{minutes}:{seconds:02d} /km"

    def clean_activity_data(self, raw: dict) -> dict:
        """
        從原始 JSON 萃取分析所需欄位，並完成單位換算：
          距離: 公尺 → 公里
          時間: 秒   → 分鐘
          速度: m/s  → min/km 配速字串
        """
        cleaned_splits = []
        for split in raw.get("splits_metric", []):
            cleaned_splits.append({
                "公里數":     split.get("split"),
                "距離_m":    round(split.get("distance", 0), 1),
                "耗時_秒":   split.get("elapsed_time"),
                "配速":       self._mps_to_pace(split.get("average_speed")),
                "平均心率":   split.get("average_heartrate"),
                "平均功率_W": split.get("average_watts"),
            })

        return {
            "activity_id":       raw.get("id"),
            "活動名稱":           raw.get("name"),
            "運動類型":           raw.get("sport_type"),
            "開始時間":           raw.get("start_date_local"),
            "距離_km":           round(raw.get("distance", 0) / 1000, 2),
            "總爬升_m":          raw.get("total_elevation_gain"),
            "移動時間_min":       round(raw.get("moving_time",  0) / 60, 1),
            "總經過時間_min":     round(raw.get("elapsed_time", 0) / 60, 1),
            "平均心率_bpm":       raw.get("average_heartrate"),
            "最大心率_bpm":       raw.get("max_heartrate"),
            "平均功率_W":         raw.get("average_watts"),
            "最大功率_W":         raw.get("max_watts"),
            "標準化功率_NP_W":    raw.get("weighted_average_watts"),
            "平均踏頻_rpm":       raw.get("average_cadence"),
            "總能量輸出_kJ":      raw.get("kilojoules"),
            "Suffer_Score":      raw.get("suffer_score"),
            "每公里分段splits":   cleaned_splits,
        }

    # ── 狀態記錄 ──────────────────────────────────────────────────────────

    def mark_as_processed(self, activity_id: int) -> None:
        """將 activity_id 寫入 processed_ids.txt，避免重複分析。"""
        self._save_processed_id(activity_id)
        logger.info(f"活動 {activity_id} 已標記為已處理。")
