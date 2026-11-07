"""가족·지인 나눔 — 대상·분량·시점 정리와 로컬 문구 (SRS §5.6). 실제 전송 도구 없음."""

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from gosari.domain.errors import GosariError
from gosari.personal import Preview, ShareDraft, ShareItem
from gosari.personal.approval import create_preview
from gosari.sessions import Session, utcnow

SCHEMA_VERSION = "share-v1"


def _validate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise GosariError("INVALID_INPUT", {"fields": ["items"]})
    for item in items:
        if not item.get("recipient_alias"):
            raise GosariError("INVALID_INPUT", {"fields": ["items[].recipient_alias"]})
        if item.get("amount_value") is None or not item.get("amount_unit"):
            raise GosariError("UNIT_UNRESOLVED")
        try:
            Decimal(str(item["amount_value"]))
        except InvalidOperation:
            raise GosariError("INVALID_INPUT", {"fields": ["items[].amount_value"]}) from None
    return items


def build_message(items: list[ShareItem]) -> str:
    """로컬 템플릿 문구. 개인 원문은 외부 모델로 보내지 않는다."""
    lines = ["고사리 나눌 계획이에요."]
    for item in items:
        amount = (
            f"{item.amount_value.normalize():f}"
            if item.amount_value == item.amount_value.to_integral_value()
            else str(item.amount_value)
        )
        line = f"- {item.recipient_alias}: {amount}{item.amount_unit}"
        if item.planned_delivery:
            line += f" ({item.planned_delivery})"
        lines.append(line)
    return "\n".join(lines)


def summarize_totals(items: list[ShareItem]) -> dict[str, str]:
    """SRS FR-SHARE-002: 같은 단위끼리만 합산하며 서로 다른 단위를 임의 환산하지 않는다."""
    totals: dict[str, Decimal] = {}
    for item in items:
        totals[item.amount_unit] = totals.get(item.amount_unit, Decimal(0)) + item.amount_value
    formatted: dict[str, str] = {}
    for unit, total in totals.items():
        formatted[unit] = (
            f"{total.normalize():f}" if total == total.to_integral_value() else str(total)
        )
    return formatted


def _reference_ids(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise GosariError("INVALID_INPUT", {"fields": [field]})
    return list(dict.fromkeys(value))


def prepare(
    session: Session,
    payload: dict[str, Any],
    action: str = "save",
    share_draft_id: str | None = None,
) -> tuple[Preview, dict[str, Any]]:
    if action not in {"save", "update", "delete"}:
        raise GosariError("ACTION_NOT_ALLOWED")
    existing = None
    if action != "save":
        existing = session.share_drafts.get(share_draft_id or "")
        if existing is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        expected_revision = payload.get("expected_revision")
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision != existing.revision
        ):
            raise GosariError("REVISION_CONFLICT")
        if action == "delete":
            display = {"items": [item.model_dump(mode="json") for item in existing.items]}
            preview = create_preview(
                session,
                "share.delete",
                existing.share_draft_id,
                existing.revision,
                SCHEMA_VERSION,
                {"share_draft_id": existing.share_draft_id},
                display_payload=display,
            )
            return preview, display
        payload = {**existing.model_dump(mode="json"), **payload}

    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list) or not all(isinstance(item, dict) for item in raw_items):
        raise GosariError("INVALID_INPUT", {"fields": ["items"]})
    items = []
    for raw in raw_items:
        item = dict(raw)
        contact_id = item.get("contact_id")
        if contact_id:
            contact = session.contacts.get(contact_id) if isinstance(contact_id, str) else None
            if contact is None:
                historical = existing is not None and any(
                    old.contact_id == contact_id
                    and old.recipient_alias == item.get("recipient_alias")
                    for old in existing.items
                )
                if not historical:
                    raise GosariError("RESOURCE_NOT_FOUND", {"fields": ["contact_id"]})
            elif not (
                existing is not None
                and any(
                    old.contact_id == contact_id
                    and old.recipient_alias == item.get("recipient_alias")
                    for old in existing.items
                )
            ):
                item["recipient_alias"] = contact.name
        items.append(item)
    items = _validate_items(items)
    try:
        share_items = [ShareItem.model_validate(item) for item in items]
    except ValidationError:
        raise GosariError("INVALID_INPUT", {"fields": ["items"]}) from None
    for item in share_items:
        if not item.amount_value.is_finite() or item.amount_value <= 0:
            raise GosariError("INVALID_INPUT", {"fields": ["amount_value"]})
        if item.status == "delivered" and item.occurred_on is None:
            raise GosariError("INVALID_INPUT", {"fields": ["occurred_on"]})
    message_enabled = bool(payload.get("message_enabled", False))
    message = payload.get("editable_message") or (
        build_message(share_items) if message_enabled else None
    )
    unit_totals = summarize_totals(share_items)
    canonical = {
        "items": [i.model_dump(mode="json") for i in share_items],
        "unit_totals": unit_totals,
        "message_enabled": message_enabled,
        "editable_message": message,
        "source_record_ids": _reference_ids(
            payload.get("source_record_ids", []), "source_record_ids"
        ),
        "public_evidence_ids": _reference_ids(
            payload.get("public_evidence_ids", []), "public_evidence_ids"
        ),
    }
    for record_id in canonical["source_record_ids"]:
        entry = session.notebook.get(record_id)
        if entry:
            canonical["public_evidence_ids"] = list(
                dict.fromkeys(
                    [
                        *canonical["public_evidence_ids"],
                        *entry.public_evidence_ids,
                    ]
                )
            )
    previous_sources = set(existing.source_record_ids) if existing else set()
    if any(
        record_id not in session.notebook and record_id not in previous_sources
        for record_id in canonical["source_record_ids"]
    ):
        raise GosariError("RESOURCE_NOT_FOUND", {"fields": ["source_record_ids"]})
    preview = create_preview(
        session,
        f"share.{action}",
        existing.share_draft_id if existing else None,
        existing.revision if existing else 0,
        SCHEMA_VERSION,
        canonical,
    )
    display = {
        **canonical,
        "prepared_at": utcnow().isoformat(),
        "note": "미리보기입니다. 확정 전에는 저장되지 않으며 실제 전송은 없습니다.",
    }
    return preview, display


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    if preview.action not in {"share.save", "share.update", "share.delete"}:
        raise GosariError("ACTION_NOT_ALLOWED")
    existing = None
    if preview.action != "share.save":
        existing = session.share_drafts.get(preview.target_id)
        if existing is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        if existing.revision != preview.expected_revision:
            raise GosariError("REVISION_CONFLICT")
        if preview.action == "share.delete":
            del session.share_drafts[existing.share_draft_id]
            return existing.share_draft_id, existing.revision
    payload = preview.canonical_payload
    draft = ShareDraft(
        share_draft_id=preview.target_id,
        revision=existing.revision + 1 if existing else 1,
        items=[ShareItem(**i) for i in payload["items"]],
        message_enabled=payload["message_enabled"],
        editable_message=payload.get("editable_message"),
        source_record_ids=list(payload.get("source_record_ids", [])),
        public_evidence_ids=list(payload.get("public_evidence_ids", [])),
        prepared_at=existing.prepared_at if existing else utcnow(),
    )
    session.share_drafts[draft.share_draft_id] = draft
    return draft.share_draft_id, draft.revision
