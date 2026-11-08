"""질문·응답 의미 캐시 (SRS §11). 적격성 → 정확 fingerprint → exact → cosine 순서."""

import hashlib
import json
import math
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from gosari.cache.embeddings import MAX_TOKENS, get_engine
from gosari.config import get_settings
from gosari.db import connection, db_available
from gosari.domain import CacheResolution
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)

FINGERPRINT_VERSION = "fingerprint-v2-public-db"
CALCULATION_VERSION = "calc-v1"
PROMPT_VERSION = "prompt-v11-candidate-comparison"
TOOL_SCHEMA_VERSION = "tools-v8-ranked-weather-context"
SAFETY_POLICY_VERSION = "safety-v1"


def canonical_public_spec(spec: dict[str, Any]) -> dict[str, Any]:
    from gosari.agent import build_public_spec

    if spec.get("contains_personal_hint"):
        raise ValueError("Personal conditions are not cacheable")
    canonical = build_public_spec(
        {key: value for key, value in spec.items() if key != "contains_personal_hint"}
    )
    for key in ("source_ids", "years", "elements", "market_ids"):
        if isinstance(canonical.get(key), list):
            canonical[key] = sorted(set(canonical[key]))
    canonical.setdefault("timezone", "Asia/Seoul")
    canonical.setdefault("accumulation_window", "1d")
    canonical.setdefault("polarity", "positive")
    return canonical


def answer_integrity(answer: dict[str, Any], evidence_ids: list[str], fingerprint: str) -> str:
    return json_hash({"answer": answer, "evidence_ids": evidence_ids, "fingerprint": fingerprint})


def condition_fingerprint(spec: dict[str, Any]) -> str:
    """§11.3 정확 조건 키. 도메인 비적용 필드는 정규 null, 미확정이면 우회 대상."""
    spec = canonical_public_spec(spec)
    body = {
        "canonical_spec": spec,
        "runtime_profile": get_settings().app_profile,
        "external_requests": get_settings().external_requests_enabled,
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


def eligibility_bypass_reason(
    spec: dict[str, Any], safe_text: str, *, check_tokens: bool = True
) -> str | None:
    """임베딩 이전 우회 사유. 개인혼입 의심·조건 미확정·길이 초과/미확인."""
    settings = get_settings()
    if not settings.response_cache_enabled:
        return "CACHE_DISABLED"
    from gosari.agent import detect_personal_hint

    if spec.get("contains_personal_hint") or detect_personal_hint(safe_text):
        return "PERSONAL_HINT"
    try:
        canonical_public_spec(spec)
    except Exception:
        return "CONDITIONS_UNRESOLVED"
    if not safe_text or len(safe_text) > settings.max_text_length:
        return "INPUT_TOO_LARGE"
    if not check_tokens:
        return None
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
    bypass = eligibility_bypass_reason(spec, safe_text, check_tokens=False)
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
                SELECT cache_entry_id, public_answer, evidence_ids, valid_until, answer_hash
                FROM public_response_cache
                WHERE condition_fingerprint = %s AND exact_query_hash = %s
                  AND reusable = true AND quality_passed = true
                  AND rights_status = 'public_api' AND invalidated_at IS NULL AND valid_until > %s
                LIMIT 1
                """,
                (fingerprint, eq_hash, now),
            ).fetchone()
            if (
                row
                and row[2]
                and result_cacheable(row[1])
                and row[4] == answer_integrity(row[1], row[2], fingerprint)
            ):
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
            threshold = max(0.95, float(settings.domain_threshold_config))
            if eligibility_bypass_reason(spec, safe_text):
                return CacheResolution.MISS, None
            vector = get_engine().embed(safe_text)
            if vector is None:
                return CacheResolution.MISS, None
            candidates = conn.execute(
                """
                SELECT cache_entry_id, public_answer, evidence_ids,
                       1 - (embedding <=> %s::vector) AS similarity, answer_hash
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
                    and float(cand[3]) > threshold
                    and cand[4] == answer_integrity(cand[1], cand[2], fingerprint)
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
        if key == "data_status" and value != "complete":
            return False
        if key in {"warnings", "errors", "failed_candidates"} and value:
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
        if key in {
            "session_id",
            "record_id",
            "source_record_ids",
            "private_region_id",
            "contact_id",
            "recipient_alias",
            "companion_aliases",
            "activity_text",
            "location_address",
            "consent_id",
            "preview_id",
            "editable_message",
            "local_alias",
            "conversation_history",
            "api_key",
            "serviceKey",
            "projectKey",
            "authKey",
            "password",
        }:
            return False
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
        if (
            key
            in (
                "temperature_c",
                "positive_days",
                "valid_days",
                "average",
                "price_value",
                "normalized_value",
                "normalized_numeric_value",
            )
            and value is None
        ):
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
    bypass = eligibility_bypass_reason(spec, safe_text, check_tokens=False)
    if bypass or not db_available() or not evidence_ids or not result_cacheable(answer):
        return False
    vector = (
        get_engine().embed(safe_text)
        if eligibility_bypass_reason(spec, safe_text) is None
        else None
    )
    fingerprint = condition_fingerprint(spec)
    eq_hash = exact_query_hash(safe_text, fingerprint)
    valid_until = min(valid_until, now + timedelta(seconds=1800))
    if valid_until <= now:
        return False
    digest = answer_integrity(answer, evidence_ids, fingerprint)
    try:
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO public_response_cache
                    (cache_entry_id, public_query_text, exact_query_hash, condition_fingerprint,
                     embedding, embedding_model, embedding_revision, dimensions,
                     public_answer, evidence_ids, llm_model, prompt_version, tool_schema_version,
                     safety_policy_version, created_at, valid_until,
                     quality_passed, reusable, rights_status, answer_hash)
                VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,true,%s,%s)
                ON CONFLICT (exact_query_hash) DO UPDATE SET
                    public_query_text = EXCLUDED.public_query_text,
                    condition_fingerprint = EXCLUDED.condition_fingerprint,
                    public_answer = EXCLUDED.public_answer,
                    evidence_ids = EXCLUDED.evidence_ids,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_revision = EXCLUDED.embedding_revision,
                    dimensions = EXCLUDED.dimensions,
                    llm_model = EXCLUDED.llm_model,
                    prompt_version = EXCLUDED.prompt_version,
                    tool_schema_version = EXCLUDED.tool_schema_version,
                    safety_policy_version = EXCLUDED.safety_policy_version,
                    embedding = EXCLUDED.embedding,
                    created_at = EXCLUDED.created_at,
                    valid_until = EXCLUDED.valid_until,
                    invalidated_at = NULL,
                    quality_passed = true,
                    reusable = true,
                    answer_hash = EXCLUDED.answer_hash
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
                    Jsonb(evidence_ids),
                    get_settings().llm_model,
                    PROMPT_VERSION,
                    TOOL_SCHEMA_VERSION,
                    SAFETY_POLICY_VERSION,
                    now,
                    valid_until,
                    "public_api",
                    digest,
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("cache store failed", error_type=type(exc).__name__)
        return False


def response_cache_singleflight(
    spec: dict[str, Any], safe_text: str, *, checkpoint: Callable[[], None] | None = None
) -> AbstractContextManager[None]:
    from gosari.cache.public_source import public_cache_singleflight

    return public_cache_singleflight(
        exact_query_hash(safe_text, condition_fingerprint(spec)),
        namespace="response",
        checkpoint=checkpoint,
    )
