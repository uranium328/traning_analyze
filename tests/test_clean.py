"""
tests/test_clean.py — GarminClient.clean_activity_data 的 smoke test

用假 Garmin activity summary dict 驗證：
- 中文輸出欄位名齊全，且與 ai_coach / discord_notifier 的契約一致
- 單位換算正確（距離 公尺→公里、時間 秒→分鐘）
- 缺漏欄位不拋 KeyError，回 None（室內騎乘常缺功率/GPS 欄位）

執行：python -m pytest tests/
欄位名參考 garminconnect 0.3.6 get_activities() summary（已查證/實測欄位存在）。
"""

from garmin_client import GarminClient, is_cycling_type


FAKE_ACTIVITY = {
    "activityId": 123456789,
    "activityName": "晨騎 Zone 2",
    "activityType": {"typeKey": "road_biking"},
    "startTimeLocal": "2026-07-03 06:30:00",
    "distance": 42340.0,          # 公尺 → 42.34 km
    "elevationGain": 350.0,
    "movingDuration": 5400,       # 秒 → 90.0 min
    "duration": 5700,             # 秒 → 95.0 min
    "averageHR": 142,
    "maxHR": 171,
    "avgPower": 210,
    "maxPower": 640,
    "normPower": 225,
    "averageBikingCadenceInRevPerMinute": 88,
    "activityTrainingLoad": 120.5,
    "aerobicTrainingEffect": 3.2,
    "anaerobicTrainingEffect": 0.8,
}


def test_clean_maps_all_contract_fields():
    cleaned = GarminClient.clean_activity_data(FAKE_ACTIVITY)
    # 下游 discord_notifier / ai_coach 依賴的鍵必須存在且不多不少
    expected_keys = {
        "activity_id", "活動名稱", "運動類型", "開始時間",
        "距離_km", "總爬升_m", "移動時間_min", "總經過時間_min",
        "平均心率_bpm", "最大心率_bpm", "平均功率_W", "最大功率_W",
        "標準化功率_NP_W", "平均踏頻_rpm", "訓練負荷",
        "有氧訓練效果", "無氧訓練效果", "每公里分段splits",
    }
    assert set(cleaned.keys()) == expected_keys


def test_clean_unit_conversions():
    c = GarminClient.clean_activity_data(FAKE_ACTIVITY)
    assert c["activity_id"] == 123456789
    assert c["運動類型"] == "road_biking"
    assert c["距離_km"] == 42.34          # 42340 / 1000
    assert c["移動時間_min"] == 90.0       # 5400 / 60
    assert c["總經過時間_min"] == 95.0     # 5700 / 60
    assert c["平均心率_bpm"] == 142
    assert c["最大功率_W"] == 640
    assert c["標準化功率_NP_W"] == 225
    assert c["訓練負荷"] == 120.5
    assert c["有氧訓練效果"] == 3.2
    assert c["無氧訓練效果"] == 0.8
    assert c["平均踏頻_rpm"] == 88


def test_clean_tolerates_missing_fields():
    # 室內騎乘：缺功率、距離、GPS 相關欄位，不應拋例外
    minimal = {
        "activityId": 42,
        "activityName": "室內訓練台",
        "activityType": {"typeKey": "indoor_cycling"},
        "startTimeLocal": "2026-07-03 20:00:00",
        "duration": 3600,
    }
    c = GarminClient.clean_activity_data(minimal)
    assert c["activity_id"] == 42
    assert c["總經過時間_min"] == 60.0
    assert c["距離_km"] is None          # 缺 distance → None（不硬填 0）
    assert c["平均功率_W"] is None
    assert c["移動時間_min"] is None
    assert c["每公里分段splits"] == []


def test_clean_handles_empty_activity_type():
    c = GarminClient.clean_activity_data({"activityId": 1})
    assert c["運動類型"] is None
    assert c["活動名稱"] is None


def test_clean_splits_from_lapdtos():
    # 注意：splits 結構未經官方查證，此處以社群慣例 lapDTOs 形狀測試防禦性清洗；
    # 真登入確認結構後可能需調整鍵名（見 garmin_client._clean_splits 檔頭註解）。
    splits_raw = {"lapDTOs": [
        {"lapIndex": 1, "distance": 1000.0, "duration": 150,
         "averageHR": 140, "averagePower": 200, "averageSpeed": 6.67},
    ]}
    c = GarminClient.clean_activity_data(FAKE_ACTIVITY, splits_raw)
    assert len(c["每公里分段splits"]) == 1
    lap = c["每公里分段splits"][0]
    assert lap["距離_m"] == 1000.0
    assert lap["平均心率"] == 140
    assert lap["平均配速"].endswith("/km")


def test_clean_splits_empty_when_no_lapdtos():
    assert GarminClient.clean_activity_data(FAKE_ACTIVITY, {})["每公里分段splits"] == []
    assert GarminClient.clean_activity_data(FAKE_ACTIVITY, None)["每公里分段splits"] == []


def test_is_cycling_type():
    assert is_cycling_type("cycling")
    assert is_cycling_type("road_biking")
    assert is_cycling_type("virtual_ride")      # 在白名單
    assert is_cycling_type("indoor_cycling")
    assert is_cycling_type("gravel_cycling")
    assert is_cycling_type("MOUNTAIN_BIKING")    # 大小寫不敏感
    assert not is_cycling_type("running")
    assert not is_cycling_type("lap_swimming")
    assert not is_cycling_type(None)
    assert not is_cycling_type("")
