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


class MfaAborted(Exception):
    """使用者在 MFA 提示留空中止——通常代表密碼輸入錯誤，而非帳號真的需要 MFA。"""


def _resolve_mfa_code(mfa_flow, input_fn=input) -> str:
    """
    取得 MFA 驗證碼；使用者留空按 Enter 則 raise MfaAborted。

    背景（garminconnect 0.3.6 已知行為）：登入有多個策略，其中 web「widget」策略
    以頁面標題判斷是否需要 MFA，而 Garmin 登入 widget 頁標題本身含
    "Authentication Application"——因此**密碼輸入錯誤**卡在該頁時，會被誤判成需要 MFA。
    故 widget 流程觸發時額外警告：沒開兩步驟驗證就代表密碼打錯，留空 Enter 即可乾淨中止。
    （ios/portal 策略的 MFA 來自 API 明確回應，較可信，但同樣提供留空中止的安全閥。）
    """
    if mfa_flow == "widget":
        print("\n[注意] 登入要求 MFA 驗證碼，但這一步在**密碼輸入錯誤**時也可能被誤觸。")
        print("  · 帳號沒開兩步驟驗證 → 這代表密碼打錯了：直接按 Enter 中止，檢查密碼後重跑。")
        print("  · 帳號確實有開兩步驟驗證 → 請輸入驗證碼。")
    code = input_fn("請輸入 Garmin MFA 驗證碼（未開 MFA 請直接按 Enter 中止）：").strip()
    if not code:
        raise MfaAborted()
    return code


def main() -> None:
    from garminconnect import Garmin, GarminConnectAuthenticationError

    print("===== Garmin 一次性登入設定 =====")
    email = input("Garmin 帳號 email：").strip()
    password = getpass.getpass("Garmin 密碼（輸入時不顯示）：")

    # 用 return_on_mfa=True 的兩階段流程：login() 遇到 MFA 只回傳 ("needs_mfa", None)，
    # 不在函式內部呼叫 prompt_mfa。原因：Garmin.login() 有個 catch-all（__init__.py）
    # 會把內部丟出的例外一律轉成 ConnectionError——若在那裡面 raise 中止訊號會被吞掉。
    # 改成回傳後由本程式接手，密碼錯誤（mobile 策略明確回報）能乾淨區分、中止也乾淨。
    garmin = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        mfa_status, _ = garmin.login()
    except GarminConnectAuthenticationError as e:
        print(f"\n[登入失敗] 帳號或密碼錯誤：{e}", file=sys.stderr)
        print("請確認 Garmin 帳密後重跑：python login_setup.py", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[登入失敗] {e}", file=sys.stderr)
        print(
            "若持續失敗，可能是 Garmin 端風控或 garminconnect 需升級"
            "（pip install -U garminconnect）。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 需要 MFA：此時控制權在我們手上（不在被 catch-all 包住的 login 內部）。
    if mfa_status == "needs_mfa":
        mfa_flow = getattr(getattr(garmin, "client", None), "_mfa_flow", None)
        try:
            mfa_code = _resolve_mfa_code(mfa_flow)
        except MfaAborted:
            print(
                "\n已中止：未輸入 MFA 驗證碼（多半是密碼打錯）。"
                "請確認 Garmin 密碼正確後重跑：python login_setup.py",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            garmin.resume_login({}, mfa_code)   # client_state 被忽略，MFA 狀態存在 client 上
        except Exception as e:
            print(f"\n[MFA 驗證失敗] {e}", file=sys.stderr)
            print("請確認驗證碼正確且未過期後重跑：python login_setup.py", file=sys.stderr)
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
