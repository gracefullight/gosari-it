"""제주 대표 지역의 공개 날씨. 예보와 과거 재분석 자료를 구분한다."""

import math
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

KOREA = ZoneInfo("Asia/Seoul")

# 읍면동 중심 부근의 대표 좌표이며 관측소 또는 개인 채취지 좌표가 아니다.
JEJU_LOCATIONS = (
    ("jeju", "제주시", 33.4996, 126.5312),
    ("aewol", "애월", 33.4620, 126.3290),
    ("hallim", "한림", 33.4100, 126.2670),
    ("hangyeong", "한경", 33.3500, 126.1840),
    ("daejeong", "대정", 33.2260, 126.2520),
    ("andeok", "안덕", 33.2570, 126.3510),
    ("seogwipo", "서귀포", 33.2541, 126.5601),
    ("namwon", "남원", 33.2790, 126.7200),
    ("pyoseon", "표선", 33.3260, 126.8310),
    ("seongsan", "성산", 33.4420, 126.9100),
    ("gujwa", "구좌", 33.5220, 126.8520),
    ("jocheon", "조천", 33.5340, 126.6340),
)


class WeatherLocation(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    temperature_c: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_probability: float | None = None
    condition: Literal["clear", "cloudy", "rain", "snow", "unknown"] = "unknown"
    forecast_at: str


class WeatherResponse(BaseModel):
    evidence_ids: list[str] = Field(default_factory=list)
    date: str
    updated_at: str | None
    locations: list[WeatherLocation]
    source: str = "Open-Meteo"
    source_url: str = "https://open-meteo.com/"
    kind: Literal["forecast", "historical"]
    status: Literal["complete", "partial", "unavailable"]
    min_date: str
    max_date: str


def korea_today() -> date:
    return datetime.now(KOREA).date()


def weather_condition(code: float | None) -> Literal["clear", "cloudy", "rain", "snow", "unknown"]:
    if code is None:
        return "unknown"
    if code in (0, 1):
        return "clear"
    if code in (2, 3, 45, 48):
        return "cloudy"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        return "rain"
    return "unknown"


def _number(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        else None
    )


def _at(values: dict[str, Any], key: str, index: int) -> float | None:
    series = values.get(key)
    if not isinstance(series, list) or index >= len(series):
        return None
    return _number(series[index])


class WeatherService:
    """한 번의 다중 좌표 요청, 5분 캐시, 실패 시 수치 생성 없이 빈 값 반환."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, WeatherResponse]] = {}

    async def _fetch(self, selected: date, historical: bool) -> Any:
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            if historical
            else "https://api.open-meteo.com/v1/forecast"
        )
        hourly = "temperature_2m,weather_code"
        if not historical:
            hourly += ",precipitation_probability"
        params = {
            "latitude": ",".join(str(item[2]) for item in JEJU_LOCATIONS),
            "longitude": ",".join(str(item[3]) for item in JEJU_LOCATIONS),
            "start_date": selected.isoformat(),
            "end_date": selected.isoformat(),
            "hourly": hourly,
            "daily": "temperature_2m_min,temperature_2m_max",
            "timezone": "Asia/Seoul",
        }
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=False) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def get(self, selected: date) -> WeatherResponse:
        key = selected.isoformat()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1].model_copy(deep=True)
        historical = selected < korea_today()
        kind: Literal["forecast", "historical"] = "historical" if historical else "forecast"
        target_time = f"{key}T12:00"
        locations = [
            WeatherLocation(
                id=id_, name=name, latitude=lat, longitude=lon, forecast_at=f"{target_time}+09:00"
            )
            for id_, name, lat, lon in JEJU_LOCATIONS
        ]
        fetched = False
        try:
            payload = await self._fetch(selected, historical)
            rows = payload if isinstance(payload, list) else [payload]
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or row.get("error"):
                    continue
                # Multi-location responses carry location_id except the first item.
                location_index = row.get("location_id", index)
                if not isinstance(location_index, int) or not 0 <= location_index < len(locations):
                    continue
                hourly = row.get("hourly", {})
                if not isinstance(hourly, dict):
                    continue
                times = hourly.get("time", [])
                if not isinstance(times, list) or target_time not in times:
                    continue
                hour_index = times.index(target_time)
                point = locations[location_index]
                point.temperature_c = _at(hourly, "temperature_2m", hour_index)
                probability = _at(hourly, "precipitation_probability", hour_index)
                point.precipitation_probability = (
                    probability
                    if not historical and probability is not None and 0 <= probability <= 100
                    else None
                )
                point.condition = weather_condition(_at(hourly, "weather_code", hour_index))
                daily = row.get("daily", {})
                if isinstance(daily, dict) and key in daily.get("time", []):
                    day_index = daily["time"].index(key)
                    point.temperature_min_c = _at(daily, "temperature_2m_min", day_index)
                    point.temperature_max_c = _at(daily, "temperature_2m_max", day_index)
            fetched = True
        except httpx.HTTPError, ValueError, TypeError, KeyError:
            # No replay or generated weather values are substituted for provider failures.
            pass
        complete = sum(
            point.temperature_c is not None
            and point.condition != "unknown"
            and (historical or point.precipitation_probability is not None)
            for point in locations
        )
        available = any(
            point.temperature_c is not None or point.condition != "unknown" for point in locations
        )
        response = WeatherResponse(
            date=key,
            updated_at=datetime.now(UTC).isoformat() if fetched else None,
            locations=locations,
            kind=kind,
            status="complete"
            if complete == len(locations)
            else "partial"
            if available
            else "unavailable",
            min_date="1940-01-01",
            max_date=(korea_today() + timedelta(days=15)).isoformat(),
        )
        if response.status != "unavailable":
            if len(self._cache) >= 64:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic() + 300, response)
        return response.model_copy(deep=True)


weather_service = WeatherService()
