"""Exact first-turn public plan index; questions and answers are never stored here."""

import hashlib
import json
import unicodedata
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from gosari.agent.dialogue_privacy import requires_private_dialogue
from gosari.cache import semantic
from gosari.config import get_settings
from gosari.db import connection, db_available
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)
PLAN_INDEX_VERSION = "dialogue-plan-index-v1"
KOREA = ZoneInfo("Asia/Seoul")
TIME_SENSITIVE_OPERATIONS = frozenset({"current_observation", "forecast_compare", "outing_compare"})


def _scope(now: datetime) -> dict[str, Any]:
    from gosari.cache.public_source import PARSER_VERSION, SCHEMA_VERSION, SOURCE_VERSION

    settings = get_settings()
    return {
        "index_version": PLAN_INDEX_VERSION,
        "kst_date": now.astimezone(KOREA).date().isoformat(),
        "fingerprint_version": semantic.FINGERPRINT_VERSION,
        "calculation_version": semantic.CALCULATION_VERSION,
        "prompt_version": semantic.PROMPT_VERSION,
        "tool_schema_version": semantic.TOOL_SCHEMA_VERSION,
        "safety_policy_version": semantic.SAFETY_POLICY_VERSION,
        "source_parser_version": PARSER_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "source_version": SOURCE_VERSION,
        "runtime_profile": settings.app_profile,
        "external_requests": settings.external_requests_enabled,
        "llm_model": settings.llm_model,
        "embedding_config_hash": json_hash(
            {
                "model": settings.embedding_model_path,
                "revision": settings.embedding_revision,
            }
        ),
    }


def _key(
    question: str, context_hash: str | None, now: datetime
) -> tuple[str, str, dict[str, Any]] | None:
    settings = get_settings()
    if (
        context_hash is not None
        or not settings.response_cache_enabled
        or not isinstance(question, str)
        or not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        return None
    normalized = unicodedata.normalize("NFC", question.strip())
    if (
        not normalized
        or len(normalized) > settings.max_text_length
        or requires_private_dialogue(normalized)
    ):
        return None
    scope = _scope(now)
    fingerprint = json_hash({"namespace": PLAN_INDEX_VERSION, "scope": scope})
    digest = hashlib.sha256(f"{PLAN_INDEX_VERSION}\0{normalized}".encode()).hexdigest()
    exact = json_hash({"fingerprint": fingerprint, "question_digest": digest})
    return fingerprint, exact, scope


def _canonical(specs: Any) -> list[dict[str, Any]] | None:
    if not isinstance(specs, list) or len(specs) != 1 or not isinstance(specs[0], dict):
        return None
    try:
        plan = semantic.canonical_public_spec(specs[0])
        if not plan.get("operation") or not plan.get("source_ids"):
            return None
        # No serializers, NaN, arbitrary objects, or private fields enter the DB payload.
        return cast(
            list[dict[str, Any]],
            json.loads(json.dumps([plan], ensure_ascii=False, allow_nan=False)),
        )
    except Exception:
        return None


def read_plan(
    question: str,
    context_hash: str | None = None,
    *,
    now: datetime,
) -> list[dict[str, Any]] | None:
    """Only a context-free exact question can recover a validated public spec.

    The caller must still use semantic.lookup with canonical spec JSON and verify
    a complete response hit; a plan-index hit is never an answer-cache hit.
    """
    try:
        key = _key(question, context_hash, now)
        if key is None or not db_available():
            return None
        fingerprint, exact, scope = key
        with connection() as conn:
            row = conn.execute(
                """
                SELECT public_answer, valid_until, answer_hash
                FROM public_response_cache
                WHERE condition_fingerprint = %s AND exact_query_hash = %s
                  AND reusable = true AND quality_passed = true
                  AND rights_status = 'public_api' AND invalidated_at IS NULL
                  AND valid_until > %s
                LIMIT 1
                """,
                (fingerprint, exact, now),
            ).fetchone()
            if not row:
                return None
            payload, expires, digest = row
            if (
                not isinstance(payload, dict)
                or payload.get("kind") != PLAN_INDEX_VERSION
                or payload.get("scope") != scope
                or not isinstance(expires, datetime)
                or expires.tzinfo is None
                or expires <= now
                or digest != semantic.answer_integrity(payload, [], fingerprint)
            ):
                return None
            plans = _canonical(payload.get("specs"))
            if plans is None or plans != payload.get("specs"):
                return None
            conn.execute(
                "UPDATE public_response_cache SET hit_count = hit_count + 1, "
                "last_used_at = %s WHERE exact_query_hash = %s AND condition_fingerprint = %s",
                (now, exact, fingerprint),
            )
            conn.commit()
            return plans
    except Exception as exc:
        logger.warning("dialogue plan index unavailable", error_type=type(exc).__name__)
        return None


def store_plan(
    question: str,
    specs: list[dict[str, Any]],
    context_hash: str | None = None,
    *,
    now: datetime,
    valid_until: datetime | None = None,
) -> bool:
    """Call only after a verified complete, single-tool, fresh public response.

    Existing JSON columns hold only canonical public conditions and a digest key.
    The intentionally non-answer payload and empty evidence list cannot be reused
    by the ordinary response cache's result_cacheable/evidence checks.
    """
    try:
        key = _key(question, context_hash, now)
        plans = _canonical(specs)
        if key is None or plans is None or not db_available():
            return False
        fingerprint, exact, scope = key
        ttl = 60 if plans[0]["operation"] in TIME_SENSITIVE_OPERATIONS else 1800
        tomorrow = now.astimezone(KOREA).date() + timedelta(days=1)
        midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KOREA)
        expires = min(
            valid_until or now + timedelta(seconds=ttl), now + timedelta(seconds=ttl), midnight
        )
        if expires <= now:
            return False
        payload = {"kind": PLAN_INDEX_VERSION, "scope": scope, "specs": plans}
        digest = semantic.answer_integrity(payload, [], fingerprint)
        settings = get_settings()
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
                    public_query_text=EXCLUDED.public_query_text,
                    condition_fingerprint=EXCLUDED.condition_fingerprint,
                    public_answer=EXCLUDED.public_answer,
                    evidence_ids=EXCLUDED.evidence_ids,
                    embedding=NULL,
                    embedding_model=EXCLUDED.embedding_model,
                    embedding_revision=EXCLUDED.embedding_revision,
                    llm_model=EXCLUDED.llm_model,
                    prompt_version=EXCLUDED.prompt_version,
                    tool_schema_version=EXCLUDED.tool_schema_version,
                    safety_policy_version=EXCLUDED.safety_policy_version,
                    created_at=EXCLUDED.created_at, valid_until=EXCLUDED.valid_until,
                    quality_passed=true, reusable=true, invalidated_at=NULL,
                    rights_status=EXCLUDED.rights_status, answer_hash=EXCLUDED.answer_hash
                """,
                (
                    f"plan-{exact[:24]}",
                    PLAN_INDEX_VERSION,
                    exact,
                    fingerprint,
                    None,
                    "none-dialogue-plan",
                    PLAN_INDEX_VERSION,
                    384,
                    Jsonb(payload),
                    Jsonb([]),
                    settings.llm_model,
                    semantic.PROMPT_VERSION,
                    semantic.TOOL_SCHEMA_VERSION,
                    semantic.SAFETY_POLICY_VERSION,
                    now,
                    expires,
                    "public_api",
                    digest,
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("dialogue plan index store unavailable", error_type=type(exc).__name__)
        return False
