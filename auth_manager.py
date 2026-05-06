"""
AuthManager — Strava Token 生命週期管理

負責：
- 從 tokens.json 讀取 Token
- 檢查是否即將過期（60 秒緩衝）
- 過期則用 refresh_token 自動換新，並更新 tokens.json
"""

import json
import time
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

TOKENS_FILE = Path("tokens.json")


class AuthManager:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id     = client_id
        self.client_secret = client_secret
        self.tokens        = self._load_tokens()

    # ── 讀寫 ──────────────────────────────────────────────────────────────

    def _load_tokens(self) -> dict:
        if not TOKENS_FILE.exists():
            raise FileNotFoundError(
                f"找不到 {TOKENS_FILE}。\n"
                "請先執行 get_data.py 取得初始 Token，它會自動產生此檔案。"
            )
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_tokens(self) -> None:
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tokens, f, indent=2, ensure_ascii=False)
        logger.info("tokens.json 已更新。")

    # ── Token 狀態判斷 ────────────────────────────────────────────────────

    def _is_expired(self) -> bool:
        expires_at = self.tokens.get("expires_at", 0)
        # 提前 60 秒視為過期，避免在 API 呼叫途中剛好失效
        return time.time() >= (expires_at - 60)

    # ── Token 換新 ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        logger.info("Access Token 即將過期，正在換新...")
        url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.tokens["refresh_token"],
            "grant_type":    "refresh_token",
        }
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()

        new_tokens = resp.json()
        # 只更新 token 相關欄位，保留其他設定
        for key in ("access_token", "refresh_token", "expires_at", "expires_in"):
            if key in new_tokens:
                self.tokens[key] = new_tokens[key]

        self._save_tokens()
        logger.info("Token 換新完成。")

    # ── 公開介面 ──────────────────────────────────────────────────────────

    def get_access_token(self) -> str:
        """回傳有效的 access_token，必要時自動刷新。"""
        if self._is_expired():
            self._refresh()
        return self.tokens["access_token"]
