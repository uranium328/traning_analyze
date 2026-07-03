"""
tests/test_wellness.py — WellnessClient 清洗與容錯 smoke test

驗證：
- clean_wellness_data 把六類原始回應攤平成扁平中文鍵 dict、單位換算正確
  （原始回應形狀取自 garminconnect repo 的 cassette / 作者樣本）
- Body Battery 最高/最低由時間序列自算
- fetch_wellness：單項 API 拋例外不中斷、輸出壓成只含非 None 欄位

執行：python -m pytest tests/
"""

from unittest.mock import MagicMock

from wellness_client import WellnessClient


# 形狀對照：HRV/BodyBattery/壓力 來自 cassette 真實錄製；睡眠/準備度 來自作者樣本
RAW_SLEEP = {"dailySleepDTO": {
    "sleepTimeSeconds": 25200, "deepSleepSeconds": 5400,
    "sleepScores": {"overall": {"value": 84}},
}}
RAW_HRV = {"hrvSummary": {"lastNightAvg": 40, "weeklyAvg": 42, "status": "BALANCED"}, "hrv": []}
RAW_BODY_BATTERY = [{
    "date": "2026-07-03", "charged": 23, "drained": 30,
    "bodyBatteryValuesArray": [[1, 50], [2, 80], [3, 20]],
}]
RAW_STRESS = {"avgStressLevel": 28, "maxStressLevel": 87}
RAW_READINESS = [{"score": 72, "level": "HIGH"}]
RAW_STATUS = {"latestData": {"trainingStatusFeedbackPhrase": "PRODUCTIVE_1"}}


def test_clean_wellness_full():
    w = WellnessClient.clean_wellness_data(
        RAW_SLEEP, RAW_HRV, RAW_BODY_BATTERY, RAW_STRESS, RAW_READINESS, RAW_STATUS
    )
    # 睡眠（UNVERIFIED 路徑，但換算邏輯可測）
    assert w["睡眠總時數_hr"] == 7.0          # 25200 / 3600
    assert w["深睡_hr"] == 1.5               # 5400 / 3600
    assert w["睡眠分數"] == 84
    # HRV（VERIFIED）
    assert w["昨晚HRV平均_ms"] == 40
    assert w["週平均HRV_ms"] == 42
    assert w["HRV狀態"] == "BALANCED"
    # Body Battery（VERIFIED，最高/最低自算）
    assert w["Body_Battery最高"] == 80
    assert w["Body_Battery最低"] == 20
    assert w["Body_Battery充電"] == 23
    assert w["Body_Battery消耗"] == 30
    # 壓力（VERIFIED）
    assert w["平均壓力"] == 28
    assert w["最高壓力"] == 87
    # 準備度（UNVERIFIED）
    assert w["訓練準備度分數"] == 72
    assert w["訓練準備度等級"] == "HIGH"
    # 訓練狀態（深度搜尋）
    assert w["訓練狀態"] == "PRODUCTIVE_1"


def test_clean_wellness_all_none():
    w = WellnessClient.clean_wellness_data()
    assert all(v is None for v in w.values())
    # 鍵集固定（即使全 None 也要有這些鍵，供下游穩定判斷）
    assert "HRV狀態" in w and "睡眠總時數_hr" in w and "訓練狀態" in w


def test_clean_wellness_tolerates_partial_shapes():
    # body battery 陣列缺 level、sleep 缺 dailySleepDTO：不應拋例外
    w = WellnessClient.clean_wellness_data(
        sleep={}, body_battery=[{"charged": 5}], stress={"avgStressLevel": 10},
    )
    assert w["睡眠總時數_hr"] is None
    assert w["Body_Battery最高"] is None      # 無 bodyBatteryValuesArray
    assert w["Body_Battery充電"] == 5
    assert w["平均壓力"] == 10


def test_fetch_wellness_compacts_and_survives_partial_failure():
    garmin = MagicMock()
    garmin.get_sleep_data.return_value = RAW_SLEEP
    garmin.get_hrv_data.side_effect = Exception("HRV 服務暫時失敗")   # 單項失敗
    garmin.get_body_battery.return_value = RAW_BODY_BATTERY
    garmin.get_stress_data.return_value = RAW_STRESS
    garmin.get_training_readiness.return_value = None
    garmin.get_training_status.return_value = None

    wc = WellnessClient(garmin)
    result = wc.fetch_wellness("2026-07-03")   # 不應拋例外

    # body battery 用區間參數 (cdate, cdate)
    garmin.get_body_battery.assert_called_once_with("2026-07-03", "2026-07-03")
    # 壓成只含非 None：HRV 失敗 → 不出現；壓力/睡眠/BB 有值 → 出現
    assert "HRV狀態" not in result
    assert result["睡眠總時數_hr"] == 7.0
    assert result["平均壓力"] == 28
    assert result["Body_Battery最高"] == 80
    assert all(v is not None for v in result.values())
