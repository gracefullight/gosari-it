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
