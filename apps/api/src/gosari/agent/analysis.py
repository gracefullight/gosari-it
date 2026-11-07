"""공개 분석 모듈 — 결정론 계산·근거 생성. LLM은 설명만 담당한다 (SRS §4.1)."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from gosari.agent.evidence_store import get_evidence_store
from gosari.agent.outing_replay import compare_outings_replay
from gosari.config import Settings, get_settings
from gosari.domain import DataStatus, LinkStatus, RuntimeMode, SourceMode
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.quality.calculation import (
    Observation,
    common_actual_dates,
    common_month_days,
    deduplicate,
    rain_stats,
    temperature_stats,
)
from gosari.sources import SourceManifest, now_utc
from gosari.sources.at import query_settlements
from gosari.sources.links import (
    retail_link_cards,
    retail_sample_cards,
    survey_link_cards,
    survey_sample_cards,
)
from gosari.sources.replay import (
    ReplaySource,
    load_current_observations,
    load_retail_products,
)


class AnalysisEngine:
    def __init__(
        self, settings: Settings | None = None, checkpoint: Callable[[], None] | None = None
    ) -> None:
        self.checkpoint = checkpoint or (lambda: None)
        self.settings = settings or get_settings()
        self.replay = ReplaySource(self.settings.resolved_fixtures_dir)

    @property
    def runtime_mode(self) -> RuntimeMode:
        if self.settings.app_profile == "replay":
            return RuntimeMode.REPLAY
        if self.settings.external_requests_enabled:
            return RuntimeMode.LIVE
        return RuntimeMode.LIMITED

    def run(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        operation = spec["operation"]
        handler = {
            "history_compare": self._history_compare,
            "region_compare": self._region_compare,
            "current_observation": self._current_observation,
            "forecast_compare": self._forecast_compare,
            "outing_compare": self._outing_compare,
            "market_query": self._market_query,
            "survey_link": self._survey_link,
            "retail_lookup": self._retail_lookup,
            "station_search": self._station_search,
        }.get(operation)
        if handler is None:
            raise GosariError("INVALID_INPUT", {"fields": ["operation"]})
        return handler(spec, request_id)

    def _observations_for(
        self, spec: dict[str, Any]
    ) -> tuple[list[Observation], SourceMode, list[SourceManifest], list[str]]:
        """과거 관측은 replay 표본 우선. live는 날짜별 579 호출(예산 내)."""
        stations = [
            s.get("station_name")
            for s in spec.get("station_selections", [])
            if s.get("station_name")
        ]
        if self.runtime_mode != RuntimeMode.LIVE:
            observations = self.replay.all_observations()
            if stations:
                observations = [
                    o
                    for o in observations
                    if o.station_key in stations or o.station_key.partition("(")[0] in stations
                ]
            years = spec.get("years", [])
            start = spec.get("month_day_start")
            end = spec.get("month_day_end")
            if start and end and start > end:
                raise GosariError("INVALID_INPUT", {"fields": ["month_day_start", "month_day_end"]})
            observations = [
                row
                for row in observations
                if (not years or row.observation_date.year in years)
                and (not start or row.observation_date.strftime("%m-%d") >= start)
                and (not end or row.observation_date.strftime("%m-%d") <= end)
            ]
            _, meta = self.replay.seonheul()
            manifest = SourceManifest(
                source_id="jeju_579",
                dataset_id="579",
                operation="replay",
                sanitized_parameters={"station_names": stations},
                content_hash=meta["file_hash"],
                verified_on=meta["verified_on"],
                source_mode="replay",
            )
            warnings = [] if self.runtime_mode == RuntimeMode.REPLAY else ["표본 자료입니다."]
            return observations, SourceMode.REPLAY, [manifest], warnings
        from gosari.sources.observations import live_observations

        return live_observations(spec, self.settings, self.checkpoint)

    def _history_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        stations = spec.get("station_selections", [])
        if len(stations) != 1 or not stations[0].get("station_name"):
            raise GosariError("STATION_AMBIGUOUS")
        station = stations[0]["station_name"]
        station_id = stations[0].get("station_id") or stations[0].get("station_code")
        if stations[0].get("source_id") == "kma_asos" and station_id:
            suffix = f"({station_id})"
            station = station if station.endswith(suffix) else f"{station}{suffix}"
        years = sorted(spec.get("years", []))
        if len(years) < 2:
            raise GosariError("INVALID_INPUT", {"fields": ["years"]})
        observations, source_mode, manifests, warnings = self._observations_for(spec)
        deduped = deduplicate(observations)
        if deduped.conflicts:
            warnings.append(f"값이 다른 관측 자료 {len(deduped.conflicts)}건이 있습니다.")
        elements = spec.get("elements", ["daily_rainfall"])
        result: dict[str, Any] = {}
        for element in elements:
            common, _per_year = common_month_days(deduped.unique, station, years, element)
            element_result: dict[str, Any] = {
                "common_month_days": sorted(common),
                "common_day_count": len(common),
                "per_year": {},
            }
            for year in years:
                if element == "daily_rainfall":
                    stats = rain_stats(deduped.unique, station, year, restrict_month_days=common)
                    element_result["per_year"][str(year)] = {
                        "positive_days": stats.positive_days,
                        "valid_days": stats.valid_days,
                        "ratio": str(stats.ratio) if stats.ratio is not None else None,
                    }
                else:
                    avg, count = temperature_stats(
                        deduped.unique, station, year, restrict_month_days=common
                    )
                    full_avg, full_count = temperature_stats(deduped.unique, station, year)
                    element_result["per_year"][str(year)] = {
                        "average": str(avg) if avg is not None else None,
                        "valid_days": count,
                        "full_period": {
                            "average": str(full_avg) if full_avg is not None else None,
                            "valid_days": full_count,
                        },
                    }
                full = (
                    rain_stats(deduped.unique, station, year)
                    if element == "daily_rainfall"
                    else None
                )
                if full:
                    element_result["per_year"][str(year)]["full_period"] = {
                        "positive_days": full.positive_days,
                        "valid_days": full.valid_days,
                    }
                year_obs = [
                    o
                    for o in deduped.unique
                    if o.station_key == station
                    and o.observation_date.year == year
                    and o.element == element
                ]
                state_counts: dict[str, int] = {}
                for obs in year_obs:
                    st = obs.value_state.value
                    state_counts[st] = state_counts.get(st, 0) + 1
                element_result["per_year"][str(year)]["value_states"] = state_counts
            result[element] = element_result
            if any(key[1] == station and key[3] == element for key, _ in deduped.conflicts):
                element_result["comparison_status"] = "conflict"
                for stats in element_result["per_year"].values():
                    for section in (stats, stats.get("full_period", {})):
                        for field in ("positive_days", "ratio", "average"):
                            if field in section:
                                section[field] = None
        incomplete = any(m.failed_scope or m.has_more for m in manifests)
        if not observations:
            data_status = DataStatus.UNAVAILABLE if incomplete else DataStatus.NO_DATA
        else:
            data_status = DataStatus.PARTIAL if warnings or incomplete else DataStatus.COMPLETE
        if deduped.conflicts:
            data_status = DataStatus.CONFLICT
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [m.to_dict() for m in manifests],
                "effective_scope": {
                    "station": station,
                    "years": years,
                    "elements": elements,
                },
                "formula_version": "calc-v1",
                "result_values": result,
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=data_status,
            source_mode=source_mode,
            requested_scope={
                "years": years,
                "month_days": [spec.get("month_day_start"), spec.get("month_day_end")],
            },
            effective_scope={
                "station": station,
                "common_month_days": result.get("daily_rainfall", {}).get("common_day_count"),
            },
            observed_period={"years": years},
            verified_on=manifests[0].verified_on if manifests else None,
            result=result,
            evidence_ids=[evidence_id],
            warnings=warnings,
        )

    def _region_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        stations = []
        for selection in spec.get("station_selections", []):
            name = selection.get("station_name")
            if not name:
                continue
            station_id = selection.get("station_id") or selection.get("station_code")
            if selection.get("source_id") == "kma_asos" and station_id:
                suffix = f"({station_id})"
                stations.append(name if name.endswith(suffix) else f"{name}{suffix}")
            else:
                stations.append(name)
        if len(stations) < 2:
            raise GosariError("INVALID_INPUT", {"fields": ["station_selections"]})
        observations, source_mode, manifests, warnings = self._observations_for(spec)
        deduped = deduplicate(observations)
        if deduped.conflicts:
            warnings.append(f"값이 다른 관측 자료 {len(deduped.conflicts)}건이 있습니다.")
        elements = spec.get("elements", ["daily_rainfall"])
        result: dict[str, Any] = {}
        for element in elements:
            common = common_actual_dates(deduped.unique, stations, element)
            per_station: dict[str, Any] = {}
            for station in stations:
                all_station_obs = [
                    o for o in deduped.unique if o.station_key == station and o.element == element
                ]
                value_state_counts: dict[str, int] = {}
                for obs in all_station_obs:
                    st = obs.value_state.value
                    value_state_counts[st] = value_state_counts.get(st, 0) + 1
                if element == "daily_rainfall":
                    common_values = [
                        o.numeric
                        for o in all_station_obs
                        if o.observation_date in common and o.numeric is not None
                    ]
                    positive = sum(1 for v in common_values if v > 0)
                    full_values = [o.numeric for o in all_station_obs if o.numeric is not None]
                    full_positive = sum(1 for v in full_values if v > 0)
                    per_station[station] = {
                        "positive_days": positive,
                        "valid_days": len(common_values),
                        "ratio": (
                            str(Decimal(positive) / Decimal(len(common_values)))
                            if common_values
                            else None
                        ),
                        "full_period": {
                            "positive_days": full_positive,
                            "valid_days": len(full_values),
                        },
                        "value_states": value_state_counts,
                    }
                else:
                    common_values = [
                        o.numeric
                        for o in all_station_obs
                        if o.observation_date in common and o.numeric is not None
                    ]
                    full_values = [o.numeric for o in all_station_obs if o.numeric is not None]
                    avg = (
                        sum(common_values) / Decimal(len(common_values)) if common_values else None
                    )
                    full_avg = sum(full_values) / Decimal(len(full_values)) if full_values else None
                    per_station[station] = {
                        "average": str(avg) if avg is not None else None,
                        "valid_days": len(common_values),
                        "full_period": {
                            "average": str(full_avg) if full_avg is not None else None,
                            "valid_days": len(full_values),
                        },
                        "value_states": value_state_counts,
                    }
            result[element] = {
                "common_dates": sorted(d.isoformat() for d in common),
                "common_day_count": len(common),
                "per_station": per_station,
            }
            if any(key[3] == element for key, _ in deduped.conflicts):
                result[element]["comparison_status"] = "conflict"
                for stats in per_station.values():
                    for section in (stats, stats.get("full_period", {})):
                        for field in ("positive_days", "ratio", "average"):
                            if field in section:
                                section[field] = None
        primary = "daily_rainfall" if "daily_rainfall" in elements else elements[0]
        merged: dict[str, Any] = {}
        for element in elements:
            for station, stats in result[element]["per_station"].items():
                entry = merged.setdefault(station, {"elements": {}})
                entry["elements"][element] = stats
                if element == primary:
                    entry["full_period"] = stats["full_period"]
                    entry["value_states"] = stats["value_states"]
                    for key in ("positive_days", "valid_days", "ratio", "average"):
                        if key in stats:
                            entry[key] = stats[key]
        result["per_station"] = merged
        incomplete = any(m.failed_scope or m.has_more for m in manifests)
        if not observations:
            data_status = DataStatus.UNAVAILABLE if incomplete else DataStatus.NO_DATA
        else:
            data_status = DataStatus.PARTIAL if warnings or incomplete else DataStatus.COMPLETE
        if deduped.conflicts:
            data_status = DataStatus.CONFLICT
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [m.to_dict() for m in manifests],
                "effective_scope": {"stations": stations, "elements": elements},
                "formula_version": "calc-v1",
                "result_values": result,
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=data_status,
            source_mode=source_mode,
            requested_scope={"stations": stations, "elements": elements},
            effective_scope={"stations": stations},
            verified_on=manifests[0].verified_on if manifests else None,
            result=result,
            evidence_ids=[evidence_id],
            warnings=warnings,
        )

    def _current_observation(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode == RuntimeMode.LIMITED:
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.UNAVAILABLE,
                result={"reason": "EXTERNAL_REQUESTS_DISABLED"},
            )
        if self.settings.app_profile != "replay":
            from gosari.sources.observations import (
                current_grid_observations,
                current_public_weather,
            )

            self.checkpoint()
            try:
                rows, manifests, warnings = current_grid_observations(
                    self.settings, self.checkpoint
                )
                source = "기상청 초단기실황"
                observation_type = "grid_observation"
                source_manifests = [manifest.to_dict() for manifest in manifests]
            except GosariError:
                self.checkpoint()
                rows, digest = current_public_weather()
                source = "Open-Meteo"
                observation_type = "model_estimate"
                warnings = ["기관 실황 연결 불가 · Open-Meteo 모델 기상"]
                source_manifests = [
                    {
                        "source_id": "open_meteo",
                        "operation": "current_model_weather",
                        "content_hash": digest,
                    }
                ]
            self.checkpoint()
            evidence_id = get_evidence_store().put(
                {
                    "public_query_spec": spec,
                    "source_manifests": source_manifests,
                    "result_values": {
                        "stations": rows,
                        "station_count": len(rows),
                        "source": source,
                        "observation_type": observation_type,
                    },
                    "units": {"temperature_c": "℃", "rain_1h_mm": "mm/1h", "wind_speed_ms": "m/s"},
                    "created_at": now_utc().isoformat(),
                }
            )
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.PARTIAL if warnings else DataStatus.COMPLETE,
                source_mode=SourceMode.FETCHED,
                fetched_at=now_utc(),
                observed_period={
                    "observation_time": rows[0].get("observation_time") if rows else None
                },
                result={
                    "stations": rows,
                    "source": source,
                    "observation_type": observation_type,
                    "rain_period_label": "1시간 강수 (mm)"
                    if observation_type == "grid_observation"
                    else "현재 강수 (mm)",
                    "accumulation_window": "1h" if observation_type == "grid_observation" else None,
                },
                evidence_ids=[evidence_id],
                warnings=warnings,
            )
        stations, meta = load_current_observations(self.settings.resolved_fixtures_dir)
        station_filter = spec.get("station_selections", [])
        if station_filter:
            names = {s.get("station_name") for s in station_filter}
            codes = {s.get("station_code") for s in station_filter}
            stations = [
                s for s in stations if s["station_name"] in names or s["station_code"] in codes
            ]
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [
                    SourceManifest(
                        source_id="kma_aws",
                        dataset_id="public_table",
                        operation="replay",
                        sanitized_parameters={},
                        content_hash=meta["file_hash"],
                        verified_on=meta["verified_on"],
                        source_mode="replay",
                    ).to_dict()
                ],
                "result_values": {"stations": stations, "station_count": len(stations)},
                "units": {"temperature_c": "℃", "day_rain_mm": "mm/day"},
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE if stations else DataStatus.NO_DATA,
            source_mode=SourceMode.REPLAY,
            observed_period={"observation_time": "2026-11-05 18:43 KST"},
            verified_on=meta["verified_on"],
            result={
                "stations": stations,
            },
            evidence_ids=[evidence_id],
            warnings=["2026-11-05 18:43 KST 관측 자료"],
        )

    def _forecast_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode != RuntimeMode.LIVE:
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.UNAVAILABLE,
                source_mode=None,
                result={"reason": "FORECAST_REPLAY_UNAVAILABLE"},
                warnings=["예보 자료가 없습니다."],
                errors=[
                    {
                        "code": "CAPABILITY_DISABLED",
                        "message": "예보 조회는 라이브 모드에서 가능합니다.",
                    }
                ],
            )
        from gosari.sources.live import KmaAdapter, TransmissionGate

        grid = spec.get("forecast_grid_id")
        if not grid:
            raise GosariError("INVALID_INPUT", {"fields": ["forecast_grid_id"]})
        nx, ny = (int(v) for v in grid.split(","))
        published = spec.get("forecast_published_at")
        if not published:
            raise GosariError("INVALID_INPUT", {"fields": ["forecast_published_at"]})
        base_date = date.fromisoformat(published[:10])
        base_time = published[11:16].replace(":", "")[:4]
        adapter = KmaAdapter(
            TransmissionGate(self.settings, checkpoint=self.checkpoint), self.settings
        )
        rows, manifest = adapter.vilage_forecast(nx, ny, base_date, base_time)
        targets = spec.get("forecast_target_times")
        if targets:
            rows = [r for r in rows if r["target_at"] in targets]
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [manifest.to_dict()],
                "result_values": {"forecast": rows, "row_count": len(rows)},
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE if rows else DataStatus.NO_DATA,
            source_mode=SourceMode.FETCHED,
            fetched_at=manifest.fetched_at,
            observed_period={"published_at": published, "grid": grid},
            result={"forecast": rows, "notice": "예보이며 관측과 구분됨"},
            evidence_ids=[evidence_id],
        )

    def _market_query(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode != RuntimeMode.LIVE or not self.settings.at_service_key:
            reason = "AT_KEY_MISSING" if not self.settings.at_service_key else "LIVE_DISABLED"
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.UNAVAILABLE,
                result={"channel": "wholesale", "reason": reason, "price_cards": []},
                errors=[
                    {
                        "code": "CAPABILITY_DISABLED",
                        "message": "도매 가격 연결이 준비되지 않았습니다.",
                    }
                ],
            )
        result, manifests, failed, completed = query_settlements(
            spec, self.settings, self.checkpoint
        )
        invalid = sum(card["price_state"] != "valid" for card in result["price_cards"])
        status = (
            DataStatus.PARTIAL
            if failed or invalid
            else (DataStatus.COMPLETE if result["price_cards"] else DataStatus.NO_DATA)
        )
        if not completed and not result["price_cards"] and failed:
            status = DataStatus.UNAVAILABLE
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [m.to_dict() for m in manifests],
                "requested_scope": spec,
                "failed_scope": failed,
                "fetched_scope": completed,
                "result_values": {
                    "price_count": len(result["price_cards"]),
                    "invalid_price_count": invalid,
                    "price_cards": result["price_cards"],
                    "units": {
                        "price_value": "KRW/original_quantity",
                        "net_weight_value": "g",
                        "price_per_kg_value": "KRW/kg",
                        "total_quantity": "original_unit",
                    },
                },
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=status,
            source_mode=SourceMode.FETCHED,
            fetched_at=now_utc(),
            requested_scope=spec,
            effective_scope={"completed": completed, "failed": failed},
            observed_period={
                "start": spec.get("settlement_date"),
                "end": spec.get("settlement_date_end"),
            },
            result=result,
            evidence_ids=[evidence_id],
            warnings=[f"조회하지 못한 날짜·시장 {len(failed)}곳"] if failed else [],
        )

    def _outing_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode == RuntimeMode.LIMITED:
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.UNAVAILABLE,
                result={"reason": "EXTERNAL_REQUESTS_DISABLED"},
            )
        if self.settings.app_profile != "replay":
            from gosari.sources.outing import compare_outings

            return compare_outings(spec, request_id, self.checkpoint)
        return compare_outings_replay(spec, request_id, settings=self.settings, replay=self.replay)

    def _survey_link(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        links = survey_link_cards()
        samples = survey_sample_cards()
        available_sample_count = len(samples)
        raw_form = str(spec.get("fresh_or_dried") or "")
        form = {"fresh": "생고사리", "dried": "건고사리"}.get(raw_form, raw_form)
        if form and form != "전체":
            samples = [card for card in samples if card.get("form") == form]
        for field, card_field in (
            ("survey_stage", "survey_stage"),
            ("grade", "survey_grade"),
            ("survey_as_of", "price_as_of"),
        ):
            if spec.get(field):
                samples = [card for card in samples if card.get(card_field) == spec[field]]
        if spec.get("origin_filter"):
            samples = [
                card
                for card in samples
                if str(spec["origin_filter"]) in str(card.get("survey_region") or "")
            ]
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.UNAVAILABLE,
            source_mode=SourceMode.LINK,
            link_status=LinkStatus.LINK_READY,
            verified_on="2026-11-04",
            requested_scope={"sample_conditions": spec},
            effective_scope={
                "matched_samples": len(samples),
                "available_samples": available_sample_count,
            },
            result={
                "channel": "survey",
                "sample_cards": samples,
                "links": links,
                "reason": "LINK_ONLY",
                "matched_sample_count": len(samples),
                "available_sample_count": available_sample_count,
                "sample_filter_status": "matched" if samples else "no_match",
            },
        )

    def _retail_lookup(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        products, meta = load_retail_products(self.settings.resolved_fixtures_dir)
        cards = retail_sample_cards(products, meta["verified_on"])
        links = retail_link_cards()
        available_sample_count = len(cards)
        raw_form = str(spec.get("fresh_or_dried") or "")
        form = {"fresh": "생고사리", "dried": "건고사리"}.get(raw_form, raw_form)
        if form and form != "전체":
            cards = [card for card in cards if card.get("form") == form]
        retailers = set(spec.get("source_ids", [])) & {"tamnao", "oasis"}
        names = {"tamnao": "탐나오", "oasis": "오아시스마켓"}
        if retailers:
            cards = [
                card for card in cards if card.get("source_id") in {names[key] for key in retailers}
            ]
            links = [link for link in links if link.get("source_id") in retailers]
        if spec.get("product_option"):
            cards = [
                card
                for card in cards
                if (card.get("product_option") or f"{card.get('net_weight_value')}g")
                == spec["product_option"]
            ]
        if spec.get("product_id"):
            from urllib.parse import parse_qs, urlsplit

            def product_id(card: dict[str, Any]) -> str:
                url = urlsplit(str(card.get("source_url") or ""))
                return parse_qs(url.query).get("prdtNum", [""])[0] or url.path.rsplit("/", 1)[-1]

            cards = [card for card in cards if product_id(card) == spec["product_id"]]
        if spec.get("package_weight_unit"):
            import re

            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*(kg|g)\s*", str(spec["package_weight_unit"])
            )
            grams = Decimal(match[1]) * (1000 if match[2] == "kg" else 1) if match else None
            cards = [
                card
                for card in cards
                if grams is not None
                and card.get("net_weight_value") is not None
                and card.get("net_weight_unit") == "g"
                and Decimal(str(card.get("net_weight_value"))) == grams
            ]
        if spec.get("origin_filter"):
            cards = [
                card
                for card in cards
                if str(spec["origin_filter"]) in str(card.get("origin_label_raw") or "")
            ]
        matched_sources = {card.get("source_id") for card in cards}
        links = [link for link in links if names.get(str(link.get("source_id"))) in matched_sources]
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [
                    SourceManifest(
                        source_id="retail_sample",
                        dataset_id="display_price",
                        operation="replay",
                        sanitized_parameters={},
                        content_hash=meta["file_hash"],
                        verified_on=meta["verified_on"],
                        source_mode="replay",
                    ).to_dict()
                ],
                "result_values": {
                    "product_count": len(cards),
                    "price_cards": cards,
                    "units": {
                        "price_value": "KRW/product_option",
                        "net_weight_value": "g",
                        "price_per_kg_value": "KRW/kg",
                        "shipping_value": "KRW",
                        "coupon_price": "KRW/product_option",
                    },
                },
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE if cards else DataStatus.NO_DATA,
            source_mode=SourceMode.REPLAY,
            link_status=LinkStatus.LINK_READY,
            verified_on=meta["verified_on"],
            requested_scope={"sample_conditions": spec},
            effective_scope={
                "matched_samples": len(cards),
                "available_samples": available_sample_count,
            },
            result={
                "channel": "retail",
                "sample_cards": cards,
                "links": links,
                "matched_sample_count": len(cards),
                "available_sample_count": available_sample_count,
                "reason": None if cards else "NO_MATCHING_SAMPLE",
            },
            evidence_ids=[evidence_id],
        )

    def _station_search(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode == RuntimeMode.LIVE:
            from gosari.sources.live import JejuHubAdapter, TransmissionGate

            self.checkpoint()
            rows, manifest = JejuHubAdapter(
                TransmissionGate(self.settings, checkpoint=self.checkpoint), self.settings
            ).stations()
            stations = [
                {
                    "source_id": "jeju_578",
                    "station_name": row.get("observatoryName"),
                    "station_code": row.get("observatoryCode"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "altitude_m": row.get("seaLevelAltitude"),
                    "location": row.get("legalDongriCode", ""),
                }
                for row in rows
            ]
            evidence_id = get_evidence_store().put(
                {
                    "public_query_spec": spec,
                    "source_manifests": [manifest.to_dict()],
                    "result_values": {"station_count": len(stations)},
                    "created_at": now_utc().isoformat(),
                }
            )
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.COMPLETE,
                source_mode=SourceMode.FETCHED,
                fetched_at=manifest.fetched_at,
                result={"stations": stations},
                evidence_ids=[evidence_id],
            )
        stations = self.replay.stations()
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE,
            source_mode=SourceMode.REPLAY,
            result={"stations": stations},
        )
