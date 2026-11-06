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
PROMPT_VERSION = "prompt-v1"
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
        "parser_version": "1",
        "calculation_version": CALCULATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "safety_policy_version": SAFETY_POLICY_VERSION,
        "embedding_revision": get_settings().embedding_revision,
    }
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
                  AND reusable = true AND invalidated_at IS NULL AND valid_until > %s
                LIMIT 1
                """,
                (fingerprint, eq_hash, now),
            ).fetchone()
            if row:
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
                  AND reusable = true AND invalidated_at IS NULL AND valid_until > %s
                ORDER BY embedding <=> %s::vector
                LIMIT 5
                """,
                (vector, fingerprint, now, vector),
            ).fetchall()
            for cand in candidates:
                if cand[3] is not None and float(cand[3]) >= threshold:
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
    states = result.get("value_states", [])
    return all(s in ("valid", "valid_zero") for s in states)


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
    if bypass or not db_available() or not result_cacheable(answer):
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
                ON CONFLICT (exact_query_hash) DO NOTHING
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
