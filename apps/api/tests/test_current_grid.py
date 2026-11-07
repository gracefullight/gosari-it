from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest
from gosari.sources.live import KmaAdapter
from gosari.sources.observations import current_grid_observations, kma_grid


def test_projection_known_kma_grids():
    assert kma_grid(37.5665, 126.978) == (60, 127)
    assert kma_grid(33.4996, 126.5312) == (53, 38)


def test_current_grid_uses_previous_day_before_release_and_keeps_blanks(monkeypatch):
    calls = []

    def fetch(self, nx, ny, day, hour):
        calls.append((day.isoformat(), hour))
        return [
            {"category": "T1H", "obsrValue": "12.3"},
            {"category": "RN1", "obsrValue": ""},
            {"category": "WSD", "obsrValue": "-998.9"},
            {"category": "PTY", "obsrValue": "0"},
        ], SourceManifest(
            source_id="kma_ultra_short",
            dataset_id="15084084",
            operation="getUltraSrtNcst",
            sanitized_parameters={},
        )

    monkeypatch.setattr(KmaAdapter, "current_grid", fetch)
    rows, manifests, warnings = current_grid_observations(
        Settings(), lambda: None, datetime(2026, 11, 7, 0, 20, tzinfo=ZoneInfo("Asia/Seoul"))
    )
    assert len(rows) == len(manifests) == 12
    assert set(calls) == {("2026-11-06", "2300")}
    assert rows[0]["observation_time"] == "2026-11-06T23:00:00+09:00"
    assert rows[0]["temperature_c"] == 12.3
    assert rows[0]["day_rain_mm"] is None
    assert rows[0]["rain_1h_mm"] is None
    assert rows[0]["wind_speed_ms"] is None
    assert rows[0]["precipitation_type"] == 0
    assert warnings


def test_partial_grid_failure_keeps_region_with_null_values(monkeypatch):
    def fetch(self, nx, ny, day, hour):
        if (nx, ny) == (53, 38):
            raise GosariError("UPSTREAM_FAILED")
        return [
            {"category": key, "obsrValue": "0"} for key in ("T1H", "RN1", "WSD", "PTY")
        ], SourceManifest(
            source_id="kma_ultra_short",
            dataset_id="15084084",
            operation="getUltraSrtNcst",
            sanitized_parameters={},
        )

    monkeypatch.setattr(KmaAdapter, "current_grid", fetch)
    rows, manifests, warnings = current_grid_observations(Settings(), lambda: None)
    assert len(rows) == 12
    assert 0 < len(manifests) < 12
    assert rows[0]["temperature_c"] is None
    assert rows[0]["observation_time"] is None
    assert warnings


def test_adapter_rejects_wrong_observation_time():
    class Gate:
        def get_json(self, url, params):
            return {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {
                        "items": {
                            "item": [
                                {"baseDate": "20261106", "baseTime": "2300", "nx": 53, "ny": 38}
                            ]
                        }
                    },
                }
            }, "hash"

    adapter = KmaAdapter(Gate(), Settings(kma_service_key="unit-test"))
    with pytest.raises(GosariError) as error:
        adapter.current_grid(53, 38, datetime(2026, 11, 7).date(), "0000")
    assert error.value.code == "UPSTREAM_SCHEMA_CHANGED"
