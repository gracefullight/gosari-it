"""공개 대표 지역·선택시각의 날씨와 최근 강수/기온 맥락."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx

from gosari.config import get_settings
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest, json_hash, now_utc
from gosari.sources.live import TransmissionGate
from gosari.sources.weather import korea_today, weather_condition


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
            "source": "Open-Meteo",
            "source_url": "https://open-meteo.com/",
            "recent_context": periods,
            "recent_context_type": "model_weather",
            "source_manifest": manifest.to_dict(),
        }
    except httpx.HTTPError, ValueError, KeyError, TypeError, IndexError:
        raise GosariError("UPSTREAM_FAILED") from None


def compare_outings(
    spec: dict[str, Any], request_id: str, checkpoint: Callable[[], None]
) -> ResultEnvelope:
    from gosari.agent.analysis import get_evidence_store
    from gosari.sources.locations import resolve_public_place, station_catalog

    cards: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
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
            values = fetch_outing_weather(place[2], place[3], day, hour)
            checkpoint()
            if values["temperature_c"] is None:
                raise GosariError("UPSTREAM_FAILED")
            required = ["temperature_c", "wind_speed_kmh", "precipitation_mm"]
            if values["kind"] == "forecast":
                required.append("precipitation_probability")
            incomplete = incomplete or any(values.get(key) is None for key in required)
            incomplete = incomplete or any(
                context.get("total_rain_mm") is None or context.get("average_temperature_c") is None
                for context in values["recent_context"]
            )
            manifests.append(
                values.get("source_manifest")
                or {
                    "source_id": "open_meteo",
                    "operation": "hourly_weather",
                    "content_hash": json_hash(values),
                    "hash_basis": "normalized_weather_values",
                    "observed_period": {"target_at": values["target_at"]},
                }
            )
            reasons = [f"기온 {values['temperature_c']}℃"]
            if values["precipitation_probability"] is not None:
                reasons.append(f"강수확률 {values['precipitation_probability']:g}%")
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
    result = {
        "candidates": cards,
        "failed_candidates": failed,
        "preferred_elements": preferred,
        "ranked_candidate_ids": [c["candidate_id"] for c in ranked],
        "preparation_checklist": checklist,
    }
    requested_scope = {"candidates": spec.get("candidates", []), "preferred_elements": preferred}
    effective_scope = {
        "matched_candidates": len(cards),
        "failed_candidates": failed,
        "candidate_ids": [card["candidate_id"] for card in cards],
    }
    evidence_id = get_evidence_store().put(
        {
            "public_query_spec": spec,
            "created_at": now_utc().isoformat(),
            "source_manifests": manifests,
            "requested_scope": requested_scope,
            "effective_scope": effective_scope,
            "formula_version": "outing-compare-v1",
            "result_values": result,
            "input_hashes": [manifest.get("content_hash") for manifest in manifests],
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
            "published_at": None,
            "publication_time_status": "not_provided",
        },
        result=result,
        evidence_ids=[evidence_id],
    )
