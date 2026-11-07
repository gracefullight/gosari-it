"""기관 관측 취득과 명시적인 공개 재분석 대체 경로."""

import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from gosari.config import Settings
from gosari.domain import SourceMode
from gosari.domain.errors import GosariError
from gosari.quality import interpret_numeric
from gosari.quality.calculation import Observation
from gosari.sources import SourceManifest, content_hash, now_utc
from gosari.sources.live import JejuHubAdapter, KmaAdapter, TransmissionGate
from gosari.sources.weather import JEJU_LOCATIONS


def kma_grid(latitude: float, longitude: float) -> tuple[int, int]:
    """기상청 동네예보 5km Lambert 격자. 공개 대표 좌표만 전달한다."""
    first, second = math.radians(30), math.radians(60)
    exponent = math.log(math.cos(first) / math.cos(second)) / math.log(
        math.tan(math.pi / 4 + second / 2) / math.tan(math.pi / 4 + first / 2)
    )
    scale = math.tan(math.pi / 4 + first / 2) ** exponent * math.cos(first) / exponent
    radius = 6371.00877 / 5 * scale
    origin = radius / math.tan(math.pi / 4 + math.radians(38) / 2) ** exponent
    projected = radius / math.tan(math.pi / 4 + math.radians(latitude) / 2) ** exponent
    angle = math.radians(longitude - 126) * exponent
    return (
        math.floor(projected * math.sin(angle) + 43.5),
        math.floor(origin - projected * math.cos(angle) + 136.5),
    )


def current_grid_observations(
    settings: Settings,
    checkpoint: Callable[[], None],
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[SourceManifest], list[str]]:
    """매시 정시의 실황값. 제공 지연 40분을 고려하며 RN1은 일강수로 바꾸지 않는다."""
    base = (
        (now or datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul"))
        - timedelta(minutes=40)
    ).replace(minute=0, second=0, microsecond=0)
    adapter = KmaAdapter(TransmissionGate(settings, checkpoint=checkpoint), settings)

    def fetch(place: tuple[str, str, float, float]) -> tuple[dict[str, Any], SourceManifest | None]:
        checkpoint()
        nx, ny = kma_grid(place[2], place[3])
        station: dict[str, Any] = {
            "station_name": place[1],
            "station_code": place[0],
            "latitude": place[2],
            "longitude": place[3],
            "grid": {"nx": nx, "ny": ny},
            "temperature_c": None,
            "day_rain_mm": None,
            "rain_1h_mm": None,
            "wind_speed_ms": None,
            "precipitation_type": None,
            "observation_time": None,
            "source": "기상청 초단기실황",
            "observation_type": "grid_observation",
            "accumulation_window": "1h",
        }
        try:
            items, manifest = adapter.current_grid(nx, ny, base.date(), base.strftime("%H%M"))
            values = {item.get("category"): item.get("obsrValue") for item in items}
            for category, field in (
                ("T1H", "temperature_c"),
                ("RN1", "rain_1h_mm"),
                ("WSD", "wind_speed_ms"),
                ("PTY", "precipitation_type"),
            ):
                raw = values.get(category)
                if raw is None:
                    continue
                try:
                    value = float(raw)
                except TypeError, ValueError:
                    continue
                if math.isfinite(value) and (value > -90 if category == "T1H" else value >= 0):
                    station[field] = value
            station["observation_time"] = base.isoformat()
            return station, manifest
        except GosariError as error:
            checkpoint()
            if error.code in ("CANCELLED", "DEADLINE_EXCEEDED"):
                raise
            return station, None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(fetch, JEJU_LOCATIONS))
    checkpoint()
    stations = [row for row, _ in results]
    manifests = [manifest for _, manifest in results if manifest is not None]
    if not manifests:
        raise GosariError("UPSTREAM_FAILED")
    incomplete = any(
        any(
            row[field] is None
            for field in ("temperature_c", "rain_1h_mm", "wind_speed_ms", "precipitation_type")
        )
        for row in stations
    )
    return stations, manifests, ["일부 지역 실황값 없음"] if incomplete else []


def current_public_weather() -> tuple[list[dict[str, Any]], str]:
    """현재 모델 기상값. 실측 관측소 값으로 표시하지 않는다."""
    try:
        response = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": ",".join(str(row[2]) for row in JEJU_LOCATIONS),
                "longitude": ",".join(str(row[3]) for row in JEJU_LOCATIONS),
                "current": "temperature_2m,precipitation",
                "timezone": "Asia/Seoul",
            },
            timeout=12.0,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != len(JEJU_LOCATIONS):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        stations = []
        for place, row in zip(JEJU_LOCATIONS, rows, strict=True):
            current = row.get("current", {})
            stations.append(
                {
                    "station_name": place[1],
                    "station_code": place[0],
                    "temperature_c": current.get("temperature_2m"),
                    "day_rain_mm": None,
                    "current_precipitation_mm": current.get("precipitation"),
                    "observation_time": current.get("time"),
                    "source": "Open-Meteo",
                    "observation_type": "model_estimate",
                }
            )
        return stations, content_hash(response.content)
    except httpx.HTTPError, ValueError, KeyError, TypeError:
        raise GosariError("UPSTREAM_FAILED") from None


def archive_observations(
    name: str, start: date, end: date
) -> tuple[list[Observation], SourceManifest]:
    places = {row[1]: row[2:] for row in JEJU_LOCATIONS}
    places.update(
        {"제주": (33.4996, 126.5312), "제주(184)": (33.4996, 126.5312), "선흘": (33.456, 126.705)}
    )
    if name not in places:
        raise GosariError("STATION_AMBIGUOUS")
    lat, lon = places[name]
    try:
        response = httpx.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "daily": "temperature_2m_mean,precipitation_sum",
                "timezone": "Asia/Seoul",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        daily = response.json()["daily"]
        records = []
        for index, day in enumerate(daily["time"]):
            for element, key in (
                ("daily_rainfall", "precipitation_sum"),
                ("average_temperature", "temperature_2m_mean"),
            ):
                raw = daily[key][index]
                parsed = interpret_numeric(str(raw) if raw is not None else None)
                records.append(
                    Observation(
                        source_id="open_meteo",
                        station_key=name,
                        observation_date=date.fromisoformat(day),
                        element=element,
                        raw=parsed.raw,
                        numeric=parsed.numeric,
                        value_state=parsed.state,
                    )
                )
        manifest = SourceManifest(
            source_id="open_meteo",
            dataset_id="archive",
            operation="daily_reanalysis",
            sanitized_parameters={
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "region": name,
            },
            returned_count=len(records),
            fetched_at=now_utc(),
            content_hash=content_hash(response.content),
            source_mode="fetched",
        )
        return records, manifest
    except httpx.HTTPError, KeyError, IndexError, ValueError, TypeError:
        raise GosariError("UPSTREAM_FAILED") from None


def live_observations(
    spec: dict[str, Any], settings: Settings, checkpoint: Callable[[], None]
) -> tuple[list[Observation], SourceMode, list[SourceManifest], list[str]]:
    from dataclasses import replace

    selections = spec.get("station_selections", [])
    if not selections:
        raise GosariError("STATION_AMBIGUOUS")
    records: list[Observation] = []
    manifests: list[SourceManifest] = []
    warnings: list[str] = []
    completed_scope: list[dict[str, Any]] = []

    def checked() -> None:
        try:
            checkpoint()
        except GosariError as error:
            if completed_scope:
                error.extra["fetched_scope"] = list(completed_scope)
            raise

    gate = TransmissionGate(settings, checkpoint=checked)
    jeju = JejuHubAdapter(gate, settings)
    kma = KmaAdapter(gate, settings)
    denied: set[str] = set()
    for selection in selections:
        source = selection.get("source_id", "jeju_579")
        name = selection.get("station_name") or "제주(184)"
        for year in spec.get("years", []):
            checked()
            try:
                start = date.fromisoformat(f"{year}-{spec.get('month_day_start', '04-01')}")
                end = date.fromisoformat(f"{year}-{spec.get('month_day_end', '05-31')}")
            except ValueError:
                import calendar

                if spec.get("month_day_start") == spec.get(
                    "month_day_end"
                ) == "02-29" and not calendar.isleap(year):
                    continue
                raise GosariError(
                    "INVALID_INPUT", {"fields": ["month_day_start", "month_day_end"]}
                ) from None
            if end < start:
                raise GosariError("INVALID_INPUT", {"fields": ["month_day_start", "month_day_end"]})
            try:
                if source in denied:
                    raise GosariError("CAPABILITY_DISABLED")
                if source == "kma_asos":
                    station_id = str(
                        selection.get("station_id") or selection.get("station_code") or "184"
                    )
                    rows, manifest = kma.asos_daily(
                        station_id,
                        start,
                        end,
                    )
                    suffix = f"({station_id})"
                    station_key = name if name.endswith(suffix) else f"{name}{suffix}"
                    records.extend(replace(row, station_key=station_key) for row in rows)
                    manifests.append(manifest)
                    completed_scope.append(
                        {
                            "source_id": "kma_asos",
                            "station": name,
                            "start": start.isoformat(),
                            "end": end.isoformat(),
                            "returned_count": manifest.returned_count,
                        }
                    )
                else:
                    day = start
                    year_rows: list[Observation] = []
                    year_manifests: list[SourceManifest] = []
                    while day <= end:
                        checked()
                        rows, manifest = jeju.daily_weather(day, name)
                        year_rows.extend(rows)
                        year_manifests.append(manifest)
                        if manifest.failed_scope or manifest.has_more:
                            warning = "일부 날짜·페이지를 불러오지 못했습니다."
                            if warning not in warnings:
                                warnings.append(warning)
                        completed_scope.append(
                            {
                                "source_id": "jeju_579",
                                "station": name,
                                "date": day.isoformat(),
                                "returned_count": manifest.returned_count,
                            }
                        )
                        day += timedelta(days=1)
                    records.extend(year_rows)
                    manifests.extend(year_manifests)
            except GosariError as error:
                checked()
                if error.code in ("BUDGET_EXCEEDED", "JOB_DEADLINE_EXCEEDED", "ACTION_NOT_ALLOWED"):
                    error.extra["fetched_scope"] = list(completed_scope)
                    raise
                if error.code in ("POLICY_BLOCKED", "CAPABILITY_DISABLED"):
                    denied.add(source)
                rows, manifest = archive_observations(name, start, end)
                checked()
                records.extend(rows)
                manifests.append(manifest)
                warning = "기관 연결 불가 · Open-Meteo 과거 날씨로 비교"
                if warning not in warnings:
                    warnings.append(warning)
    return records, SourceMode.FETCHED, manifests, warnings
