"""가족·지인 나눔 — 대상·분량·시점 정리와 로컬 문구 (SRS §5.6). 실제 전송 도구 없음."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import PersonalContact, Preview, ShareDraft, ShareItem
from gosari.personal.approval import create_preview
from gosari.sessions import Session, new_id, utcnow

SCHEMA_VERSION = "share-v1"
FILE_SCHEMA_VERSION = "share-file-v1"
FILE_NOTE = (
    "고사리잇에서 사용자가 확정한 나눔 기록을 담은 로컬 파일입니다. 실제 발송 기능은 없습니다."
)


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


def _format_amount(value: Decimal) -> str:
    return f"{value.normalize():f}" if value == value.to_integral_value() else str(value)


def _file_items(
    drafts: list[ShareDraft], contact: PersonalContact | None
) -> list[tuple[ShareDraft, ShareItem]]:
    pairs = [
        (draft, item)
        for draft in drafts
        for item in draft.items
        if contact is None
        or item.contact_id == contact.contact_id
        or (item.contact_id is None and item.recipient_alias == contact.name)
    ]
    return sorted(
        pairs,
        key=lambda pair: (
            pair[1].occurred_on.isoformat()
            if pair[1].occurred_on
            else pair[0].prepared_at.date().isoformat()
        ),
    )


def build_share_file(
    drafts: list[ShareDraft], contact: PersonalContact | None, prepared_on: date
) -> tuple[str, str, list[dict[str, Any]]]:
    """FR-SHARE-005: 미리 본 내용만 담는 텍스트 파일 본문. 서버에는 파일을 남기지 않는다."""
    pairs = _file_items(drafts, contact)
    if not pairs:
        raise GosariError("INVALID_INPUT", {"fields": ["items"]})
    title = contact.name if contact else "전체"
    lines = [f"고사리 나눔 기록 · {title}", f"작성일 {prepared_on.isoformat()}", ""]
    for _draft, item in pairs:
        when = (
            item.occurred_on.isoformat()
            if item.occurred_on
            else (item.planned_delivery or "날짜 미정")
        )
        status = "전달 완료" if item.status == "delivered" else "전달 예정"
        lines.append(
            f"- {when} · {item.recipient_alias} · "
            f"{_format_amount(item.amount_value)}{item.amount_unit} · {status}"
        )
    totals = summarize_totals([item for _, item in pairs if item.status == "delivered"])
    lines.append("")
    lines.append(
        "전달 완료 합계: "
        + (", ".join(f"{total}{unit}" for unit, total in totals.items()) or "없음")
    )
    lines.extend(["", FILE_NOTE])
    safe_title = "".join(ch for ch in title if ch.isalnum()) or "전체"
    filename = f"나눔기록_{safe_title}_{prepared_on.strftime('%Y%m%d')}.txt"
    return filename, "\n".join(lines) + "\n", [item.model_dump(mode="json") for _, item in pairs]


def prepare_file(
    session: Session, payload: dict[str, Any], settings: Settings
) -> tuple[Preview, dict[str, Any]]:
    """공유 파일 미리보기. 허용 프로파일에서만 준비하고 승인 전에는 아무것도 만들지 않는다."""
    if not settings.allow_share_file:
        raise GosariError("CAPABILITY_DISABLED", {"reason": "SHARE_FILE_POLICY_UNCONFIRMED"})
    if not isinstance(payload, dict):
        raise GosariError("INVALID_INPUT", {"fields": ["payload"]})
    draft_ids = _reference_ids(payload.get("share_draft_ids", []), "share_draft_ids")
    if not draft_ids:
        raise GosariError("INVALID_INPUT", {"fields": ["share_draft_ids"]})
    drafts = []
    for draft_id in draft_ids:
        draft = session.share_drafts.get(draft_id)
        if draft is None:
            raise GosariError("RESOURCE_NOT_FOUND", {"fields": ["share_draft_ids"]})
        drafts.append(draft)
    contact_id = payload.get("contact_id")
    contact = None
    if contact_id is not None:
        if not isinstance(contact_id, str) or not contact_id.strip():
            raise GosariError("INVALID_INPUT", {"fields": ["contact_id"]})
        contact = session.contacts.get(contact_id)
        if contact is None:
            raise GosariError("RESOURCE_NOT_FOUND", {"fields": ["contact_id"]})
    prepared_at = utcnow()
    filename, content, items = build_share_file(drafts, contact, prepared_at.date())
    canonical = {
        "share_draft_ids": draft_ids,
        "draft_revisions": {draft.share_draft_id: draft.revision for draft in drafts},
        "contact_id": contact_id,
        "filename": filename,
        "content": content,
    }
    display = {
        "filename": filename,
        "content": content,
        "items": items,
        "unit_totals": summarize_totals(
            [ShareItem.model_validate(item) for item in items if item["status"] == "delivered"]
        ),
    }
    preview = create_preview(
        session,
        "share.file",
        new_id("file"),
        0,
        FILE_SCHEMA_VERSION,
        canonical,
        display_payload=display,
    )
    return preview, {
        **display,
        "prepared_at": prepared_at.isoformat(),
        "note": (
            "미리보기입니다. 확정하면 이 내용 그대로 파일 1개를 내려받습니다. "
            "서버에는 파일이 남지 않습니다."
        ),
    }


def execute_file(session: Session, preview: Preview) -> tuple[str, int]:
    """승인된 미리보기의 내용만 파일로 내려준다. 기록은 바꾸지 않는다."""
    if preview.action != "share.file":
        raise GosariError("ACTION_NOT_ALLOWED")
    revisions = preview.canonical_payload.get("draft_revisions", {})
    for draft_id, revision in revisions.items():
        draft = session.share_drafts.get(draft_id)
        if draft is None:
            raise GosariError("RESOURCE_NOT_FOUND", {"fields": ["share_draft_ids"]})
        if draft.revision != revision:
            raise GosariError("REVISION_CONFLICT")
    return preview.target_id, 0
