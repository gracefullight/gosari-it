import threading
import time
from datetime import date

import pytest

from gosari.agent import build_public_spec
from gosari.agent.coordinator import Coordinator
from gosari.agent.llm import public_model_data
from gosari.config import Settings
from gosari.domain import CacheResolution
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.sessions import Session


def test_public_candidate_gateway_discards_private_labels_and_coordinates():
    result = build_public_spec(
        {
            "operation": "outing_compare",
            "source_ids": ["open_meteo"],
            "candidates": [
                {
                    "location_id": "jeju",
                    "label": "우리 엄마 집",
                    "latitude": 37.123,
                    "longitude": 127.456,
                    "date": "2026-11-08",
                    "time_slot": "09:00",
                }
            ],
        }
    )
    candidate = result["candidates"][0]
    assert candidate["station_name"] == "제주시"
    assert candidate["latitude"] == 33.4996
    assert "label" not in candidate
    assert "우리 엄마" not in str(result)
    with pytest.raises(GosariError):
        build_public_spec(
            {
                "operation": "outing_compare",
                "candidates": [{"location_id": "jeju", "date": "not-date"}],
            }
        )


def test_async_job_is_queryable_and_cancellation_prevents_result(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *args, **kwargs: (CacheResolution.BYPASS, None)
    )

    def run(engine, spec, request_id):
        entered.set()
        release.wait(timeout=2)
        engine.checkpoint()
        return ResultEnvelope(request_id=request_id, result={"value": 1})

    monkeypatch.setattr("gosari.agent.analysis.AnalysisEngine.run", run)
    coordinator = Coordinator(Settings())
    session = Session(Settings())
    job = coordinator.start_job(
        session, {"operation": "current_observation", "source_ids": ["kma_aws"]}
    )
    assert entered.wait(timeout=1)
    assert coordinator.get_job(session, job.job_id).stage.value == "running"
    with pytest.raises(GosariError):
        coordinator.get_job(Session(Settings()), job.job_id)
    coordinator.cancel_job(session, job.job_id)
    release.set()
    deadline = time.monotonic() + 2
    while job.stage.value != "cancelled" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert job.result is None
    assert job.cancelled
    assert job.stage.value == "cancelled"


def test_model_projection_excludes_arbitrary_personal_values():
    payload = public_model_data(
        {
            "operation": "outing_compare",
            "candidate_id": "private-record-id",
            "label": "김말숙 집",
            "activity_text": "가족 사정 비밀",
            "station_name": "제주시",
            "temperature_c": 17.5,
        }
    )
    assert "김말숙" not in str(payload)
    assert "비밀" not in str(payload)
    assert "private-record-id" not in str(payload)
    assert payload["station_name"] == "제주시"
    assert payload["temperature_c"] == 17.5


def test_live_outing_uses_each_date_and_hour_and_partial_failure(monkeypatch):
    calls = []

    def fetch(latitude, longitude, day, hour):
        calls.append((day, hour))
        if hour == "15:00":
            raise GosariError("UPSTREAM_FAILED")
        return {
            "target_at": f"{day}T{hour}+09:00",
            "published_at": None,
            "temperature_c": 13.5,
            "precipitation_probability": 80,
            "wind_speed_kmh": 25,
            "condition": "rain",
            "precipitation_mm": 2,
            "kind": "forecast",
            "source": "Open-Meteo",
            "source_url": "https://open-meteo.com/",
            "recent_context": [{"days": 3, "total_rain_mm": 5, "average_temperature_c": 14}],
        }

    monkeypatch.setattr("gosari.sources.outing.fetch_outing_weather", fetch)
    monkeypatch.setattr("gosari.agent.analysis.db_available", lambda: False)
    from gosari.agent.analysis import AnalysisEngine

    spec = build_public_spec(
        {
            "operation": "outing_compare",
            "source_ids": ["open_meteo"],
            "candidates": [
                {"location_id": "jeju", "date": "2026-11-08", "time_slot": "09:00"},
                {"location_id": "seogwipo", "date": "2026-11-09", "time_slot": "15:00"},
            ],
            "preferred_elements": ["low_rain", "low_wind"],
        }
    )
    result = AnalysisEngine(Settings(app_profile="center", external_requests_enabled=True)).run(
        spec, "test"
    )
    assert calls == [(date(2026, 11, 8), "09:00"), (date(2026, 11, 9), "15:00")]
    assert result.data_status == "partial"
    assert len(result.result["candidates"]) == len(result.result["failed_candidates"]) == 1
    assert "비옷·여벌 양말" in result.result["preparation_checklist"]
    assert "보온 겉옷" in result.result["preparation_checklist"]
    assert "방풍 겉옷" in result.result["preparation_checklist"]


def test_scope_fingerprint_covers_candidates_and_price_settlement(monkeypatch):
    from gosari.cache.semantic import condition_fingerprint

    base = {"operation": "market_query", "settlement_date": "2026-04-12", "package_code": "kg"}
    assert condition_fingerprint(base) != condition_fingerprint(
        {**base, "settlement_date": "2026-04-13"}
    )
    assert condition_fingerprint(base) != condition_fingerprint({**base, "package_code": "g"})
    assert condition_fingerprint(
        {"candidates": [{"target_date": "2026-11-08"}]}
    ) != condition_fingerprint({"candidates": [{"target_date": "2026-11-09"}]})


def test_institution_denial_uses_disclosed_archive_without_repeated_auth_calls(monkeypatch):
    from gosari.domain import SourceMode
    from gosari.sources import SourceManifest
    from gosari.sources.observations import live_observations

    calls = []

    def denied(*args, **kwargs):
        calls.append("institution")
        raise GosariError("POLICY_BLOCKED")

    def fallback(name, start, end):
        calls.append(start.year)
        return [], SourceManifest(
            source_id="open_meteo",
            dataset_id="archive",
            operation="daily_reanalysis",
            sanitized_parameters={},
            source_mode="fetched",
        )

    monkeypatch.setattr("gosari.sources.observations.JejuHubAdapter.daily_weather", denied)
    monkeypatch.setattr("gosari.sources.observations.archive_observations", fallback)
    _, mode, manifests, warnings = live_observations(
        {
            "station_selections": [{"source_id": "jeju_579", "station_name": "선흘"}],
            "years": [2023, 2024],
        },
        Settings(external_requests_enabled=True),
        lambda: None,
    )
    assert calls == ["institution", 2023, 2024]
    assert mode == SourceMode.FETCHED
    assert all(m.source_id == "open_meteo" for m in manifests)
    assert warnings == ["기관 연결 불가 · Open-Meteo 과거 날씨로 비교"]


def test_source_retry_stops_before_another_call_when_cancelled(monkeypatch):
    import httpx

    from gosari.sources.live import TransmissionGate

    calls = []
    cancelled = False

    def checkpoint():
        if cancelled:
            raise GosariError("ACTION_NOT_ALLOWED")

    def rate_limit(*args, **kwargs):
        nonlocal cancelled
        calls.append(True)
        cancelled = True
        return httpx.Response(429, headers={"Retry-After": "10"})

    monkeypatch.setattr("gosari.sources.live.httpx.get", rate_limit)
    gate = TransmissionGate(Settings(external_requests_enabled=True), checkpoint=checkpoint)
    with pytest.raises(GosariError):
        gate.get_json("https://apis.data.go.kr/example", {})
    assert len(calls) == 1
