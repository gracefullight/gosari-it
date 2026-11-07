"""나들이 후보 일정·지역 비교 replay 구현 (SRS §5.2 FR-OUT-001~008).

관측시각·예보 발표시각·예보 대상시각을 분리하고, 로컬 편집용 준비 목록 초안을 함께 제공한다.
"""

from typing import Any

from gosari.agent.evidence_store import get_evidence_store
from gosari.config import Settings
from gosari.domain import DataStatus, SourceMode
from gosari.domain.envelope import ResultEnvelope
from gosari.quality.calculation import deduplicate, rain_stats, temperature_stats
from gosari.sources import SourceManifest, now_utc
from gosari.sources.replay import ReplaySource, load_current_observations


def compare_outings_replay(
    spec: dict[str, Any],
    request_id: str,
    *,
    settings: Settings,
    replay: ReplaySource,
) -> ResultEnvelope:
    candidates = spec.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        # 기본 후보: station_selections 기반으로 후보 카드 구성
        selections = spec.get("station_selections", [])
        if selections:
            candidates = [
                {
                    "candidate_id": f"cand-{idx + 1}",
                    "station_name": s.get("station_name"),
                    "station_code": s.get("station_code"),
                    "target_date": s.get("target_date") or "봄철 기준 (4~5월)",
                    "target_time_window": s.get("target_time_window") or "오전 07:00~11:00",
                }
                for idx, s in enumerate(selections)
                if s.get("station_name")
            ]
        else:
            candidates = [
                {
                    "candidate_id": "cand-1",
                    "station_name": "선흘",
                    "target_date": "후보 1 (주말 오전)",
                    "target_time_window": "07:00~11:00",
                },
                {
                    "candidate_id": "cand-2",
                    "station_name": "제주(184)",
                    "target_date": "후보 2 (주말 오전)",
                    "target_time_window": "08:00~12:00",
                },
            ]
    current_stations, current_meta = load_current_observations(settings.resolved_fixtures_dir)
    all_obs = replay.all_observations()
    deduped = deduplicate(all_obs)
    preferred = spec.get("preferred_elements") or ["강수 적은 날", "기온 완만"]

    candidate_cards: list[dict[str, Any]] = []
    failed_candidates: list[dict[str, Any]] = []
    for idx, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            continue
        station_name = str(cand.get("station_name") or "").strip()
        target_date = str(cand.get("target_date") or f"후보 {idx + 1}")
        time_window = str(cand.get("target_time_window") or "오전")
        if not station_name:
            failed_candidates.append(
                {
                    "candidate_id": cand.get("candidate_id", f"cand-{idx + 1}"),
                    "reason": "STATION_MISSING",
                    "message": "관측소 지점이 지정되지 않았습니다.",
                }
            )
            continue
        matched_current = next(
            (
                s
                for s in current_stations
                if s["station_name"] == station_name
                or station_name.startswith(s["station_name"])
                or (s["station_code"] and s["station_code"] in station_name)
            ),
            None,
        )
        station_obs = [o for o in deduped.unique if o.station_key == station_name]
        years = sorted({o.observation_date.year for o in station_obs})
        history_summary = []
        for y in years:
            r_stats = rain_stats(station_obs, station_name, y)
            t_avg, t_cnt = temperature_stats(station_obs, station_name, y)
            val_states: dict[str, int] = {}
            for o in station_obs:
                if o.observation_date.year == y and o.element == "daily_rainfall":
                    val_states[o.value_state.value] = val_states.get(o.value_state.value, 0) + 1
            history_summary.append(
                {
                    "year": y,
                    "rain_positive_days": r_stats.positive_days,
                    "rain_valid_days": r_stats.valid_days,
                    "temp_average_c": str(round(t_avg, 1)) if t_avg is not None else None,
                    "temp_valid_days": t_cnt,
                    "unresolved_blank_days": val_states.get("unresolved_blank", 0),
                }
            )
        if not matched_current and not history_summary:
            failed_candidates.append(
                {
                    "candidate_id": cand.get("candidate_id", f"cand-{idx + 1}"),
                    "station_name": station_name,
                    "reason": "NO_STATION_DATA",
                    "message": f"'{station_name}' 지점의 관측 자료가 없습니다.",
                }
            )
            continue
        reasons: list[str] = []
        if matched_current:
            reasons.append(
                f"{matched_current['observation_time']} KST · "
                f"기온 {matched_current['temperature_c']}℃, "
                f"일강수 {matched_current['day_rain_mm']}mm"
            )
        for h in history_summary:
            blank_note = (
                f" (공란 미확정 {h['unresolved_blank_days']}일 별도)"
                if h["unresolved_blank_days"]
                else ""
            )
            reasons.append(
                f"{h['year']}년 봄 · "
                f"관측 {h['rain_valid_days']}일 중 비 {h['rain_positive_days']}일"
                + (
                    f", 평균 {h['temp_average_c']}℃ ({h['temp_valid_days']}일 관측)"
                    if h["temp_average_c"]
                    else ""
                )
                + blank_note
            )
        candidate_cards.append(
            {
                "candidate_id": cand.get("candidate_id", f"cand-{idx + 1}"),
                "station_name": station_name,
                "target_date": target_date,
                "target_time_window": time_window,
                "current_observation": (
                    {
                        "observation_time_kst": matched_current["observation_time"],
                        "temperature_c": str(matched_current["temperature_c"])
                        if matched_current["temperature_c"] is not None
                        else None,
                        "day_rain_mm": str(matched_current["day_rain_mm"])
                        if matched_current["day_rain_mm"] is not None
                        else None,
                        "location": matched_current["location"],
                        "altitude_m": str(matched_current["altitude_m"])
                        if matched_current["altitude_m"] is not None
                        else None,
                    }
                    if matched_current
                    else None
                ),
                "forecast_status": {
                    "published_at": None,
                    "target_at": f"{target_date} {time_window}",
                    "status": "unavailable_in_replay",
                    "note": "예보 자료가 없습니다.",
                },
                "history_context": history_summary,
                "comparison_reasons": reasons,
            }
        )

    checklist = [
        "긴소매·긴바지 및 방수 겉옷·장화 (중산간 기온·강수 대비)",
        "고사리 가방(앞치마)·장갑·모자",
        "식수·간식 및 동행자 연락 수단 확인",
        "현장 출입·채취 허용 구역 여부 사전 확인 (관리 주체 기준)",
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
                    content_hash=current_meta["file_hash"],
                    verified_on=current_meta["verified_on"],
                    source_mode="replay",
                ).to_dict()
            ],
            "formula_version": "calc-v1",
            "result_values": {
                "candidate_count": len(candidate_cards),
                "failed_count": len(failed_candidates),
            },
            "created_at": now_utc().isoformat(),
        }
    )
    if candidate_cards and failed_candidates:
        status = DataStatus.PARTIAL
    elif candidate_cards:
        status = DataStatus.COMPLETE
    else:
        status = DataStatus.NO_DATA
    warnings: list[str] = []
    if failed_candidates:
        warnings.append(f"관측 자료가 없는 후보 {len(failed_candidates)}건")
    return ResultEnvelope(
        request_id=request_id,
        data_status=status,
        source_mode=SourceMode.REPLAY,
        requested_scope={"candidates": candidates, "preferred_elements": preferred},
        effective_scope={"matched_candidates": len(candidate_cards)},
        observed_period={"observation_time": "2026-11-05 18:43 KST"},
        verified_on=current_meta["verified_on"],
        result={
            "candidates": candidate_cards,
            "failed_candidates": failed_candidates,
            "preferred_elements": preferred,
            "preparation_checklist": checklist,
        },
        evidence_ids=[evidence_id],
        warnings=warnings,
    )
