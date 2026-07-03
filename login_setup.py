"""
login_setup.py — Garmin 一次性本機登入，匯出 token 供 GitHub secret GARMINTOKENS

用法（在本機互動執行一次；CI/雲端不要跑這支）：
    python login_setup.py

流程：
1. 輸入 Garmin 帳密（支援 MFA），garminconnect 完成登入。
2. 以 garmin.client.dumps() 取得 token JSON，base64 編碼後印出。
3. 把印出的整串貼進 GitHub repo 的 secret GARMINTOKENS。
   token 效期約一年；過期時（主程式提示需重新登入）再跑一次本支更新 secret。

安全提醒：印出的 token 等同你的 Garmin 登入憑證，切勿貼上網、commit 或外流。

技術背景（garminconnect 0.3.6）：garth 已 deprecated，改用自研 auth engine；
Garmin 物件無 .garth 屬性，token 序列化改走 garmin.client.dumps()（回傳 JSON 字串）。
"""

import base64
import getpass
import sys


def main() -> None:
    from garminconnect import Garmin

    print("===== Garmin 一次性登入設定 =====")
    email = input("Garmin 帳號 email：").strip()
    password = getpass.getpass("Garmin 密碼（輸入時不顯示）：")

    garmin = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("請輸入 Garmin MFA 驗證碼：").strip(),
    )
    try:
        garmin.login()
    except Exception as e:
        print(f"\n[登入失敗] {e}", file=sys.stderr)
        print(
            "請確認帳密與 MFA 是否正確；若持續失敗，可能是 garminconnect 需升級"
            "（pip install -U garminconnect）。",
            file=sys.stderr,
        )
        sys.exit(1)

    token_json = garmin.client.dumps()
    token_b64 = base64.b64encode(token_json.encode("utf-8")).decode("ascii")

    print("\n" + "=" * 60)
    print("複製以下整串（單行），存進 GitHub secret：GARMINTOKENS")
    print("=" * 60 + "\n")
    print(token_b64)
    print("\n" + "=" * 60)
    print("以上為登入憑證，請勿外流／commit。")
    print("=" * 60)

    # 診斷（可選）：印出一筆真實騎乘活動的欄位 key 與 splits 頂層結構，
    # 供校正重構規劃階段查無官方出處的三處：踏頻欄位名、typeKey、splits 結構。
    # 失敗不影響上面已完成的 token 匯出。
    try:
        acts = garmin.get_activities(0, 1) or []
        if acts:
            act = acts[0]
            print("\n[診斷] 最新一筆活動的欄位 keys：")
            print(sorted(act.keys()))
            at = act.get("activityType") or {}
            print("[診斷] activityType.typeKey =", at.get("typeKey"))
            print(
                "[診斷] 踏頻相關欄位：",
                {k: v for k, v in act.items() if "adence" in k.lower()},
            )
            splits = garmin.get_activity_splits(act.get("activityId"))
            print(
                "[診斷] splits 頂層 keys：",
                list(splits.keys()) if isinstance(splits, dict) else type(splits),
            )
    except Exception as e:
        print(f"\n[診斷略過] 取得診斷資料失敗（不影響 token 匯出）：{e}")


if __name__ == "__main__":
    main()
