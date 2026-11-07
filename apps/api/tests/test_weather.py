import asyncio
from datetime import date
from typing import Any

import httpx
from litestar import Litestar
from litestar.testing import TestClient

from gosari.api.weather import WeatherController
from gosari.sources import weather


def provider_row(day: str, index: int = 0) -> dict[str, Any]:
    return {
        "location_id": index,
        "hourly": {
            "time": [f"{day}T11:00", f"{day}T12:00"],
            "temperature_2m": [14, 17.5],
            "precipitation_probability": [0, 73],
            "weather_code": [0, 61],
        },
        "daily": {"time": [day], "temperature_2m_min": [9], "temperature_2m_max": [19]},
    }


def test_forecast_matches_selected_day_and_caches_by_date(monkeypatch) -> None:
    service = weather.WeatherService()
    requested = []
    monkeypatch.setattr(weather, "korea_today", lambda: date(2026, 11, 7))

    async def fetch(selected, historical):
        requested.append((selected, historical))
        return [provider_row(selected.isoformat(), i) for i in range(len(weather.JEJU_LOCATIONS))]

    monkeypatch.setattr(service, "_fetch", fetch)
    first = asyncio.run(service.get(date(2026, 11, 8)))
    assert first.status == "complete"
    assert first.locations[0].temperature_c == 17.5
    assert first.locations[0].precipitation_probability == 73
    assert first.locations[0].condition == "rain"
    assert first.locations[0].forecast_at == "2026-11-08T12:00+09:00"
    assert first.locations[0].temperature_min_c == 9
    assert first.locations[0].temperature_max_c == 19
    first.locations[0].temperature_c = 100
    cached = asyncio.run(service.get(date(2026, 11, 8)))
    assert cached.locations[0].temperature_c == 17.5
    assert len(requested) == 1
    next_day = asyncio.run(service.get(date(2026, 11, 9)))
    assert next_day.date == "2026-11-09"
    assert len(requested) == 2


def test_historical_values_have_no_precipitation_probability(monkeypatch) -> None:
    service = weather.WeatherService()
    monkeypatch.setattr(weather, "korea_today", lambda: date(2026, 11, 7))

    async def fetch(selected, historical):
        assert historical
        return [provider_row(selected.isoformat(), i) for i in range(len(weather.JEJU_LOCATIONS))]

    monkeypatch.setattr(service, "_fetch", fetch)
    response = asyncio.run(service.get(date(2024, 4, 12)))
    assert response.kind == "historical"
    assert response.status == "complete"
    assert all(point.precipitation_probability is None for point in response.locations)


def test_missing_time_is_not_replaced_with_another_days_values(monkeypatch) -> None:
    service = weather.WeatherService()

    async def fetch(selected, historical):
        return [provider_row("2020-01-01")]

    monkeypatch.setattr(service, "_fetch", fetch)
    response = asyncio.run(service.get(date(2026, 11, 8)))
    assert response.status == "unavailable"
    assert all(point.temperature_c is None for point in response.locations)


def test_partial_location_response_preserves_other_missing_locations(monkeypatch) -> None:
    service = weather.WeatherService()
    monkeypatch.setattr(weather, "korea_today", lambda: date(2026, 11, 7))

    async def fetch(selected, historical):
        return [provider_row(selected.isoformat(), 3)]

    monkeypatch.setattr(service, "_fetch", fetch)
    response = asyncio.run(service.get(date(2026, 11, 8)))
    assert response.status == "partial"
    assert response.locations[3].temperature_c == 17.5
    assert response.locations[0].temperature_c is None
    assert len(response.locations) == 12


def test_timeout_does_not_return_fabricated_values(monkeypatch) -> None:
    service = weather.WeatherService()

    async def fetch(selected, historical):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(service, "_fetch", fetch)
    response = asyncio.run(service.get(date(2026, 11, 8)))
    assert response.status == "unavailable"
    assert response.updated_at is None
    assert all(
        point.temperature_c is None and point.condition == "unknown" for point in response.locations
    )


def test_weather_route_validates_dates_and_serializes_contract(monkeypatch) -> None:
    monkeypatch.setattr(weather, "korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr("gosari.api.weather.korea_today", lambda: date(2026, 11, 7))

    async def fetch(selected, historical):
        return [provider_row(selected.isoformat(), i) for i in range(len(weather.JEJU_LOCATIONS))]

    monkeypatch.setattr(weather.weather_service, "_fetch", fetch)
    with TestClient(Litestar(route_handlers=[WeatherController])) as client:
        invalid = client.get("/weather/?date=not-a-date")
        assert invalid.status_code == 400
        assert client.get("/weather/?date=2026-11-23").status_code == 400
        valid = client.get("/weather/?date=2026-11-08")
        assert valid.status_code == 200
        assert valid.json()["date"] == "2026-11-08"
        assert valid.json()["source"] == "Open-Meteo"
        assert len(valid.json()["locations"]) == 12
