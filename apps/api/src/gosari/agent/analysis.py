"""공개 분석 모듈 — 결정론 계산·근거 생성. LLM은 설명만 담당한다 (SRS §4.1)."""

import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from gosari.config import Settings, get_settings
from gosari.domain import DataStatus, LinkStatus, RuntimeMode, SourceMode
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.logging import get_logger
from gosari.quality.calculation import (
    Observation,
    common_actual_dates,
    common_month_days,
    deduplicate,
    rain_stats,
    temperature_stats,
)
from gosari.sources import SourceManifest, json_hash, now_utc
from gosari.sources.links import (
    retail_link_cards,
    retail_sample_cards,
    survey_link_cards,
)
from gosari.sources.replay import (
    ReplaySource,
    load_at_summary,
    load_current_observations,
    load_retail_products,
)

logger = get_logger(__name__)

WARNING_NOT_HARVEST = "관측소 기술통계이며 고사리 출현·수확량·채취 허가를 뜻하지 않음"


class EvidenceStore:
    """공개 근거 저장소. 개인 수첩 ID·별칭·세션 ID를 포함하지 않는다."""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def put(self, evidence: dict[str, Any]) -> str:
        evidence_id = f"ev-{json_hash(evidence)[:24]}"
        with self._lock:
            self._entries[evidence_id] = evidence
        return evidence_id

    def get(self, evidence_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._entries.get(evidence_id)


_evidence_store = EvidenceStore()


def get_evidence_store() -> EvidenceStore:
    return _evidence_store


class AnalysisEngine:
    def __init__(self, settings: Settings | None = None) -> None:
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
                observations = [o for o in observations if o.station_key in stations]
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
            warnings = (
                []
                if self.runtime_mode == RuntimeMode.REPLAY
                else ["고정 검증 표본 재생 — 실시간 조회 아님"]
            )
            return observations, SourceMode.REPLAY, [manifest], warnings
        from gosari.sources.live import JejuHubAdapter, TransmissionGate

        gate = TransmissionGate(self.settings)
        adapter = JejuHubAdapter(gate, self.settings)
        years = spec.get("years", [])
        start_md = spec.get("month_day_start", "04-01")
        end_md = spec.get("month_day_end", "05-31")
        observations: list[Observation] = []
        manifests: list[SourceManifest] = []
        failed: list[str] = []
        for year in years:
            start = date.fromisoformat(f"{year}-{start_md}")
            end = date.fromisoformat(f"{year}-{end_md}")
            day = start
            while day <= end:
                try:
                    obs, manifest = adapter.daily_weather(
                        day, stations[0] if len(stations) == 1 else None
                    )
                    if stations:
                        obs = [o for o in obs if o.station_key in stations]
                    observations.extend(obs)
                    manifests.append(manifest)
                except GosariError:
                    failed.append(day.isoformat())
                day += timedelta(days=1)
        warnings = [f"일부 날짜 조회 실패: {len(failed)}일"] if failed else []
        return observations, SourceMode.FETCHED, manifests, warnings

    def _history_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        stations = spec.get("station_selections", [])
        if len(stations) != 1 or not stations[0].get("station_name"):
            raise GosariError("STATION_AMBIGUOUS")
        station = stations[0]["station_name"]
        years = sorted(spec.get("years", []))
        if len(years) < 2:
            raise GosariError("INVALID_INPUT", {"fields": ["years"]})
        observations, source_mode, manifests, warnings = self._observations_for(spec)
        deduped = deduplicate(observations)
        if deduped.conflicts:
            warnings.append(f"동일 키 충돌 {len(deduped.conflicts)}건 — 자동 봉합하지 않음")
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
                    element_result["per_year"][str(year)] = {
                        "average": str(avg) if avg is not None else None,
                        "valid_days": count,
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
            result[element] = element_result
        data_status = DataStatus.COMPLETE if not warnings else DataStatus.PARTIAL
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
            warnings=[WARNING_NOT_HARVEST, *warnings],
        )

    def _region_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        stations = [
            s.get("station_name")
            for s in spec.get("station_selections", [])
            if s.get("station_name")
        ]
        if len(stations) < 2:
            raise GosariError("INVALID_INPUT", {"fields": ["station_selections"]})
        observations, source_mode, manifests, warnings = self._observations_for(spec)
        deduped = deduplicate(observations)
        elements = spec.get("elements", ["daily_rainfall"])
        result: dict[str, Any] = {}
        for element in elements:
            common = common_actual_dates(deduped.unique, stations, element)
            per_station = {}
            for station in stations:
                if element == "daily_rainfall":
                    values = [
                        o.numeric
                        for o in deduped.unique
                        if o.station_key == station
                        and o.element == element
                        and o.observation_date in common
                        and o.numeric is not None
                    ]
                    positive = sum(1 for v in values if v > 0)
                    per_station[station] = {
                        "positive_days": positive,
                        "valid_days": len(values),
                        "ratio": str(Decimal(positive) / Decimal(len(values))) if values else None,
                    }
            result[element] = {
                "common_dates": sorted(d.isoformat() for d in common),
                "per_station": per_station,
            }
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [m.to_dict() for m in manifests],
                "formula_version": "calc-v1",
                "result_values": result,
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE if result else DataStatus.NO_DATA,
            source_mode=source_mode,
            requested_scope={"stations": stations},
            result=result,
            evidence_ids=[evidence_id],
            warnings=[WARNING_NOT_HARVEST, *warnings],
        )

    def _current_observation(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
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
                "result_values": {"station_count": len(stations)},
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
                "notice": "고정 공개 표 재생 — 현재 API 호출 결과 아님",
            },
            evidence_ids=[evidence_id],
            warnings=["당일 관측 표본은 2026-11-05 18:43 KST 기준이며 실시간이 아님"],
        )

    def _forecast_compare(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        if self.runtime_mode != RuntimeMode.LIVE:
            return ResultEnvelope(
                request_id=request_id,
                data_status=DataStatus.UNAVAILABLE,
                source_mode=None,
                result={"reason": "FORECAST_REPLAY_UNAVAILABLE"},
                warnings=["예보 재생 표본이 없습니다. 라이브 모드에서 getVilageFcst로 조회합니다."],
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
        base_time = published[11:15].replace(":", "")
        adapter = KmaAdapter(TransmissionGate(self.settings), self.settings)
        rows, manifest = adapter.vilage_forecast(nx, ny, base_date, base_time)
        targets = spec.get("forecast_target_times")
        if targets:
            rows = [r for r in rows if r["target_at"] in targets]
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [manifest.to_dict()],
                "result_values": {"row_count": len(rows)},
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
        rows, meta = load_at_summary(self.settings.resolved_fixtures_dir)
        market_ids = spec.get("market_ids")
        if market_ids:
            rows = [r for r in rows if r["market_code"] in market_ids]
        evidence_id = get_evidence_store().put(
            {
                "public_query_spec": spec,
                "source_manifests": [
                    SourceManifest(
                        source_id="at_settlement",
                        dataset_id="15141809",
                        operation="replay_summary",
                        sanitized_parameters={"market_ids": market_ids},
                        content_hash=meta["file_hash"],
                        verified_on=meta["verified_on"],
                        source_mode="replay",
                    ).to_dict()
                ],
                "result_values": {"market_rows": len(rows)},
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE if rows else DataStatus.NO_DATA,
            source_mode=SourceMode.REPLAY,
            verified_on=meta["verified_on"],
            result={
                "channel": "wholesale",
                "summary_rows": rows,
                "notice": "날짜별·시장별 조회 검증 기록이며 거래 상세 가격이 아님. "
                "표본 내 제주 산지명 0건은 전체 부재 증거가 아님.",
            },
            evidence_ids=[evidence_id],
        )

    def _survey_link(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        cards = survey_link_cards()
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.UNAVAILABLE,
            source_mode=SourceMode.LINK,
            link_status=LinkStatus.LINK_READY,
            result={"channel": "survey", "links": cards, "reason": "LINK_ONLY"},
            warnings=["공식 조회 링크만 제공 — 자동 취득·재배포 권리 미확인"],
        )

    def _retail_lookup(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        products, meta = load_retail_products(self.settings.resolved_fixtures_dir)
        cards = retail_sample_cards(products, meta["verified_on"])
        links = retail_link_cards()
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
                "result_values": {"product_count": len(cards)},
                "created_at": now_utc().isoformat(),
            }
        )
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE,
            source_mode=SourceMode.REPLAY,
            link_status=LinkStatus.LINK_READY,
            verified_on=meta["verified_on"],
            result={"channel": "retail", "sample_cards": cards, "links": links},
            evidence_ids=[evidence_id],
            warnings=["표본 표시가는 체결가·시장 대표시세가 아니며 확인시점 기준임"],
        )

    def _station_search(self, spec: dict[str, Any], request_id: str) -> ResultEnvelope:
        stations = self.replay.stations()
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus.COMPLETE,
            source_mode=SourceMode.REPLAY,
            result={"stations": stations},
            warnings=["재생 관측소 목록 — 라이브 모드에서는 578 실조회"],
        )
