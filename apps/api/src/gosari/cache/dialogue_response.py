"""One public dialogue answer row: exact digest, guarded cosine, shared lifetime."""

import copy
import json
import math
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from gosari.agent.dialogue_privacy import requires_private_dialogue
from gosari.cache import semantic
from gosari.cache.dialogue_guards import (
    GUARD_VERSION,
    context_hash,
    guard_fingerprint,
    normalize_text,
)
from gosari.cache.embeddings import DIMENSIONS, MAX_TOKENS, get_engine
from gosari.cache.public_source import (
    PARSER_VERSION,
    SCHEMA_VERSION,
    SOURCE_VERSION,
    public_payload,
)
from gosari.config import get_settings
from gosari.db import connection, db_available
from gosari.domain import CacheResolution
from gosari.domain.envelope import ResultEnvelope
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)
NAMESPACE = "dialogue-response-v2"
KOREA = ZoneInfo("Asia/Seoul")
_DIALOGUE_PRIVATE_FIELDS = frozenset(
    {
        "question",
        "original_question",
        "user_question",
        "history",
        "messages",
        "dialogue_messages",
        "conversation_id",
    }
)


def _public_answer(value: Any) -> bool:
    if isinstance(value, dict):
        return not _DIALOGUE_PRIVATE_FIELDS.intersection(value) and all(
            _public_answer(item) for item in value.values()
        )
    if isinstance(value, list):
        return all(_public_answer(item) for item in value)
    return True


def _canonical(specs: Any) -> list[dict[str, Any]] | None:
    if not isinstance(specs, list) or not 1 <= len(specs) <= 8:
        return None
    try:
        result = [semantic.canonical_public_spec(spec) for spec in specs]
        if not all(spec.get("source_ids") for spec in result):
            return None
        json.dumps(result, allow_nan=False)
        return result
    except Exception:
        return None


def lifespan(specs: list[dict[str, Any]], now: datetime) -> datetime:
    """Shortest result lifetime, bounded by the next Korean calendar day."""
    seconds = min(
        300
        if spec.get("operation") == "outing_compare"
        else 900
        if spec.get("operation") in {"current_observation", "forecast_compare"}
        else 1800
        for spec in specs
    )
    tomorrow = now.astimezone(KOREA).date() + timedelta(days=1)
    midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KOREA)
    return min(now + timedelta(seconds=seconds), midnight)


def _key(
    question: str, history: list[dict[str, Any]], now: datetime
) -> tuple[str, str, dict[str, Any], str | None] | None:
    settings = get_settings()
    if (
        not settings.response_cache_enabled
        or not isinstance(question, str)
        or not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        return None
    normalized = normalize_text(question)
    if (
        not normalized
        or len(normalized) > settings.max_text_length
        or requires_private_dialogue(normalized)
    ):
        return None
    context = context_hash(history)
    if context is None:
        return None
    digest = json_hash({"question": normalized})
    guard = guard_fingerprint(normalized, now=now)
    scope = {
        "namespace": NAMESPACE,
        "context_hash": context,
        "kst_date": now.astimezone(KOREA).date().isoformat(),
        "guard_version": GUARD_VERSION,
        "guard_hash": guard or json_hash({"exact_only": digest}),
        "fingerprint_version": semantic.FINGERPRINT_VERSION,
        "calculation_version": semantic.CALCULATION_VERSION,
        "prompt_version": semantic.PROMPT_VERSION,
        "tool_schema_version": semantic.TOOL_SCHEMA_VERSION,
        "safety_policy_version": semantic.SAFETY_POLICY_VERSION,
        "source_parser_version": PARSER_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "source_version": SOURCE_VERSION,
        "profile": settings.app_profile,
        "external_requests": settings.external_requests_enabled,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model_path,
        "embedding_revision": settings.embedding_revision,
    }
    fingerprint = json_hash(scope)
    exact = json_hash(
        {"namespace": NAMESPACE, "fingerprint": fingerprint, "question_digest": digest}
    )
    return fingerprint, exact, scope, guard


def _answer_ok(answer: Any, specs: list[dict[str, Any]], evidence_ids: Any) -> bool:
    if (
        not isinstance(answer, dict)
        or not answer.get("result")
        or not isinstance(answer.get("assistant_text"), str)
        or not answer["assistant_text"].strip()
        or not isinstance(evidence_ids, list)
        or not evidence_ids
        or not all(isinstance(value, str) and value for value in evidence_ids)
        or not semantic.result_cacheable(answer)
        or not public_payload(answer)
        or not _public_answer(answer)
        or answer.get("personal_search")
        or answer.get("personal_form")
    ):
        return False
    try:
        primary = ResultEnvelope.model_validate(answer)
        if not primary.evidence_ids or not set(primary.evidence_ids).issubset(evidence_ids):
            return False
        tools = answer.get("dialogue_tool_results")
        if tools is None:
            if (
                len(specs) != 1
                or semantic.canonical_public_spec(primary.requested_scope) != specs[0]
            ):
                return False
        else:
            if not isinstance(tools, list) or len(tools) != len(specs):
                return False
            for spec, tool in zip(specs, tools, strict=True):
                if (
                    not isinstance(tool, dict)
                    or set(tool) != {"spec", "envelope"}
                    or semantic.canonical_public_spec(tool["spec"]) != spec
                    or not semantic.result_cacheable(tool["envelope"])
                ):
                    return False
                envelope = ResultEnvelope.model_validate(tool["envelope"])
                if (
                    not envelope.evidence_ids
                    or semantic.canonical_public_spec(envelope.requested_scope) != spec
                    or not set(envelope.evidence_ids).issubset(evidence_ids)
                ):
                    return False
        if answer.get("ui_spec") is not None or answer.get("ui_results"):
            from gosari.agent.ui import restore_ui

            restored, results = restore_ui(answer.get("ui_spec"), answer.get("ui_results"))
            if restored is None or not all(
                semantic.result_cacheable(value.model_dump(mode="json"))
                and value.evidence_ids
                and set(value.evidence_ids).issubset(evidence_ids)
                for value in results.values()
            ):
                return False
        if "dialogue_continuation" in answer:
            continuation = answer["dialogue_continuation"]
            if (
                not isinstance(continuation, list)
                or not continuation
                or any(
                    not isinstance(message, dict)
                    or message.get("role") not in {"assistant", "tool"}
                    for message in continuation
                )
                or context_hash(continuation) is None
            ):
                return False
        json.dumps(answer, allow_nan=False)
        return True
    except Exception:
        return False


def _verified(
    row: Any, fingerprint: str, scope: dict[str, Any], now: datetime
) -> dict[str, Any] | None:
    if not row or len(row) < 5:
        return None
    _, payload, evidence, expires, digest = row[:5]
    if (
        not isinstance(expires, datetime)
        or expires.tzinfo is None
        or expires <= now
        or not isinstance(payload, dict)
        or set(payload) != {"kind", "scope", "specs", "answer"}
        or payload.get("kind") != NAMESPACE
        or payload.get("scope") != scope
        or digest != semantic.answer_integrity(payload, evidence, fingerprint)
    ):
        return None
    specs = _canonical(payload["specs"])
    if (
        specs is None
        or specs != payload["specs"]
        or not _answer_ok(payload["answer"], specs, evidence)
    ):
        return None
    return copy.deepcopy({"specs": specs, "answer": payload["answer"], "evidence_ids": evidence})


def _threshold() -> float | None:
    value = get_settings().domain_threshold_config
    try:
        configured = float(value) if value else None
        if configured is None or not math.isfinite(configured) or configured >= 1:
            return None
        return max(0.95, configured)
    except TypeError, ValueError:
        return None


def _vector(question: str) -> list[float] | None:
    engine = get_engine()
    count = engine.token_count(normalize_text(question))
    if not isinstance(count, int) or isinstance(count, bool) or not 0 < count <= MAX_TOKENS:
        return None
    values = engine.embed(normalize_text(question))
    if (
        values is None
        or len(values) != DIMENSIONS
        or not all(math.isfinite(value) for value in values)
        or not any(values)
    ):
        return None
    return values


_EXACT_SELECT = """SELECT cache_entry_id, public_answer, evidence_ids, valid_until, answer_hash
    FROM public_response_cache WHERE condition_fingerprint = %s AND exact_query_hash = %s
    AND reusable = true AND quality_passed = true AND rights_status = 'public_api'
    AND invalidated_at IS NULL AND valid_until > %s LIMIT 1"""
_CANDIDATE_EXISTS = """SELECT 1 FROM public_response_cache
    WHERE condition_fingerprint = %s AND embedding IS NOT NULL
    AND reusable = true AND quality_passed = true AND rights_status = 'public_api'
    AND invalidated_at IS NULL AND valid_until > %s LIMIT 1"""
_SEMANTIC_SELECT = """SELECT cache_entry_id, public_answer, evidence_ids, valid_until, answer_hash,
    1 - (embedding <=> %s::vector) AS similarity FROM public_response_cache
    WHERE condition_fingerprint = %s AND embedding IS NOT NULL
    AND reusable = true AND quality_passed = true AND rights_status = 'public_api'
    AND invalidated_at IS NULL AND valid_until > %s
    ORDER BY embedding <=> %s::vector LIMIT 5"""
_ENRICH_UPDATE = """UPDATE public_response_cache SET embedding = %s::vector
    WHERE cache_entry_id = %s AND answer_hash = %s
    AND reusable = true AND quality_passed = true AND rights_status = 'public_api'
    AND invalidated_at IS NULL AND valid_until > %s RETURNING cache_entry_id"""


def lookup_response(
    question: str, history: list[dict[str, Any]], *, now: datetime
) -> tuple[CacheResolution, dict[str, Any] | None]:
    key = _key(question, history, now)
    if key is None or not db_available():
        return CacheResolution.BYPASS, None
    fingerprint, exact, scope, guard = key
    try:
        with connection() as conn:
            row = conn.execute(
                _EXACT_SELECT,
                (fingerprint, exact, now),
            ).fetchone()
            payload = _verified(row, fingerprint, scope, now)
            resolution = CacheResolution.EXACT_HIT
            if payload is None:
                threshold = _threshold()
                if guard is None or threshold is None:
                    return CacheResolution.MISS, None
                existing = conn.execute(
                    _CANDIDATE_EXISTS,
                    (fingerprint, now),
                ).fetchone()
                if not existing:
                    return CacheResolution.MISS, None
                vector = _vector(question)
                if vector is None:
                    return CacheResolution.MISS, None
                rows = conn.execute(
                    _SEMANTIC_SELECT,
                    (vector, fingerprint, now, vector),
                ).fetchall()
                for candidate in rows:
                    similarity = candidate[5]
                    if (
                        not isinstance(similarity, (int, float))
                        or not math.isfinite(similarity)
                        or similarity <= threshold
                    ):
                        continue
                    payload = _verified(candidate, fingerprint, scope, now)
                    if payload is not None:
                        row = candidate
                        resolution = CacheResolution.SEMANTIC_HIT
                        break
                if payload is None:
                    return CacheResolution.MISS, None
            if row is None:
                return CacheResolution.MISS, None
            conn.execute(
                "UPDATE public_response_cache SET hit_count = hit_count + 1, last_used_at = %s "
                "WHERE cache_entry_id = %s",
                (now, row[0]),
            )
            conn.commit()
            return resolution, payload
    except Exception as exc:
        logger.warning("dialogue response lookup unavailable", error_type=type(exc).__name__)
        return CacheResolution.BYPASS, None


def store_response(
    question: str,
    history: list[dict[str, Any]],
    specs: list[dict[str, Any]],
    answer: dict[str, Any],
    evidence_ids: list[str],
    *,
    now: datetime,
    valid_until: datetime,
) -> bool:
    key = _key(question, history, now)
    canonical = _canonical(specs)
    if (
        key is None
        or canonical is None
        or not db_available()
        or not _answer_ok(answer, canonical, evidence_ids)
    ):
        return False
    try:
        fingerprint, exact, scope, _ = key
        expires = min(valid_until, lifespan(canonical, now))
        if expires <= now:
            return False
        payload = {"kind": NAMESPACE, "scope": scope, "specs": canonical, "answer": answer}
        digest = semantic.answer_integrity(payload, evidence_ids, fingerprint)
        settings = get_settings()
        with connection() as conn:
            conn.execute(
                """INSERT INTO public_response_cache
                (cache_entry_id, public_query_text, exact_query_hash, condition_fingerprint,
                 embedding, embedding_model, embedding_revision, dimensions, public_answer,
                 evidence_ids, llm_model, prompt_version, tool_schema_version,
                 safety_policy_version,
                 created_at, valid_until, quality_passed, reusable, rights_status, answer_hash)
                VALUES (%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,true,%s,%s)
                ON CONFLICT (exact_query_hash) DO UPDATE SET
                  public_answer=EXCLUDED.public_answer, evidence_ids=EXCLUDED.evidence_ids,
                  embedding=NULL, embedding_model=EXCLUDED.embedding_model,
                  embedding_revision=EXCLUDED.embedding_revision, dimensions=EXCLUDED.dimensions,
                  created_at=EXCLUDED.created_at, valid_until=EXCLUDED.valid_until,
                  answer_hash=EXCLUDED.answer_hash, invalidated_at=NULL,
                  quality_passed=true,reusable=true,rights_status=EXCLUDED.rights_status""",
                (
                    f"dlg-{exact[:24]}",
                    NAMESPACE,
                    exact,
                    fingerprint,
                    settings.embedding_model_path,
                    settings.embedding_revision,
                    DIMENSIONS,
                    Jsonb(payload),
                    Jsonb(evidence_ids),
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
        logger.warning("dialogue response store unavailable", error_type=type(exc).__name__)
        return False


def enrich_response_embedding(
    question: str, history: list[dict[str, Any]], *, now: datetime
) -> bool:
    """Call from the caller's bounded background worker, never the SSE completion path."""
    key = _key(question, history, now)
    if key is None or key[3] is None or not db_available() or _threshold() is None:
        return False
    fingerprint, exact, scope, _ = key
    try:
        with connection() as conn:
            row = conn.execute(
                _EXACT_SELECT,
                (fingerprint, exact, now),
            ).fetchone()
        if row is None or _verified(row, fingerprint, scope, now) is None:
            return False
        started = time.monotonic()
        vector = _vector(question)
        if vector is None:
            return False
        current = now + timedelta(seconds=time.monotonic() - started)
        with connection() as conn:
            changed = conn.execute(
                _ENRICH_UPDATE,
                (vector, row[0], row[4], current),
            ).fetchone()
            conn.commit()
        return changed is not None
    except Exception as exc:
        logger.warning("dialogue response embedding unavailable", error_type=type(exc).__name__)
        return False
