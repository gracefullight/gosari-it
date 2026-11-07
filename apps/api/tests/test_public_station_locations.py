from datetime import timedelta

import pytest

from gosari.agent import PUBLIC_JEJU_STATIONS, build_public_spec
from gosari.agent.dialogue import public_spec_for_tool
from gosari.domain.errors import GosariError
from gosari.sources.locations import public_places, resolve_public_place, station_catalog
from gosari.sources.observations import kma_grid
from gosari.sources.weather import JEJU_LOCATIONS, korea_today


def test_all_42_official_stations_have_verified_coordinates_and_provenance():
    stations = station_catalog()
    assert {(row["name"], row["code"]) for row in stations.values()} == set(PUBLIC_JEJU_STATIONS)
    assert len(stations) == 42
    for row in stations.values():
        assert 32 < row["latitude"] < 35 and 125 < row["longitude"] < 128
        assert row["coordinate_source"] == "jeju_578"
        assert len(row["coordinate_content_hash"]) == 64
        assert row["coordinate_verified_at"].startswith("2026-11-07")
    assert resolve_public_place("한라산남벽") == ("aws:965", "한라산남벽", 33.3524, 126.533)
    assert stations["aws:965"]["altitude_m"] == 1576
    assert len(JEJU_LOCATIONS) == 12


@pytest.mark.parametrize("identifier", ["aws:965", "965", "한라산남벽"])
def test_halla_name_or_public_id_resolves_in_actual_tool_args(identifier):
    day = (korea_today() + timedelta(days=1)).isoformat()
    spec = public_spec_for_tool(
        "outing_compare",
        {
            "candidates": [
                {
                    "location_id": identifier,
                    "date": day,
                    "time_slot": "09:00",
                }
            ]
        },
    )
    row = spec["candidates"][0]
    assert row["location_id"] == "aws:965" and row["station_name"] == "한라산남벽"
    assert (row["latitude"], row["longitude"]) == (33.3524, 126.533)
    forged = build_public_spec({**spec, "candidates": [{**row, "latitude": 1, "longitude": 2}]})
    assert forged["candidates"][0]["latitude"] == 33.3524
    assert forged["candidates"][0]["longitude"] == 126.533


def test_official_forecast_uses_halla_station_grid_and_duplicate_names_stay_distinct():
    forecast = public_spec_for_tool(
        "forecast_compare",
        {
            "location_id": "aws:965",
            "forecast_published_at": "2026-11-07T02:00+09:00",
            "forecast_target_times": ["2026-11-08T09:00+09:00"],
        },
    )
    assert forecast["forecast_grid_id"] == ",".join(map(str, kma_grid(33.3524, 126.533)))
    with pytest.raises(GosariError):
        resolve_public_place("강정")
    assert resolve_public_place("aws:685") != resolve_public_place("aws:980")
    with pytest.raises(GosariError):
        resolve_public_place("PRIVATE_CANARY_LOCATION")
    assert len(public_places()) == 55


def test_actual_outing_fetch_receives_official_halla_coordinate_and_result_preserves_it(
    monkeypatch,
):
    from gosari.sources.outing import compare_outings

    fetched = []
    day = (korea_today() + timedelta(days=1)).isoformat()

    def weather(latitude, longitude, selected, hour):
        fetched.append((latitude, longitude, selected.isoformat(), hour))
        return {
            "target_at": f"{day}T09:00+09:00",
            "published_at": None,
            "temperature_c": 5.2,
            "precipitation_probability": 20,
            "precipitation_mm": 0,
            "wind_speed_kmh": 12,
            "condition": "cloudy",
            "kind": "forecast",
            "source": "Open-Meteo",
            "recent_context": [],
        }

    monkeypatch.setattr("gosari.sources.outing.fetch_outing_weather", weather)
    spec = public_spec_for_tool(
        "outing_compare",
        {
            "candidates": [
                {
                    "location_id": "aws:965",
                    "date": day,
                    "time_slot": "09:00",
                }
            ]
        },
    )
    result = compare_outings(spec, "test-halla", lambda: None)
    assert fetched == [(33.3524, 126.533, day, "09:00")]
    row = result.result["candidates"][0]
    assert row["station_name"] == "한라산남벽" and row["latitude"] == 33.3524
    assert row["longitude"] == 126.533 and row["altitude_m"] == 1576
    assert row["coordinate_source"] == "jeju_578"
    assert row["weather"]["temperature_c"] == 5.2
