"""
WellnessClient — Garmin 健康／恢復數據抓取與清洗

抓「活動當天」的睡眠、HRV、Body Battery、壓力、訓練準備度、訓練狀態，
清洗成一個扁平的中文鍵 dict（純量值，缺項填 None），供 ai_coach 結合訓練
數據評估恢復狀態、discord_notifier 顯示恢復摘要。

設計鐵則（見 docs/garmin-refactor-plan.md）：
- 任何單一項目抓取失敗都不得中斷活動分析主流程 → 每項獨立 try/except，失敗填 None。
- 日期參數格式一律 "YYYY-MM-DD"；get_body_battery 吃 (startdate, enddate) 區間，
  其餘方法吃單一 cdate（garminconnect 0.3.6 實測簽名）。

欄位查證狀態（2026-07 由 cassette / 原始碼查證）：
- HRV / Body Battery / 壓力：欄位路徑來自 repo test cassette 的真實錄製回應，VERIFIED。
  （Body Battery 無現成當日最高/最低欄位，需自 bodyBatteryValuesArray 取 max/min。）
- 睡眠 / 訓練準備度：repo 無 cassette，路徑取自作者手寫樣本 test_typed.py，UNVERIFIED。
- 訓練狀態：repo 無任何範例，結構未知，採深度搜尋 best-effort，UNVERIFIED。
  → 上述 UNVERIFIED 三項待本機真登入實跑對應 API 核對後校正（見 login_setup.py 診斷輸出）。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WellnessClient:
    def __init__(self, garmin):
        """garmin：已登入的 garminconnect.Garmin 實例（見 garmin_client.create_authenticated_garmin）。"""
        self.garmin = garmin

    # ── 抓取（每項獨立容錯，失敗不中斷）──────────────────────────────────

    def _safe(self, label: str, fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            logger.warning(f"抓取{label}失敗，略過此項：{e}")
            return None

    def fetch_wellness(self, cdate: str) -> dict:
        """
        抓 cdate（YYYY-MM-DD）當日恢復數據並清洗。
        回傳只含「非 None」欄位的扁平中文鍵 dict；該日完全無資料時回 {}。
        """
        sleep        = self._safe("睡眠", self.garmin.get_sleep_data, cdate)
        hrv          = self._safe("HRV", self.garmin.get_hrv_data, cdate)
        body_battery = self._safe("Body Battery", self.garmin.get_body_battery, cdate, cdate)
        stress       = self._safe("壓力", self.garmin.get_stress_data, cdate)
        readiness    = self._safe("訓練準備度", self.garmin.get_training_readiness, cdate)
        status       = self._safe("訓練狀態", self.garmin.get_training_status, cdate)

        cleaned = self.clean_wellness_data(sleep, hrv, body_battery, stress, readiness, status)
        # 壓成只含非 None 的精簡 dict：讓下游 `if wellness_data:` 能正確判斷有無資料
        return {k: v for k, v in cleaned.items() if v is not None}

    # ── 清洗（純函式，不依賴 SDK，可獨立測試）────────────────────────────

    @staticmethod
    def _get(d, *path):
        """安全深取 dict 路徑；任一層缺失或非 dict 回 None。"""
        cur = d
        for key in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    @staticmethod
    def _num(v):
        if isinstance(v, bool):
            return None
        return v if isinstance(v, (int, float)) else None

    @staticmethod
    def _secs_to_hours(secs):
        n = WellnessClient._num(secs)
        return round(n / 3600, 2) if n is not None else None

    @staticmethod
    def _deep_find_str(obj, key_substr: str, _depth: int = 0):
        """
        深度搜尋：回傳第一個「鍵名含 key_substr 且值為非空字串」的值。
        用於結構未知的回應（訓練狀態），找不到回 None。深度上限防呆。
        """
        if _depth > 6:
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                if key_substr.lower() in str(k).lower() and isinstance(v, str) and v:
                    return v
            for v in obj.values():
                found = WellnessClient._deep_find_str(v, key_substr, _depth + 1)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = WellnessClient._deep_find_str(item, key_substr, _depth + 1)
                if found:
                    return found
        return None

    # -- 各數據類清洗 --

    @staticmethod
    def _clean_sleep(sleep) -> dict:
        # UNVERIFIED：路徑取自 test_typed.py 手寫樣本，待真登入核對
        dto = WellnessClient._get(sleep, "dailySleepDTO") or {}
        return {
            "睡眠總時數_hr": WellnessClient._secs_to_hours(dto.get("sleepTimeSeconds")),
            "深睡_hr":       WellnessClient._secs_to_hours(dto.get("deepSleepSeconds")),
            "睡眠分數":       WellnessClient._get(dto, "sleepScores", "overall", "value"),
        }

    @staticmethod
    def _clean_hrv(hrv) -> dict:
        # VERIFIED：test_hrv_data.yaml 真實錄製
        s = WellnessClient._get(hrv, "hrvSummary") or {}
        return {
            "昨晚HRV平均_ms": s.get("lastNightAvg"),
            "週平均HRV_ms":   s.get("weeklyAvg"),
            "HRV狀態":        s.get("status"),
        }

    @staticmethod
    def _clean_body_battery(body_battery) -> dict:
        # VERIFIED：test_body_battery.yaml 真實錄製；最高/最低需自時間序列計算
        result = {
            "Body_Battery最高": None,
            "Body_Battery最低": None,
            "Body_Battery充電": None,
            "Body_Battery消耗": None,
        }
        if not isinstance(body_battery, list) or not body_battery:
            return result
        day = body_battery[0] if isinstance(body_battery[0], dict) else {}
        levels = []
        for pair in (day.get("bodyBatteryValuesArray") or []):
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                lvl = WellnessClient._num(pair[1])
                if lvl is not None:
                    levels.append(lvl)
        if levels:
            result["Body_Battery最高"] = max(levels)
            result["Body_Battery最低"] = min(levels)
        result["Body_Battery充電"] = day.get("charged")
        result["Body_Battery消耗"] = day.get("drained")
        return result

    @staticmethod
    def _clean_stress(stress) -> dict:
        # VERIFIED：test_all_day_stress.yaml 真實錄製
        s = stress if isinstance(stress, dict) else {}
        return {
            "平均壓力": s.get("avgStressLevel"),
            "最高壓力": s.get("maxStressLevel"),
        }

    @staticmethod
    def _clean_readiness(readiness) -> dict:
        # UNVERIFIED：路徑取自 test_typed.py 手寫樣本，待真登入核對
        item = {}
        if isinstance(readiness, list) and readiness and isinstance(readiness[0], dict):
            item = readiness[0]
        elif isinstance(readiness, dict):
            item = readiness
        return {
            "訓練準備度分數": item.get("score"),
            "訓練準備度等級": item.get("level"),
        }

    @staticmethod
    def _clean_training_status(status) -> dict:
        # UNVERIFIED：repo 無任何範例，結構未知 → 深度搜尋 trainingStatus 字串
        return {"訓練狀態": WellnessClient._deep_find_str(status, "trainingStatus")}

    @staticmethod
    def clean_wellness_data(
        sleep=None, hrv=None, body_battery=None,
        stress=None, readiness=None, status=None,
    ) -> dict:
        """把六個原始回應攤平成一個扁平中文鍵 dict（含 None 佔位，鍵集固定）。"""
        return {
            **WellnessClient._clean_sleep(sleep),
            **WellnessClient._clean_hrv(hrv),
            **WellnessClient._clean_body_battery(body_battery),
            **WellnessClient._clean_stress(stress),
            **WellnessClient._clean_readiness(readiness),
            **WellnessClient._clean_training_status(status),
        }
