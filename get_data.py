"""
bootstrap.py 的別名 — 首次授權腳本（只需執行一次）

執行前請先設定環境變數（或在 .env 中填入）：
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

執行後會產生 tokens.json，之後由 AuthManager 負責自動換新 Token。
"""

import os
import json
import requests

# 優先讀取 .env 檔（若有安裝 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CLIENT_ID     = os.environ.get("STRAVA_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET", "")

# Authorization Code 從 Strava OAuth 授權頁面取得（一次性）
# 授權 URL 範例：
# https://www.strava.com/oauth/authorize?client_id=YOUR_ID&redirect_uri=http://localhost&response_type=code&scope=activity:read_all
AUTHORIZATION_CODE = os.environ.get("STRAVA_AUTHORIZATION_CODE", "")


def get_initial_tokens(auth_code: str) -> None:
    """用授權碼換取 access_token + refresh_token，並存入 tokens.json。"""
    if not CLIENT_ID or not CLIENT_SECRET or not auth_code:
        print("錯誤：請先設定 STRAVA_CLIENT_ID、STRAVA_CLIENT_SECRET、STRAVA_AUTHORIZATION_CODE 環境變數。")
        return

    url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          auth_code,
        "grant_type":    "authorization_code",
    }

    resp = requests.post(url, data=payload, timeout=10)
    if resp.status_code != 200:
        print(f"授權失敗，狀態碼: {resp.status_code}")
        print(resp.text)
        return

    tokens = resp.json()

    # 移除 athlete 物件，只儲存 token 相關欄位
    tokens_to_save = {
        "token_type":    tokens.get("token_type"),
        "access_token":  tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_at":    tokens.get("expires_at"),
        "expires_in":    tokens.get("expires_in"),
    }

    with open("tokens.json", "w", encoding="utf-8") as f:
        json.dump(tokens_to_save, f, indent=2)

    print("成功取得並儲存 tokens.json！")
    print(f"  Access Token : {tokens.get('access_token')[:20]}...")
    print(f"  Refresh Token: {tokens.get('refresh_token')[:20]}...")
    print("\n接下來可以直接執行 main.py，AuthManager 會自動管理 Token 更新。")


if __name__ == "__main__":
    get_initial_tokens(AUTHORIZATION_CODE)
