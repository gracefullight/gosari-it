"""개인 지인 목록과 관계 관리. 나눔 이력의 이름 스냅샷은 변경하지 않는다."""

from typing import Any

from gosari.domain.errors import GosariError
from gosari.personal import PersonalContact, Preview
from gosari.personal.approval import create_preview
from gosari.sessions import Session, utcnow

RELATIONSHIPS = {"가족", "친척", "친구", "이웃", "동료", "기타"}
SCHEMA_VERSION = "contact-v1"


def _validate(payload: dict[str, Any]) -> dict[str, str]:
    name = payload.get("name")
    relationship = payload.get("relationship", "기타")
    notes = payload.get("notes", "")
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise GosariError("INVALID_INPUT", {"fields": ["name"]})
    if not isinstance(relationship, str) or relationship not in RELATIONSHIPS:
        raise GosariError("INVALID_INPUT", {"fields": ["relationship"]})
    if not isinstance(notes, str) or len(notes) > 2000:
        raise GosariError("INVALID_INPUT", {"fields": ["notes"]})
    return {"name": name.strip(), "relationship": relationship, "notes": notes.strip()}


def prepare_create(session: Session, payload: dict[str, Any]) -> Preview:
    return create_preview(session, "contact.create", None, 0, SCHEMA_VERSION, _validate(payload))


def prepare_update(session: Session, contact_id: str, payload: dict[str, Any]) -> Preview:
    with session.lock:
        contact = session.contacts.get(contact_id)
        if contact is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        merged = _validate({**contact.model_dump(), **payload})
        return create_preview(
            session, "contact.update", contact_id, contact.revision, SCHEMA_VERSION, merged
        )


def prepare_delete(session: Session, contact_id: str) -> Preview:
    with session.lock:
        contact = session.contacts.get(contact_id)
        if contact is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return create_preview(
            session,
            "contact.delete",
            contact_id,
            contact.revision,
            SCHEMA_VERSION,
            {"contact_id": contact_id},
            display_payload={"name": contact.name, "relationship": contact.relationship},
        )


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    now = utcnow()
    if preview.action == "contact.create":
        contact = PersonalContact(
            contact_id=preview.target_id,
            created_at=now,
            updated_at=now,
            **_validate(preview.canonical_payload),
        )
        session.contacts[contact.contact_id] = contact
        return contact.contact_id, contact.revision
    if preview.action not in {"contact.update", "contact.delete"}:
        raise GosariError("ACTION_NOT_ALLOWED")
    contact = session.contacts.get(preview.target_id)
    if contact is None:
        raise GosariError("RESOURCE_NOT_FOUND")
    if contact.revision != preview.expected_revision:
        raise GosariError("REVISION_CONFLICT")
    if preview.action == "contact.delete":
        del session.contacts[contact.contact_id]
        return contact.contact_id, contact.revision
    updated = contact.model_copy(
        update={
            **_validate(preview.canonical_payload),
            "revision": contact.revision + 1,
            "updated_at": now,
        }
    )
    session.contacts[updated.contact_id] = updated
    return updated.contact_id, updated.revision
