"""Shared, normalized public tool results; never personal/session payloads."""

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from psycopg.types.json import Jsonb

from gosari.cache.semantic import canonical_public_spec, result_cacheable
from gosari.config import get_settings
from gosari.db import connection, db_available
from gosari.domain.errors import GosariError
from gosari.logging import get_logger
from gosari.sources import json_hash

logger = get_logger(__name__)
PARSER_VERSION = "normalized-public-v1"
SCHEMA_VERSION = "source-cache-v1"
SOURCE_VERSION = "public-tools-v1"
_STRIPES = tuple(threading.RLock() for _ in range(64))
_LOCK_CONNECTION = threading.local()
PRIVATE_FIELDS = frozenset(
    {
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
        "personal_records",
        "conversation_history",
        "api_key",
        "serviceKey",
        "projectKey",
        "authKey",
        "password",
    }
)


def public_payload(value: Any) -> bool:
    if isinstance(value, dict):
        return not PRIVATE_FIELDS.intersection(value) and all(
            public_payload(item) for item in value.values()
        )
    if isinstance(value, list):
        return all(public_payload(item) for item in value)
    return True


def source_key(spec: dict[str, Any]) -> str:
    canonical = canonical_public_spec(spec)
    settings = get_settings()
    return json_hash(
        {
            "spec": canonical,
            "parser": PARSER_VERSION,
            "schema": SCHEMA_VERSION,
            "source_version": SOURCE_VERSION,
            "profile": settings.app_profile,
            "external_requests": settings.external_requests_enabled,
        }
    )


def _metadata_ok(manifests: list[dict[str, Any]]) -> bool:
    if not manifests:
        return False
    for source in manifests:
        if source.get("transport_status") != "ok" or source.get("failed_scope"):
            return False
        if source.get("rights_status") != "public_api":
            return False
        if source.get("source_mode") not in {"fetched", "cache", "replay"}:
            return False
        if (
            source.get("source_mode") == "replay"
            and get_settings().external_requests_enabled
            and get_settings().app_profile != "replay"
        ):
            return False
    # A paginated source must include its final page before being reusable.
    for source in manifests:
        if source.get("has_more") is True:
            matches = [
                row
                for row in manifests
                if all(
                    row.get(key) == source.get(key)
                    for key in ("source_id", "dataset_id", "operation")
                )
            ]
            if not any(
                row.get("has_more") is False
                and (row.get("page_number") or 0) > (source.get("page_number") or 0)
                for row in matches
            ):
                return False
    return public_payload(manifests)


def get_source_result(
    spec: dict[str, Any], *, now: datetime | None = None
) -> dict[str, Any] | None:
    if not get_settings().response_cache_enabled or not db_available():
        return None
    try:
        key = source_key(spec)
        with connection() as conn:
            row = conn.execute(
                """
                SELECT normalized_result, source_manifests, content_hash, parser_version,
                       schema_version, source_version
                FROM public_source_cache WHERE cache_key = %s AND valid_until > %s
                  AND quality_passed = true AND invalidated_at IS NULL
            """,
                (key, now or datetime.now(UTC)),
            ).fetchone()
            if not row:
                return None
            payload, manifests, digest, parser, schema, version = row
            if not isinstance(payload, dict) or not isinstance(manifests, list):
                return None
            if (parser, schema, version) != (PARSER_VERSION, SCHEMA_VERSION, SOURCE_VERSION):
                return None
            expected = json_hash({"key": key, "result": payload, "manifests": manifests})
            if (
                digest != expected
                or not result_cacheable(payload)
                or not public_payload(payload)
                or not _metadata_ok(manifests)
            ):
                return None
            conn.execute(
                "UPDATE public_source_cache SET hit_count = hit_count + 1, "
                "last_used_at = %s WHERE cache_key = %s",
                (now or datetime.now(UTC), key),
            )
            conn.commit()
            return cast(dict[str, Any], payload)
    except Exception as exc:
        logger.warning("public source cache lookup unavailable", error_type=type(exc).__name__)
        return None


def put_source_result(
    spec: dict[str, Any],
    envelope: Any,
    *,
    ttl_seconds: int = 300,
    valid_until: datetime | None = None,
    source_manifests: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> bool:
    if not get_settings().response_cache_enabled or not db_available():
        return False
    try:
        key = source_key(spec)
        payload = envelope.model_dump(mode="json") if hasattr(envelope, "model_dump") else envelope
        if (
            not isinstance(payload, dict)
            or not result_cacheable(payload)
            or not public_payload(payload)
        ):
            return False
        # Serialization rejects NaN/Infinity rather than persisting unusable JSON.
        payload = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str))
        manifests: list[dict[str, Any]] = (
            list(source_manifests) if source_manifests is not None else []
        )
        if source_manifests is None:
            from gosari.agent.analysis import get_evidence_store

            for evidence_id in payload.get("evidence_ids", []):
                evidence = get_evidence_store().get(evidence_id)
                if not evidence:
                    return False
                manifests.extend(evidence.get("source_manifests", []))
        if not _metadata_ok(manifests):
            return False
        created = now or datetime.now(UTC)
        expires = min(
            valid_until or created + timedelta(seconds=ttl_seconds),
            created + timedelta(seconds=max(0, min(ttl_seconds, 1800))),
        )
        if expires <= created:
            return False
        digest = json_hash({"key": key, "result": payload, "manifests": manifests})
        with connection() as conn:
            conn.execute(
                """
                INSERT INTO public_source_cache (
                    cache_key, public_query_spec, normalized_result, source_manifests,
                    observed_period, content_hash, parser_version, schema_version,
                    source_version, created_at, valid_until, quality_passed
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)
                ON CONFLICT (cache_key) DO UPDATE SET
                    public_query_spec=EXCLUDED.public_query_spec,
                    normalized_result=EXCLUDED.normalized_result,
                    source_manifests=EXCLUDED.source_manifests,
                    parser_version=EXCLUDED.parser_version,
                    schema_version=EXCLUDED.schema_version,
                    source_version=EXCLUDED.source_version,
                    observed_period=EXCLUDED.observed_period,
                    content_hash=EXCLUDED.content_hash, created_at=EXCLUDED.created_at,
                    valid_until=EXCLUDED.valid_until, quality_passed=true, invalidated_at=NULL
            """,
                (
                    key,
                    Jsonb(canonical_public_spec(spec)),
                    Jsonb(payload),
                    Jsonb(manifests),
                    Jsonb(payload.get("observed_period", {})),
                    digest,
                    PARSER_VERSION,
                    SCHEMA_VERSION,
                    SOURCE_VERSION,
                    created,
                    expires,
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("public source cache store unavailable", error_type=type(exc).__name__)
        return False


@contextmanager
def public_cache_singleflight(
    key: str, *, namespace: str = "source", checkpoint: Callable[[], None] | None = None
) -> Iterator[None]:
    """One lock connection per thread, reused for nested source/response scopes."""
    digest = json_hash({"namespace": namespace, "key": key})
    number = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
    deadline = time.monotonic() + max(1, get_settings().job_deadline)

    def check() -> None:
        if checkpoint:
            checkpoint()
        if time.monotonic() >= deadline:
            raise GosariError("LOCAL_BUSY")

    @contextmanager
    def hold(conn: Any) -> Iterator[None]:
        while True:
            acquired = conn.execute("SELECT pg_try_advisory_lock(%s)", (number,)).fetchone()
            if acquired and acquired[0]:
                break
            check()
            time.sleep(0.05)
        try:
            check()
            yield
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (number,))

    existing = getattr(_LOCK_CONNECTION, "current", None)
    if existing is not None:
        # Child locks are released at the child boundary, avoiding lock-order
        # cycles across several tool calls while retaining the outer response lock.
        with hold(existing):
            yield
        return
    lock = _STRIPES[int(digest[:8], 16) % len(_STRIPES)]
    while not lock.acquire(timeout=0.1):
        check()
    try:
        check()
        if not db_available():
            yield
            return
        with connection() as conn:
            _LOCK_CONNECTION.current = conn
            try:
                with hold(conn):
                    yield
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                del _LOCK_CONNECTION.current
    finally:
        lock.release()


@contextmanager
def public_source_singleflight(
    spec: dict[str, Any], *, checkpoint: Callable[[], None] | None = None
) -> Iterator[None]:
    with public_cache_singleflight(source_key(spec), checkpoint=checkpoint):
        yield
