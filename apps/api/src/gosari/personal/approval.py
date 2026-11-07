"""SRS §12.1 공통 승인 프로토콜: preview → 사용자 확인 → consent → commit.

모델은 consent 발급 경로를 호출할 수 없다. commit은 서버가 보관한 승인된
preview의 payload만 사용하며 클라이언트 새 payload를 받지 않는다.
"""

import hashlib
import json
import unicodedata
from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta
from typing import Any

from gosari.config import get_settings
from gosari.domain.errors import GosariError
from gosari.personal import ActionResult, Consent, Preview
from gosari.sessions import Session, get_session_store, new_id, utcnow

CANONICAL_SCHEMA_VERSION = "canonical-v1"


def canonical_json(payload: dict[str, Any]) -> str:
    """키 순서·Unicode 정규화·숫자 표현을 버전으로 고정한다."""
    normalized = json.loads(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
        parse_float=lambda s: str(s),
    )
    text = json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return unicodedata.normalize("NFC", text)


def preview_hash(
    action: str,
    target_id: str,
    target_revision: int,
    schema_version: str,
    payload: dict[str, Any],
) -> str:
    body = canonical_json(
        {
            "action": action,
            "target_id": target_id,
            "target_revision": target_revision,
            "schema_version": schema_version,
            "canonical_payload": payload,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def command_hash(consent_id: str, preview: Preview) -> str:
    body = canonical_json(
        {
            "consent_id": consent_id,
            "action": preview.action,
            "target_id": preview.target_id,
            "target_revision": preview.expected_revision,
            "preview_hash": preview.preview_hash,
        }
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def create_preview(
    session: Session,
    action: str,
    target_id: str | None,
    expected_revision: int,
    schema_version: str,
    payload: dict[str, Any],
    display_payload: dict[str, Any] | None = None,
) -> Preview:
    settings = get_settings()
    with session.lock:
        session.touch()
        resolved_target = target_id or new_id("draft")
        digest = preview_hash(action, resolved_target, expected_revision, schema_version, payload)
        now = utcnow()
        preview = Preview(
            preview_id=new_id("preview"),
            action=action,
            target_id=resolved_target,
            expected_revision=expected_revision,
            schema_version=schema_version,
            canonical_payload=payload,
            display_payload=display_payload if display_payload is not None else payload,
            preview_hash=digest,
            created_at=now,
            expires_at=now + timedelta(seconds=settings.preview_ttl),
        )
        session.previews[preview.preview_id] = preview
        try:
            get_session_store().save(session)
        except Exception:
            del session.previews[preview.preview_id]
            raise
        return preview


def issue_consent(
    session: Session, preview_id: str, hash_from_client: str, decision: str
) -> Consent:
    """사용자 UI 경로만 호출 가능. 해시·만료·소유권을 검사한다."""
    settings = get_settings()
    if decision != "confirm":
        raise GosariError("INVALID_INPUT")
    with session.lock:
        session.touch()
        preview = session.previews.get(preview_id)
        if preview is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        if utcnow() > preview.expires_at:
            raise GosariError("PREVIEW_EXPIRED")
        if preview.preview_hash != hash_from_client:
            raise GosariError("PREVIEW_MISMATCH")
        if preview.state not in ("preview", "confirmed"):
            raise GosariError("ACTION_NOT_ALLOWED")
        now = utcnow()
        consent = Consent(
            consent_id=new_id("consent"),
            preview_id=preview.preview_id,
            action=preview.action,
            target_id=preview.target_id,
            target_revision=preview.expected_revision,
            preview_hash=preview.preview_hash,
            issued_at=now,
            expires_at=now + timedelta(seconds=settings.consent_ttl),
        )
        preview.state = "confirmed"
        session.consents[consent.consent_id] = consent
        try:
            get_session_store().save(session)
        except Exception:
            del session.consents[consent.consent_id]
            preview.state = "preview"
            raise
        return consent


Executor = Callable[[Session, Preview], tuple[str, int]]


def commit(
    session: Session,
    consent_id: str,
    preview_id: str,
    action: str,
    target_id: str,
    target_revision: int,
    hash_from_client: str,
    executor: Executor,
) -> ActionResult:
    with session.lock:
        session.touch()
        consent = session.consents.get(consent_id)
        if consent is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        preview = session.previews.get(preview_id)
        if preview is None:
            raise GosariError("RESOURCE_NOT_FOUND")

        if (
            consent.preview_id != preview_id
            or consent.action != action
            or consent.target_id != target_id
            or consent.target_revision != target_revision
            or consent.preview_hash != hash_from_client
            or preview.preview_hash != hash_from_client
            or preview.action != action
            or preview.target_id != target_id
            or preview.expected_revision != target_revision
        ):
            raise GosariError("PREVIEW_MISMATCH")

        cmd_hash = command_hash(consent_id, preview)
        # 이미 성공한 동일 명령은 기존 결과만 반환 — 변경을 다시 실행하지 않는다.
        for existing in session.actions.values():
            if existing.consent_id == consent_id and existing.canonical_command_hash == cmd_hash:
                if existing.state == "committed":
                    return existing
                raise GosariError("ACTION_NOT_ALLOWED", {"reason": "PREVIOUS_ATTEMPT_FAILED"})

        if consent.used:
            raise GosariError("CONSENT_REUSED_DIFFERENTLY")
        if utcnow() > consent.expires_at or utcnow() > preview.expires_at:
            raise GosariError("PREVIEW_EXPIRED")

        collections = (
            "notebook",
            "contacts",
            "regions",
            "share_drafts",
            "previews",
            "consents",
            "actions",
        )
        before = {name: deepcopy(getattr(session, name)) for name in collections}
        consent.used = True
        try:
            result_id, resulting_revision = executor(session, preview)
            result = ActionResult(
                action_id=new_id("action"),
                consent_id=consent_id,
                canonical_command_hash=cmd_hash,
                state="committed",
                result_id=result_id,
                resulting_revision=resulting_revision,
                committed_at=utcnow(),
            )
            session.actions[result.action_id] = result
            preview.state = "committed"
            get_session_store().save(session)
        except GosariError as exc:
            for name, value in before.items():
                setattr(session, name, value)
            if exc.code == "DATABASE_UNAVAILABLE":
                raise
            failure = ActionResult(
                action_id=new_id("action"),
                consent_id=consent_id,
                canonical_command_hash=cmd_hash,
                state="failed",
                safe_error=exc.code,
            )
            session.actions[failure.action_id] = failure
            session.previews[preview_id].state = "failed"
            session.consents[consent_id].used = True
            raise
        except Exception:
            for name, value in before.items():
                setattr(session, name, value)
            raise
        return result
