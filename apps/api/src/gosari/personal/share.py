"""가족·지인 나눔 — 대상·분량·시점 정리와 로컬 문구 (SRS §5.6). 실제 전송 도구 없음."""

from decimal import Decimal, InvalidOperation
from typing import Any

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


def prepare(session: Session, payload: dict[str, Any]) -> tuple[Preview, dict[str, Any]]:
    items = _validate_items(payload.get("items", []))
    share_items = [
        ShareItem(
            recipient_alias=i["recipient_alias"],
            amount_value=Decimal(str(i["amount_value"])),
            amount_unit=i["amount_unit"],
            planned_delivery=i.get("planned_delivery"),
            optional_role_note=i.get("optional_role_note"),
        )
        for i in items
    ]
    message_enabled = bool(payload.get("message_enabled", False))
    message = payload.get("editable_message") or (
        build_message(share_items) if message_enabled else None
    )
    canonical = {
        "items": [i.model_dump(mode="json") for i in share_items],
        "message_enabled": message_enabled,
        "editable_message": message,
        "source_record_ids": list(payload.get("source_record_ids", [])),
        "public_evidence_ids": list(payload.get("public_evidence_ids", [])),
    }
    preview = create_preview(session, "share.save", None, 0, SCHEMA_VERSION, canonical)
    display = {
        **canonical,
        "prepared_at": utcnow().isoformat(),
        "note": "미리보기입니다. 확정 전에는 저장되지 않으며 실제 전송은 없습니다.",
    }
    return preview, display


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    payload = preview.canonical_payload
    draft = ShareDraft(
        share_draft_id=preview.target_id,
        revision=1,
        items=[ShareItem(**i) for i in payload["items"]],
        message_enabled=payload["message_enabled"],
        editable_message=payload.get("editable_message"),
        source_record_ids=list(payload.get("source_record_ids", [])),
        public_evidence_ids=list(payload.get("public_evidence_ids", [])),
        prepared_at=utcnow(),
    )
    session.share_drafts[draft.share_draft_id] = draft
    return draft.share_draft_id, draft.revision
