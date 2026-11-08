from datetime import date, timedelta

from gosari.agent import build_public_spec
from gosari.agent.analysis import AnalysisEngine
from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.sources import outing


def test_outing_evidence_preserves_values_scopes_and_failed_candidate(monkeypatch):
    captured = []

    class Evidence:
        def put(self, payload):
            captured.append(payload)
            return "synthetic-evidence"

    def fetch(latitude, longitude, day, hour):
        if hour == "15:00":
            raise GosariError("UPSTREAM_FAILED")
        return {
            "target_at": f"{day}T{hour}+09:00",
            "published_at": None,
            "temperature_c": 17,
            "wind_speed_kmh": 5,
            "precipitation_mm": 0,
            "precipitation_probability": 10,
            "condition": "clear",
            "kind": "forecast",
            "source": "Open-Meteo",
            "recent_context": [],
        }

    monkeypatch.setattr("gosari.agent.analysis.get_evidence_store", lambda: Evidence())
    monkeypatch.setattr(outing, "fetch_outing_weather", fetch)
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    spec = build_public_spec(
        {
            "operation": "outing_compare",
            "source_ids": ["open_meteo"],
            "candidates": [
                {"location_id": "jeju", "date": "2026-11-08", "time_slot": hour}
                for hour in ("09:00", "12:00", "15:00")
            ],
        }
    )
    result = outing.compare_outings(spec, "outing", lambda: None)
    assert result.data_status == "partial"
    assert len(result.result["candidates"]) == 2
    assert len(result.result["failed_candidates"]) == 1
    evidence = captured[0]
    assert evidence["result_values"]["candidates"][0]["weather"]["temperature_c"] == 17
    assert len(evidence["source_manifests"]) == len(evidence["input_hashes"]) == 2
    assert len(evidence["requested_scope"]["candidates"]) == 3
    assert evidence["units"]["wind_speed_kmh"] == "km/h"
    assert result.observed_period["published_at"] is None
    assert result.observed_period["publication_time_status"] == "not_provided"


def test_fetch_preserves_source_hash_and_does_not_invent_issue_time(monkeypatch):
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    days = [(date(2026, 10, 31) + timedelta(days=n)).isoformat() for n in range(7)]
    payload = {
        "hourly": {
            "time": ["2026-11-08T09:00"],
            "temperature_2m": [17],
            "weather_code": [0],
            "wind_speed_10m": [5],
            "precipitation": [0],
            "precipitation_probability": [10],
        },
        "daily": {"time": days, "temperature_2m_mean": [14] * 7, "precipitation_sum": [2] * 7},
    }
    monkeypatch.setattr(
        "gosari.sources.live.TransmissionGate.get_json", lambda *a, **kw: (payload, "source-hash")
    )
    weather = outing.fetch_outing_weather(33.4996, 126.5312, date(2026, 11, 8), "09:00")
    assert weather["published_at"] is None
    assert weather["publication_time_status"] == "not_provided"
    assert weather["source_manifest"]["content_hash"] == "source-hash"
    assert weather["target_at"] == "2026-11-08T09:00+09:00"
    assert weather["recent_context"][1]["total_rain_mm"] == 14


def test_unsupported_future_has_no_data_values_and_disabled_policy_makes_no_calls(monkeypatch):
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    calls = []
    monkeypatch.setattr(outing, "fetch_outing_weather", lambda *args: calls.append(args))
    result = outing.compare_outings(
        {
            "candidates": [
                {"location_id": "jeju", "target_date": "2027-01-01", "target_time_window": "09:00"}
            ]
        },
        "range",
        lambda: None,
    )
    assert result.data_status == "unavailable"
    assert result.result["candidates"] == []
    assert result.result["failed_candidates"][0]["reason"] == "FORECAST_RANGE"
    assert calls == []
    engine = AnalysisEngine(Settings(external_requests_enabled=False, app_profile="center"))
    assert engine.run({"operation": "outing_compare"}, "disabled").data_status == "unavailable"
    assert engine.run({"operation": "current_observation"}, "disabled").data_status == "unavailable"
    assert calls == []


def _evidence_capture(monkeypatch):
    captured = []

    class Evidence:
        def put(self, payload):
            captured.append(payload)
            return "synthetic-evidence"

    monkeypatch.setattr("gosari.agent.analysis.get_evidence_store", lambda: Evidence())
    return captured


def _open_meteo_stub(latitude, longitude, day, hour):
    return {
        "target_at": f"{day}T{hour}+09:00",
        "published_at": None,
        "publication_time_status": "not_provided",
        "temperature_c": 15,
        "wind_speed_kmh": 9,
        "precipitation_mm": 0,
        "precipitation_probability": 40,
        "condition": "cloudy",
        "kind": "forecast",
        "source": "Open-Meteo",
        "source_id": "open_meteo",
        "recent_context": [
            {
                "days": 3,
                "start": "2026-11-04",
                "end": "2026-11-06",
                "total_rain_mm": 4.0,
                "average_temperature_c": 14.0,
                "rain_valid_days": 3,
                "temperature_valid_days": 3,
            }
        ],
        "recent_context_type": "model_weather",
        "source_manifest": {"source_id": "open_meteo", "content_hash": "open-meteo-hash"},
    }


def _kma_rows(target="20261108 0900", **overrides):
    values = {"TMP": "16", "POP": "20", "WSD": "3.5", "PCP": "강수없음", "SKY": "1", "PTY": "0"}
    values.update(overrides)
    return [
        {
            "published_at": "20261107 0500",
            "target_at": target,
            "grid": "53,38",
            "category": category,
            "value": value,
        }
        for category, value in values.items()
    ]


def _kma_manifest(row_count):
    from gosari.sources import SourceManifest, now_utc

    return SourceManifest(
        source_id="kma_vilage",
        dataset_id="15084084",
        operation="getVilageFcst",
        sanitized_parameters={},
        returned_count=row_count,
        fetched_at=now_utc(),
        content_hash="kma-hash",
        source_mode="fetched",
    )


def _kma_spec(sources=("kma_vilage", "open_meteo")):
    return build_public_spec(
        {
            "operation": "outing_compare",
            "source_ids": list(sources),
            "candidates": [{"location_id": "jeju", "date": "2026-11-08", "time_slot": "09:00"}],
        }
    )


def test_kma_forecast_is_preferred_and_open_meteo_keeps_recent_context(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    captured = _evidence_capture(monkeypatch)
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr(
        outing, "korea_now", lambda: datetime(2026, 11, 7, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    )
    monkeypatch.setattr(outing, "fetch_outing_weather", _open_meteo_stub)
    calls = []

    def vilage(self, nx, ny, base_date, base_time):
        calls.append((nx, ny, base_date, base_time))
        rows = _kma_rows()
        return rows, _kma_manifest(len(rows))

    monkeypatch.setattr(outing.KmaAdapter, "vilage_forecast", vilage)
    settings = Settings(kma_service_key="unit-test", external_requests_enabled=True)
    result = outing.compare_outings(_kma_spec(), "kma", lambda: None, settings=settings)

    assert calls == [(53, 38, date(2026, 11, 7), "0500")]
    assert result.data_status == "complete"
    card = result.result["candidates"][0]
    weather = card["weather"]
    assert weather["source"] == "기상청 단기예보"
    assert weather["published_at"] == "2026-11-07T05:00:00+09:00"
    assert weather["publication_time_status"] == "provided"
    assert weather["temperature_c"] == 16.0
    assert weather["precipitation_probability"] == 20.0
    assert weather["wind_speed_kmh"] == 12.6
    assert weather["precipitation_mm"] == 0.0
    assert weather["condition"] == "clear"
    assert weather["recent_context"][0]["total_rain_mm"] == 4.0
    assert weather["recent_context_source"] == "Open-Meteo"
    assert card["forecast_status"]["published_at"] == "2026-11-07T05:00:00+09:00"
    assert result.observed_period["publication_time_status"] == "provided"
    assert result.observed_period["published_at"] == ["2026-11-07T05:00:00+09:00"]
    assert result.result["forecast_sources"] == ["기상청 단기예보"]
    assert result.warnings == []
    manifests = captured[0]["source_manifests"]
    assert [m["source_id"] for m in manifests] == ["kma_vilage", "open_meteo"]
    assert captured[0]["input_hashes"] == ["kma-hash", "open-meteo-hash"]


def test_open_meteo_only_spec_or_missing_key_never_calls_kma(monkeypatch):
    _evidence_capture(monkeypatch)
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr(outing, "fetch_outing_weather", _open_meteo_stub)
    calls = []
    monkeypatch.setattr(
        outing.KmaAdapter, "vilage_forecast", lambda *args, **kwargs: calls.append(args)
    )
    with_key = Settings(kma_service_key="unit-test", external_requests_enabled=True)
    result = outing.compare_outings(
        _kma_spec(sources=("open_meteo",)), "open-meteo-only", lambda: None, settings=with_key
    )
    assert result.result["candidates"][0]["weather"]["source"] == "Open-Meteo"
    without_key = Settings(kma_service_key=None, external_requests_enabled=True)
    result = outing.compare_outings(_kma_spec(), "no-key", lambda: None, settings=without_key)
    assert result.result["candidates"][0]["weather"]["source"] == "Open-Meteo"
    assert result.observed_period["publication_time_status"] == "not_provided"
    assert calls == []


def test_kma_failure_falls_back_to_open_meteo_with_warning(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _evidence_capture(monkeypatch)
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr(
        outing, "korea_now", lambda: datetime(2026, 11, 7, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    )
    monkeypatch.setattr(outing, "fetch_outing_weather", _open_meteo_stub)

    def failing(self, nx, ny, base_date, base_time):
        raise GosariError("UPSTREAM_FAILED")

    monkeypatch.setattr(outing.KmaAdapter, "vilage_forecast", failing)
    settings = Settings(kma_service_key="unit-test", external_requests_enabled=True)
    result = outing.compare_outings(_kma_spec(), "fallback", lambda: None, settings=settings)
    weather = result.result["candidates"][0]["weather"]
    assert weather["source"] == "Open-Meteo"
    assert weather["published_at"] is None
    assert result.data_status == "complete"
    assert result.warnings == ["제주시 기상청 단기예보 연결 불가 · Open-Meteo 모델 예보로 비교"]


def test_kma_forecast_skips_targets_outside_the_published_window(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    calls = []
    monkeypatch.setattr(
        outing.KmaAdapter, "vilage_forecast", lambda *args, **kwargs: calls.append(args)
    )
    now = datetime(2026, 11, 7, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    settings = Settings(kma_service_key="unit-test", external_requests_enabled=True)
    # 발표 범위(3일) 밖, 과거, 키 없음은 호출 없이 폴백 대상으로 돌려준다.
    for day, hour, cfg in (
        (date(2026, 11, 11), "09:00", settings),
        (date(2026, 11, 6), "09:00", settings),
        (date(2026, 11, 8), "09:00", Settings(kma_service_key=None)),
    ):
        assert (
            outing.fetch_kma_outing_forecast(33.4996, 126.5312, day, hour, cfg, lambda: None, now)
            is None
        )
    assert calls == []


def test_kma_base_time_and_precipitation_parsing():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    seoul = ZoneInfo("Asia/Seoul")
    assert (
        outing.kma_vilage_base(datetime(2026, 11, 7, 6, 5, tzinfo=seoul)).strftime("%Y-%m-%d %H%M")
        == "2026-11-07 0500"
    )
    assert (
        outing.kma_vilage_base(datetime(2026, 11, 7, 5, 5, tzinfo=seoul)).strftime("%Y-%m-%d %H%M")
        == "2026-11-07 0200"
    )
    assert (
        outing.kma_vilage_base(datetime(2026, 11, 7, 2, 5, tzinfo=seoul)).strftime("%Y-%m-%d %H%M")
        == "2026-11-06 2300"
    )
    assert outing.parse_kma_precipitation("강수없음") == 0.0
    assert outing.parse_kma_precipitation("1.0mm") == 1.0
    assert outing.parse_kma_precipitation("1mm 미만") is None
    assert outing.parse_kma_precipitation("30.0~50.0mm") is None
    assert outing.parse_kma_precipitation(None) is None
    assert outing.kma_condition(1.0, 0.0) == "clear"
    assert outing.kma_condition(4.0, 0.0) == "cloudy"
    assert outing.kma_condition(4.0, 1.0) == "rain"
    assert outing.kma_condition(3.0, 3.0) == "snow"


def test_kma_interval_precipitation_keeps_text_without_inventing_a_number(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _evidence_capture(monkeypatch)
    monkeypatch.setattr(outing, "korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr(
        outing, "korea_now", lambda: datetime(2026, 11, 7, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    )
    monkeypatch.setattr(outing, "fetch_outing_weather", _open_meteo_stub)

    def vilage(self, nx, ny, base_date, base_time):
        rows = _kma_rows(PCP="30.0~50.0mm", POP="80", PTY="1")
        return rows, _kma_manifest(len(rows))

    monkeypatch.setattr(outing.KmaAdapter, "vilage_forecast", vilage)
    settings = Settings(kma_service_key="unit-test", external_requests_enabled=True)
    result = outing.compare_outings(_kma_spec(), "interval", lambda: None, settings=settings)
    weather = result.result["candidates"][0]["weather"]
    assert weather["precipitation_mm"] is None
    assert weather["precipitation_text"] == "30.0~50.0mm"
    assert weather["condition"] == "rain"
    assert result.data_status == "complete"
    assert "비옷·여벌 양말" in result.result["preparation_checklist"]
