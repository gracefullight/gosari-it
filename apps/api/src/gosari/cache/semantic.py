"""질문·응답 의미 캐시 (SRS §11). 적격성 → 정확 fingerprint → exact → cosine 순서."""

import hashlib
import json
from datetime import datetime
from typing import Any

from gosari.cache.embeddings import MAX_TOKENS, get_engine
from gosari.config import get_settings
from gosari.db import connection, db_available
from gosari.domain import CacheResolution
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)

FINGERPRINT_VERSION = "fingerprint-v1"
CALCULATION_VERSION = "calc-v1"
PROMPT_VERSION = "prompt-v3-bound-facts"
TOOL_SCHEMA_VERSION = "tools-v1"
SAFETY_POLICY_VERSION = "safety-v1"


def condition_fingerprint(spec: dict[str, Any]) -> str:
    """§11.3 정확 조건 키. 도메인 비적용 필드는 정규 null, 미확정이면 우회 대상."""
    body = {
        "version": FINGERPRINT_VERSION,
        "intent": spec.get("operation"),
        "source_ids": sorted(spec.get("source_ids", [])),
        "station_selections": sorted(
            json.dumps(s, sort_keys=True, ensure_ascii=False)
            for s in spec.get("station_selections", [])
        ),
        "years": sorted(spec.get("years", [])),
        "month_day_start": spec.get("month_day_start"),
        "month_day_end": spec.get("month_day_end"),
        "elements": sorted(spec.get("elements", [])),
        "comparison_scope": spec.get("comparison_scope"),
        "aggregation": spec.get("aggregation"),
        "unit": spec.get("unit"),
        "accumulation_window": spec.get("accumulation_window", "1d"),
        "timezone": spec.get("timezone", "Asia/Seoul"),
        "polarity": spec.get("polarity", "positive"),
        "forecast_grid_id": spec.get("forecast_grid_id"),
        "forecast_published_at": spec.get("forecast_published_at"),
        "forecast_target_times": spec.get("forecast_target_times"),
        "price_channel": spec.get("price_channel"),
        "market_ids": spec.get("market_ids"),
        "item_codes": spec.get("item_codes"),
        "fresh_or_dried": spec.get("fresh_or_dried"),
        "grade": spec.get("grade"),
        "package_weight_unit": spec.get("package_weight_unit"),
        "survey_region": spec.get("survey_region"),
        "survey_stage": spec.get("survey_stage"),
        "survey_as_of": spec.get("survey_as_of"),
        "product_id": spec.get("product_id"),
        "product_option": spec.get("product_option"),
        "origin_filter": spec.get("origin_filter"),
        "shipping_basis": spec.get("shipping_basis"),
        "coupon_basis": spec.get("coupon_basis"),
        "settlement_date": spec.get("settlement_date"),
        "settlement_date_end": spec.get("settlement_date_end"),
        "package_code": spec.get("package_code"),
        "candidates": spec.get("candidates"),
        "preferred_elements": spec.get("preferred_elements"),
        "parser_version": "1",
        "calculation_version": CALCULATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "safety_policy_version": SAFETY_POLICY_VERSION,
        "embedding_revision": get_settings().embedding_revision,
        "embedding_model": get_settings().embedding_model_path,
        "llm_model": get_settings().llm_model,
    }
    if spec.get("operation") == "current_observation":
        body["current_provider_version"] = "kma-ultra-short-v1"
    return json_hash(body)


def exact_query_hash(safe_text: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{fingerprint}\x00{safe_text}".encode()).hexdigest()


def eligibility_bypass_reason(spec: dict[str, Any], safe_text: str) -> str | None:
    """임베딩 이전 우회 사유. 개인혼입 의심·조건 미확정·길이 초과/미확인."""
    settings = get_settings()
    if not settings.response_cache_enabled:
        return "CACHE_DISABLED"
    if spec.get("contains_personal_hint"):
        return "PERSONAL_HINT"
    required = ("operation", "source_ids")
    if any(not spec.get(k) for k in required):
        return "CONDITIONS_UNRESOLVED"
    engine = get_engine()
    count = engine.token_count(safe_text)
    if count is None:
        return "TOKEN_COUNT_UNKNOWN"
    if count > MAX_TOKENS:
        return "TOKEN_LIMIT_EXCEEDED"
    return None


def lookup(
    spec: dict[str, Any], safe_text: str, *, now: datetime
) -> tuple[CacheResolution, dict[str, Any] | None]:
    """exact 일치 우선, 검증된 문턱값이 있을 때만 cosine 후보 조회."""
    bypass = eligibility_bypass_reason(spec, safe_text)
    if bypass:
        logger.info("cache bypass", reason=bypass)
        return CacheResolution.BYPASS, None
    if not db_available():
        return CacheResolution.BYPASS, None
    fingerprint = condition_fingerprint(spec)
    eq_hash = exact_query_hash(safe_text, fingerprint)
    try:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT cache_entry_id, public_answer, evidence_ids, valid_until
                FROM public_response_cache
                WHERE condition_fingerprint = %s AND exact_query_hash = %s
                  AND reusable = true AND quality_passed = true
                  AND rights_status = 'public_api' AND invalidated_at IS NULL AND valid_until > %s
                LIMIT 1
                """,
                (fingerprint, eq_hash, now),
            ).fetchone()
            if row and row[2] and result_cacheable(row[1]):
                conn.execute(
                    "UPDATE public_response_cache SET hit_count = hit_count + 1, "
                    "last_used_at = %s WHERE cache_entry_id = %s",
                    (now, row[0]),
                )
                conn.commit()
                return CacheResolution.EXACT_HIT, {
                    "answer": row[1],
                    "evidence_ids": row[2],
                }

            settings = get_settings()
            if not settings.domain_threshold_config:
                return CacheResolution.MISS, None
            threshold = float(settings.domain_threshold_config)
            vector = get_engine().embed(safe_text)
            if vector is None:
                return CacheResolution.MISS, None
            candidates = conn.execute(
                """
                SELECT cache_entry_id, public_answer, evidence_ids,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM public_response_cache
                WHERE condition_fingerprint = %s
                  AND reusable = true AND quality_passed = true
                  AND rights_status = 'public_api' AND invalidated_at IS NULL AND valid_until > %s
                ORDER BY embedding <=> %s::vector
                LIMIT 5
                """,
                (vector, fingerprint, now, vector),
            ).fetchall()
            for cand in candidates:
                if (
                    cand[2]
                    and result_cacheable(cand[1])
                    and cand[3] is not None
                    and float(cand[3]) >= threshold
                ):
                    conn.execute(
                        "UPDATE public_response_cache SET hit_count = hit_count + 1, "
                        "last_used_at = %s WHERE cache_entry_id = %s",
                        (now, cand[0]),
                    )
                    conn.commit()
                    return CacheResolution.SEMANTIC_HIT, {
                        "answer": cand[1],
                        "evidence_ids": cand[2],
                    }
    except Exception as exc:
        logger.warning("cache lookup failed", error_type=type(exc).__name__)
        return CacheResolution.BYPASS, None
    return CacheResolution.MISS, None


def result_cacheable(result: dict[str, Any]) -> bool:
    """필요 값에 missing/error/unresolved_blank·충돌이 있으면 저장 금지. valid_zero는 허용."""
    if result.get("data_status") not in ("complete",):
        return False
    if result.get("warnings") or result.get("explanation_verified") is False:
        return False
    answer = result.get("result", {})
    if isinstance(answer, dict) and answer.get("explanation"):
        from gosari.agent.llm import explanation_matches

        if not explanation_matches(str(answer["explanation"]), answer):
            return False

    def valid(value: Any, key: str = "") -> bool:
        if key == "forecast" and (
            not isinstance(value, list)
            or any(
                not isinstance(row, dict)
                or row.get("value") is None
                or (isinstance(row["value"], str) and not row["value"].strip())
                for row in value
            )
        ):
            return False
        if key in ("temperature_c", "positive_days", "valid_days", "average") and value is None:
            return False
        if key in ("value_state", "state") and isinstance(value, str):
            return value in ("valid", "valid_zero")
        if key in ("value_states", "value_state_counts"):
            if isinstance(value, dict):
                return all(
                    state in ("valid", "valid_zero") or count == 0 for state, count in value.items()
                )
            if isinstance(value, list):
                return all(state in ("valid", "valid_zero") for state in value)
            return False
        if isinstance(value, dict):
            return all(valid(item, str(name)) for name, item in value.items())
        if isinstance(value, list):
            return all(valid(item) for item in value)
        return True

    return valid(result)


def store(
    spec: dict[str, Any],
    safe_text: str,
    answer: dict[str, Any],
    evidence_ids: list[str],
    *,
    now: datetime,
    valid_until: datetime,
) -> bool:
    bypass = eligibility_bypass_reason(spec, safe_text)
    if bypass or not db_available() or not evidence_ids or not result_cacheable(answer):
        return False
    vector = get_engine().embed(safe_text)
    if vector is None:
        return False
    fingerprint = condition_fingerprint(spec)
    eq_hash = exact_query_hash(safe_text, fingerprint)
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO public_response_cache
                    (cache_entry_id, public_query_text, exact_query_hash, condition_fingerprint,
                     embedding, embedding_model, embedding_revision, dimensions,
                     public_answer, evidence_ids, llm_model, prompt_version, tool_schema_version,
                     safety_policy_version, created_at, valid_until,
                     quality_passed, reusable, rights_status)
                VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,true,%s)
                ON CONFLICT (exact_query_hash) DO UPDATE SET
                    public_answer = EXCLUDED.public_answer,
                    evidence_ids = EXCLUDED.evidence_ids,
                    embedding = EXCLUDED.embedding,
                    created_at = EXCLUDED.created_at,
                    valid_until = EXCLUDED.valid_until,
                    invalidated_at = NULL,
                    quality_passed = true,
                    reusable = true
                WHERE public_response_cache.valid_until <= EXCLUDED.created_at
                   OR public_response_cache.invalidated_at IS NOT NULL
                """,
                (
                    f"cache-{eq_hash[:24]}",
                    safe_text,
                    eq_hash,
                    fingerprint,
                    vector,
                    get_settings().embedding_model_path,
                    get_settings().embedding_revision,
                    384,
                    json.dumps(answer, ensure_ascii=False, default=str),
                    evidence_ids,
                    get_settings().llm_model,
                    PROMPT_VERSION,
                    TOOL_SCHEMA_VERSION,
                    SAFETY_POLICY_VERSION,
                    now,
                    valid_until,
                    "public_api",
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("cache store failed", error_type=type(exc).__name__)
        return False
