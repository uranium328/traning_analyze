"""
tests/test_process_activity.py — main.process_activity 假資料 end-to-end（mock 外部依賴）

驗證清洗 → 分析 → 計畫 → 推播 的串接正確，且送進 notifier 的是含中文欄位的
cleaned dict。不觸網、不寫 processed_ids.txt（mark_as_processed 換成 no-op）。

執行：python -m pytest tests/
"""

from unittest.mock import MagicMock

import main
from garmin_client import GarminClient


def test_process_activity_end_to_end():
    fake_activity = {
        "activityId": 999,
        "activityName": "測試騎乘",
        "activityType": {"typeKey": "road_biking"},
        "startTimeLocal": "2026-07-03 07:00:00",
        "distance": 30000.0,      # → 30.0 km
        "movingDuration": 3600,   # → 60.0 min
        "duration": 3700,
        "averageHR": 138,
        "avgPower": 190,
    }

    # 真 GarminClient + mock 底層 API：clean 用真的，splits 回 None，
    # mark_as_processed 換成 no-op 以免污染 processed_ids.txt
    api = MagicMock()
    api.get_activity_splits.return_value = None
    garmin = GarminClient(api)
    processed = []
    garmin.mark_as_processed = lambda aid: processed.append(aid)

    coach = MagicMock()
    coach.analyze.return_value = "【分析報告】Zone 2 紀律良好。"
    coach.generate_training_plan.return_value = "Day+1 休息。"

    notifier = MagicMock()

    # mock 恢復數據：回傳非空 wellness dict
    wellness = MagicMock()
    fake_wellness = {"HRV狀態": "BALANCED", "平均壓力": 28}
    wellness.fetch_wellness.return_value = fake_wellness

    main.process_activity(fake_activity, garmin, coach, notifier, wellness)

    coach.analyze.assert_called_once()
    coach.generate_training_plan.assert_called_once()

    # 恢復數據以活動當日（startTimeLocal 前 10 碼）為日期抓取
    wellness.fetch_wellness.assert_called_once_with("2026-07-03")

    # 送進 coach.analyze 的是清洗後 dict + 恢復數據
    cleaned_arg = coach.analyze.call_args.args[0]
    assert cleaned_arg["距離_km"] == 30.0
    assert cleaned_arg["移動時間_min"] == 60.0
    assert cleaned_arg["運動類型"] == "road_biking"
    assert coach.analyze.call_args.args[1] == fake_wellness

    # notifier.send 收到 cleaned + 報告 + 計畫 + 恢復數據
    notifier.send.assert_called_once()
    kwargs = notifier.send.call_args.kwargs
    assert kwargs["cleaned_data"]["活動名稱"] == "測試騎乘"
    assert kwargs["ai_report"].startswith("【分析報告】")
    assert kwargs["training_plan"] == "Day+1 休息。"
    assert kwargs["wellness_data"] == fake_wellness

    # 已標記處理（僅此活動）
    assert processed == [999]
