"""
DiscordNotifier — Discord Webhook 推播模組

負責：
- 將 AI 報告與活動摘要組裝成 Discord Embed 格式
- 透過 Webhook URL 發送通知
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# Discord Embed 側邊顏色（十進位 RGB）
SPORT_COLORS = {
    "Ride":        0xFC4C02,  # Strava 橘
    "VirtualRide": 0xFC4C02,
    "Run":         0x00B4D8,  # 藍
    "Walk":        0x4CAF50,  # 綠
    "Swim":        0x0096C7,  # 深藍
}
DEFAULT_COLOR = 0x7289DA     # Discord 紫

STRAVA_ACTIVITY_URL = "https://www.strava.com/activities/{id}"

# Discord Embed description 上限為 4096 字元
MAX_DESCRIPTION_LEN = 4000


class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    # ── Payload 組裝 ──────────────────────────────────────────────────────

    def _build_embed(self, cleaned_data: dict, ai_report: str) -> dict:
        activity_id  = cleaned_data.get("activity_id")
        sport_type   = cleaned_data.get("運動類型", "")
        color        = SPORT_COLORS.get(sport_type, DEFAULT_COLOR)
        activity_url = STRAVA_ACTIVITY_URL.format(id=activity_id)
        title        = f"🏅 新活動分析：{cleaned_data.get('活動名稱', '未命名活動')}"

        # ── Fields（摘要數字卡片）────────────────────────────────────────
        def val(key: str, unit: str = "") -> str:
            v = cleaned_data.get(key)
            return f"{v} {unit}".strip() if v is not None else "N/A"

        fields = [
            {"name": "📏 距離",       "value": val("距離_km", "km"),  "inline": True},
            {"name": "⏱️ 移動時間",   "value": val("移動時間_min", "分"), "inline": True},
            {"name": "⛰️ 總爬升",     "value": val("總爬升_m", "m"),  "inline": True},
            {"name": "❤️ 平均心率",   "value": val("平均心率_bpm", "bpm"), "inline": True},
            {"name": "❤️‍🔥 最大心率", "value": val("最大心率_bpm", "bpm"), "inline": True},
            {"name": "😓 Suffer Score", "value": val("Suffer_Score"),  "inline": True},
        ]

        # 有功率數據才加入功率欄位（騎車專屬）
        if cleaned_data.get("平均功率_W") is not None:
            fields.extend([
                {"name": "⚡ 平均功率", "value": val("平均功率_W", "W"),       "inline": True},
                {"name": "⚡ NP 標準化功率", "value": val("標準化功率_NP_W", "W"), "inline": True},
                {"name": "⚡ 最大功率", "value": val("最大功率_W", "W"),       "inline": True},
            ])

        # ── AI 報告（截斷至安全長度）─────────────────────────────────────
        if len(ai_report) > MAX_DESCRIPTION_LEN:
            report_display = ai_report[:MAX_DESCRIPTION_LEN] + "\n\n*（報告過長，已截斷）*"
        else:
            report_display = ai_report

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        return {
            "title":       title,
            "url":         activity_url,
            "description": report_display,
            "color":       color,
            "fields":      fields,
            "footer": {
                "text": f"Strava ID: {activity_id}  ·  分析時間: {now_str}",
            },
            "thumbnail": {
                # 腳踏車 emoji 作為縮圖
                "url": "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f6b4.png"
            },
        }

    def _build_plan_embed(self, training_plan: str) -> dict:
        """訓練計畫獨立 Embed，以綠色側邊條區隔視覺。"""
        if len(training_plan) > MAX_DESCRIPTION_LEN:
            plan_display = training_plan[:MAX_DESCRIPTION_LEN] + "\n\n*（計畫過長，已截斷）*"
        else:
            plan_display = training_plan

        return {
            "title":       "📅 接下來的訓練計畫",
            "description": plan_display,
            "color":       0x57F287,  # Discord 綠，象徵往前衝
        }

    def _build_payload(self, cleaned_data: dict, ai_report: str, training_plan: str = "") -> dict:
        embeds = [self._build_embed(cleaned_data, ai_report)]
        if training_plan:
            embeds.append(self._build_plan_embed(training_plan))
        return {
            "username": "AI 虛擬教練 🤖",
            "embeds":   embeds,
        }

    # ── 發送 ──────────────────────────────────────────────────────────────

    def send(self, cleaned_data: dict, ai_report: str, training_plan: str = "") -> None:
        """組裝 Embed 並發送到 Discord Webhook。training_plan 為選填。"""
        payload = self._build_payload(cleaned_data, ai_report, training_plan)
        resp    = requests.post(self.webhook_url, json=payload, timeout=10)

        # Discord 成功回應：200（有內容）或 204（無內容）
        if resp.status_code in (200, 204):
            logger.info("Discord 通知發送成功。")
        else:
            logger.error(
                f"Discord 發送失敗，狀態碼: {resp.status_code}，回應: {resp.text}"
            )
            resp.raise_for_status()
