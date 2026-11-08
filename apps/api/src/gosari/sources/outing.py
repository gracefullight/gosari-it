"""나들이 후보 비교 — 기상청 단기예보를 우선 쓰고 Open-Meteo는 폴백·최근 맥락으로 쓴다.

기획서 Ⅳ-1: 후보 일정의 예보는 기상청 getVilageFcst(공공데이터포털)로 비교하고, 최근
시계열(강수·기온 맥락)과 키·범위 밖 폴백은 공개 모델 자료(Open-Meteo)를 그 종류대로 표시한다.
"""

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from gosari.config import Settings, get_settings
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest, json_hash, now_utc
from gosari.sources.live import KmaAdapter, TransmissionGate
from gosari.sources.observations import kma_grid
from gosari.sources.weather import korea_today, weather_condition

KOREA = ZoneInfo("Asia/Seoul")
# 단기예보 발표시각(KST). 발표 후 제공까지 약 10분이 걸린다.
KMA_VILAGE_BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
KMA_VILAGE_RANGE_DAYS = 3
KMA_VILAGE_SOURCE = "기상청 단기예보"
KMA_VILAGE_SOURCE_URL = "https://www.data.go.kr/data/15084084/openapi.do"
OPEN_METEO_SOURCE = "Open-Meteo"


def korea_now() -> datetime:
    return datetime.now(KOREA)


def kma_vilage_base(now: datetime) -> datetime:
    """가장 최근에 제공되는 단기예보 발표시각(KST)."""
    local = now.astimezone(KOREA) - timedelta(minutes=10)
    hours = [hour for hour in KMA_VILAGE_BASE_HOURS if hour <= local.hour]
    if hours:
        return local.replace(hour=hours[-1], minute=0, second=0, microsecond=0)
    previous = local - timedelta(days=1)
    return previous.replace(hour=KMA_VILAGE_BASE_HOURS[-1], minute=0, second=0, microsecond=0)


def parse_kma_precipitation(raw: Any) -> float | None:
    """PCP 범주값. '강수없음'→0.0, '1.0mm'→1.0. 구간·미만·이상 표현은 수치로 바꾸지 않는다."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in ("강수없음", "0", "0.0"):
        return 0.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)mm", text)
    return float(match.group(1)) if match else None


def kma_condition(sky: float | None, pty: float | None) -> str:
    """SKY 1 맑음·3 구름많음·4 흐림. PTY 1·2·4·5·6 비 계열, 3·7 눈 계열."""
    if pty in (1, 2, 4, 5, 6):
        return "rain"
    if pty in (3, 7):
        return "snow"
    if sky == 1:
        return "clear"
    if sky in (3, 4):
        return "cloudy"
    return "unknown"


def fetch_kma_outing_forecast(
    latitude: float,
    longitude: float,
    selected: date,
    hour: str,
    settings: Settings,
    checkpoint: Callable[[], None],
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """후보 시각의 기상청 단기예보. 키가 없거나 발표 범위 밖이면 None(폴백 대상)을 돌려준다."""
    if not settings.kma_service_key:
        return None
    base = kma_vilage_base(now or korea_now())
    target = datetime.combine(selected, time.fromisoformat(hour), tzinfo=KOREA)
    if target <= base or (target.date() - base.date()).days > KMA_VILAGE_RANGE_DAYS:
        return None
    nx, ny = kma_grid(latitude, longitude)
    adapter = KmaAdapter(TransmissionGate(settings, checkpoint=checkpoint), settings)
    rows, manifest = adapter.vilage_forecast(nx, ny, base.date(), base.strftime("%H%M"))
    key = f"{selected:%Y%m%d} {hour.replace(':', '')}"
    values = {row.get("category"): row.get("value") for row in rows if row.get("target_at") == key}
    if not values or values.get("TMP") is None:
        return None

    def number(category: str) -> float | None:
        raw = values.get(category)
        try:
            return float(raw) if raw is not None else None
        except TypeError, ValueError:
            return None

    target_at = f"{selected.isoformat()}T{hour}+09:00"
    manifest.requested_scope = {"target_at": target_at}
    manifest.fetched_scope = {"target_at": target_at, "row_count": len(rows)}
    manifest.observed_period = {"published_at": base.isoformat(), "target_at": target_at}
    wind_ms = number("WSD")
    precipitation_text = values.get("PCP")
    return {
        "target_at": target_at,
        "published_at": base.isoformat(),
        "publication_time_status": "provided",
        "fetched_at": manifest.fetched_at.isoformat() if manifest.fetched_at else None,
        "temperature_c": number("TMP"),
        "wind_speed_kmh": round(wind_ms * 3.6, 1) if wind_ms is not None else None,
        "precipitation_mm": parse_kma_precipitation(precipitation_text),
        "precipitation_text": str(precipitation_text) if precipitation_text is not None else None,
        "precipitation_probability": number("POP"),
        "condition": kma_condition(number("SKY"), number("PTY")),
        "kind": "forecast",
        "source": KMA_VILAGE_SOURCE,
        "source_id": "kma_vilage",
        "source_url": KMA_VILAGE_SOURCE_URL,
        "forecast_grid": f"{nx},{ny}",
        "recent_context": [],
        "recent_context_type": None,
        "source_manifest": manifest.to_dict(),
    }


def fetch_outing_weather(
    latitude: float, longitude: float, selected: date, hour: str
) -> dict[str, Any]:
    today = korea_today()
    historical = selected < today
    recent_end = min(selected - timedelta(days=1), today - timedelta(days=1))
    recent_start = recent_end - timedelta(days=6)
    start = min(selected, recent_start)
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        if historical
        else "https://api.open-meteo.com/v1/forecast"
    )
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start.isoformat(),
        "end_date": selected.isoformat(),
        "timezone": "Asia/Seoul",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "hourly": "temperature_2m,weather_code,wind_speed_10m,precipitation"
        + ("" if historical else ",precipitation_probability"),
        "daily": "temperature_2m_mean,precipitation_sum",
    }
    try:
        data, digest = TransmissionGate(get_settings()).get_json(url, params, timeout=12.0)
        target = f"{selected.isoformat()}T{hour}"
        hourly = data["hourly"]
        index = hourly["time"].index(target)
        manifest = SourceManifest(
            source_id="open_meteo",
            dataset_id="archive" if historical else "forecast",
            operation="hourly_weather",
            sanitized_parameters=params,
            requested_scope={"target_at": target + "+09:00"},
            fetched_scope={"target_at": target + "+09:00", "hourly_count": len(hourly["time"])},
            returned_count=len(hourly["time"]),
            fetched_at=now_utc(),
            observed_period={"start": start.isoformat(), "end": selected.isoformat()},
            content_hash=digest,
            source_mode="fetched",
        )

        def value(key: str) -> float | None:
            row = hourly.get(key, [])
            val = row[index] if index < len(row) else None
            return float(val) if isinstance(val, (int, float)) else None

        daily = data.get("daily", {})
        periods = []
        for window in (3, 7):
            begin = recent_end - timedelta(days=window - 1)
            records = [
                i
                for i, day in enumerate(daily.get("time", []))
                if begin.isoformat() <= day <= recent_end.isoformat()
            ]
            rain = [
                daily["precipitation_sum"][i]
                for i in records
                if daily.get("precipitation_sum", [])[i] is not None
            ]
            temp = [
                daily["temperature_2m_mean"][i]
                for i in records
                if daily.get("temperature_2m_mean", [])[i] is not None
            ]
            periods.append(
                {
                    "days": window,
                    "start": begin.isoformat(),
                    "end": recent_end.isoformat(),
                    "total_rain_mm": round(sum(rain), 1) if len(rain) == window else None,
                    "average_temperature_c": round(sum(temp) / len(temp), 1)
                    if len(temp) == window
                    else None,
                    "rain_valid_days": len(rain),
                    "temperature_valid_days": len(temp),
                }
            )
        return {
            "target_at": target + "+09:00",
            "published_at": None,
            "publication_time_status": "not_provided",
            "fetched_at": manifest.fetched_at.isoformat() if manifest.fetched_at else None,
            "temperature_c": value("temperature_2m"),
            "wind_speed_kmh": value("wind_speed_10m"),
            "precipitation_mm": value("precipitation"),
            "precipitation_probability": None if historical else value("precipitation_probability"),
            "condition": weather_condition(value("weather_code")),
            "kind": "historical" if historical else "forecast",
            "source": OPEN_METEO_SOURCE,
            "source_id": "open_meteo",
            "source_url": "https://open-meteo.com/",
            "recent_context": periods,
            "recent_context_type": "model_weather",
            "source_manifest": manifest.to_dict(),
        }
    except httpx.HTTPError, ValueError, KeyError, TypeError, IndexError:
        raise GosariError("UPSTREAM_FAILED") from None


def candidate_weather(
    place: tuple[str, str, float, float],
    day: date,
    hour: str,
    settings: Settings,
    checkpoint: Callable[[], None],
    *,
    use_kma: bool,
) -> tuple[dict[str, Any], list[str]]:
    """후보 한 건의 날씨. 기상청 예보가 되면 그 값을 쓰고 Open-Meteo는 최근 맥락·폴백으로 쓴다."""
    warnings: list[str] = []
    official: dict[str, Any] | None = None
    if use_kma and settings.kma_service_key:
        try:
            official = fetch_kma_outing_forecast(
                place[2], place[3], day, hour, settings, checkpoint
            )
        except GosariError as exc:
            if exc.code in ("CANCELLED", "DEADLINE_EXCEEDED"):
                raise
            warnings.append(f"{place[1]} 기상청 단기예보 연결 불가 · Open-Meteo 모델 예보로 비교")
        checkpoint()
    try:
        model = fetch_outing_weather(place[2], place[3], day, hour)
    except GosariError:
        if official is None:
            raise
        model = None
        warnings.append(f"{place[1]} 최근 강수·기온 맥락(Open-Meteo) 조회 실패")
    if official is None:
        assert model is not None
        return model, warnings
    merged = {
        **official,
        "recent_context": model["recent_context"] if model else [],
        "recent_context_type": "model_weather" if model else None,
        "recent_context_source": OPEN_METEO_SOURCE if model else None,
        "recent_context_missing": model is None,
        "fallback_source": None,
    }
    manifests = [official["source_manifest"]]
    if model and model.get("source_manifest"):
        manifests.append(model["source_manifest"])
    merged["source_manifests"] = manifests
    return merged, warnings


def compare_outings(
    spec: dict[str, Any],
    request_id: str,
    checkpoint: Callable[[], None],
    settings: Settings | None = None,
) -> ResultEnvelope:
    from gosari.agent.analysis import get_evidence_store
    from gosari.sources.locations import resolve_public_place, station_catalog

    settings = settings or get_settings()
    sources = spec.get("source_ids") or []
    use_kma = not sources or "kma_vilage" in sources
    cards: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    warnings: list[str] = []
    incomplete = False
    preferred = spec.get("preferred_elements") or ["low_rain", "mild_temperature", "low_wind"]
    for index, candidate in enumerate(spec.get("candidates", [])):
        checkpoint()
        id_ = f"cand-{index + 1}"
        place = None
        try:
            place = resolve_public_place(
                candidate.get("location_id") or candidate.get("station_name") or ""
            )
            day = date.fromisoformat(
                candidate.get("date") or candidate.get("target_date") or korea_today().isoformat()
            )
            hour = candidate.get("time_slot") or candidate.get("target_time_window") or "12:00"
            hour = {"오전": "09:00", "오후": "15:00"}.get(hour, hour)
            if day > korea_today() + timedelta(days=15):
                raise GosariError("INVALID_INPUT", {"reason": "FORECAST_RANGE"})
            values, notes = candidate_weather(
                place, day, hour, settings, checkpoint, use_kma=use_kma
            )
            warnings.extend(notes)
            checkpoint()
            if values["temperature_c"] is None:
                raise GosariError("UPSTREAM_FAILED")
            required = ["temperature_c", "wind_speed_kmh"]
            if values.get("precipitation_text") is None:
                required.append("precipitation_mm")
            if values["kind"] == "forecast":
                required.append("precipitation_probability")
            incomplete = incomplete or any(values.get(key) is None for key in required)
            incomplete = incomplete or bool(values.get("recent_context_missing"))
            incomplete = incomplete or any(
                context.get("total_rain_mm") is None or context.get("average_temperature_c") is None
                for context in values["recent_context"]
            )
            manifests.extend(
                values.get("source_manifests")
                or [
                    values.get("source_manifest")
                    or {
                        "source_id": values.get("source_id", "open_meteo"),
                        "operation": "hourly_weather",
                        "content_hash": json_hash(values),
                        "hash_basis": "normalized_weather_values",
                        "observed_period": {"target_at": values["target_at"]},
                    }
                ]
            )
            reasons = [f"기온 {values['temperature_c']}℃"]
            if values["precipitation_probability"] is not None:
                reasons.append(f"강수확률 {values['precipitation_probability']:g}%")
            elif values.get("precipitation_text"):
                reasons.append(f"강수 {values['precipitation_text']}")
            if values["wind_speed_kmh"] is not None:
                reasons.append(f"바람 {values['wind_speed_kmh']:g}km/h")
            for context in values["recent_context"]:
                if context["total_rain_mm"] is not None:
                    description = f"최근 {context['days']}일 강수 {context['total_rain_mm']:g}mm"
                    if context["average_temperature_c"] is not None:
                        description += f" · 평균 {context['average_temperature_c']}℃"
                    reasons.append(description)
            cards.append(
                {
                    "candidate_id": id_,
                    "station_name": place[1],
                    "location_id": place[0],
                    "latitude": place[2],
                    "longitude": place[3],
                    **(
                        {
                            key: value
                            for key, value in station_catalog()[place[0]].items()
                            if key.startswith("coordinate_") or key == "altitude_m"
                        }
                        if place[0] in station_catalog()
                        else {}
                    ),
                    "target_date": day.isoformat(),
                    "target_time_window": hour,
                    "weather": values,
                    "recent_context": values["recent_context"],
                    "comparison_reasons": reasons,
                    "current_observation": None,
                    "forecast_status": {
                        "published_at": values["published_at"],
                        "target_at": values["target_at"],
                        "status": "historical" if values["kind"] == "historical" else "available",
                        "note": " · ".join(reasons[:3]),
                        "source": values["source"],
                        "publication_time_status": values.get(
                            "publication_time_status", "not_provided"
                        ),
                    },
                }
            )
        except GosariError as exc:
            checkpoint()
            failed.append(
                {
                    "candidate_id": id_,
                    "station_name": place[1] if place else "선택 지역",
                    "message": exc.safe_message,
                    "reason": exc.extra.get("reason", exc.code),
                    "target_date": candidate.get("date") or candidate.get("target_date"),
                    "target_time_window": candidate.get("time_slot")
                    or candidate.get("target_time_window"),
                }
            )

    def ranking(card: dict[str, Any]) -> tuple[float, ...]:
        values = card["weather"]
        metrics = {
            "low_rain": values.get("precipitation_probability")
            if values.get("precipitation_probability") is not None
            else values.get("precipitation_mm"),
            "mild_temperature": abs(values["temperature_c"] - 20),
            "low_wind": values.get("wind_speed_kmh"),
        }
        ranked_values: list[float] = []
        for preference in preferred:
            metric = metrics.get(preference)
            ranked_values.append(float(metric) if metric is not None else 999.0)
        return tuple(ranked_values)

    ranked = sorted(cards, key=ranking)
    for rank, card in enumerate(ranked, 1):
        card["rank"] = rank
    checklist = ["장화·장갑·고사리 가방", "식수·간식", "휴대전화·동행자 연락 확인"]
    if any(
        (c["weather"].get("precipitation_probability") or 0) >= 30
        or (c["weather"].get("precipitation_mm") or 0) > 0
        for c in cards
    ):
        checklist.append("비옷·여벌 양말")
    if any(c["weather"]["temperature_c"] < 15 for c in cards):
        checklist.append("보온 겉옷")
    if any((c["weather"].get("wind_speed_kmh") or 0) >= 20 for c in cards):
        checklist.append("방풍 겉옷")
    published = [card["weather"].get("published_at") for card in cards]
    publication_time_status = (
        "provided" if cards and all(published) else "mixed" if any(published) else "not_provided"
    )
    result = {
        "candidates": cards,
        "failed_candidates": failed,
        "preferred_elements": preferred,
        "ranked_candidate_ids": [c["candidate_id"] for c in ranked],
        "preparation_checklist": checklist,
        "forecast_sources": sorted({card["weather"]["source"] for card in cards}),
    }
    requested_scope = {"candidates": spec.get("candidates", []), "preferred_elements": preferred}
    effective_scope = {
        "matched_candidates": len(cards),
        "failed_candidates": failed,
        "candidate_ids": [card["candidate_id"] for card in cards],
        "forecast_sources": result["forecast_sources"],
    }
    evidence_id = get_evidence_store().put(
        {
            "public_query_spec": spec,
            "created_at": now_utc().isoformat(),
            "source_manifests": manifests,
            "requested_scope": requested_scope,
            "effective_scope": effective_scope,
            "formula_version": "outing-compare-v2",
            "result_values": result,
            "input_hashes": [manifest.get("content_hash") for manifest in manifests],
            "warnings": warnings,
            "units": {
                "temperature_c": "℃",
                "precipitation_probability": "%",
                "wind_speed_kmh": "km/h",
                "precipitation_mm": "mm",
            },
        }
    )
    return ResultEnvelope(
        request_id=request_id,
        source_mode="fetched",
        fetched_at=now_utc(),
        data_status="partial"
        if cards and (failed or incomplete)
        else "complete"
        if cards
        else "unavailable",
        requested_scope=requested_scope,
        effective_scope=effective_scope,
        observed_period={
            "target_times": [card["weather"]["target_at"] for card in cards],
            "published_at": sorted({value for value in published if value}) or None,
            "publication_time_status": publication_time_status,
        },
        result=result,
        evidence_ids=[evidence_id],
        warnings=warnings,
    )
