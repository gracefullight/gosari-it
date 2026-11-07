"""내 수첩 — 로컬 입력·미리보기·승인된 변경·회고 (SRS §5.5, §9.4). 외부 LLM 사용 안 함."""

import math
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from gosari.domain.errors import GosariError
from gosari.personal import NotebookEntry, Preview
from gosari.personal.approval import create_preview
from gosari.sessions import Session, utcnow

SCHEMA_VERSION = "notebook-v1"


def _validate_payload(payload: dict[str, Any], settings_max: int) -> dict[str, Any]:
    experience_date = payload.get("experience_date")
    activity_text = payload.get("activity_text")
    if not experience_date or not activity_text:
        raise GosariError("INVALID_INPUT", {"fields": ["experience_date", "activity_text"]})
    try:
        date.fromisoformat(str(experience_date))
    except ValueError:
        raise GosariError("INVALID_INPUT", {"fields": ["experience_date"]}) from None
    if len(str(activity_text)) > settings_max:
        raise GosariError("INPUT_TOO_LARGE")
    amount_value = payload.get("amount_value")
    amount_unit = payload.get("amount_unit")
    if (amount_value is None) != (amount_unit is None):
        raise GosariError("UNIT_UNRESOLVED")
    if amount_value is not None:
        try:
            Decimal(str(amount_value))
        except InvalidOperation:
            raise GosariError("INVALID_INPUT", {"fields": ["amount_value"]}) from None
    latitude, longitude = payload.get("latitude"), payload.get("longitude")
    if (latitude is None) != (longitude is None):
        raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]})
    if latitude is not None and longitude is not None:
        try:
            latitude, longitude = float(latitude), float(longitude)
        except ValueError, TypeError:
            raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]}) from None
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]})
        payload = {**payload, "latitude": latitude, "longitude": longitude}
    address = payload.get("location_address")
    if address is not None and (not isinstance(address, str) or len(address) > 500):
        raise GosariError("INVALID_INPUT", {"fields": ["location_address"]})
    references = payload.get("public_evidence_ids", [])
    if not isinstance(references, list) or any(
        not isinstance(item, str) or not item.strip() for item in references
    ):
        raise GosariError("INVALID_INPUT", {"fields": ["public_evidence_ids"]})
    region_id = payload.get("private_region_id")
    if region_id is not None and (not isinstance(region_id, str) or not region_id.strip()):
        raise GosariError("INVALID_INPUT", {"fields": ["private_region_id"]})
    return {**payload, "public_evidence_ids": list(dict.fromkeys(references))}


def prepare_create(session: Session, payload: dict[str, Any], max_text: int) -> Preview:
    payload = _validate_payload(payload, max_text)
    return create_preview(
        session,
        "notebook.create",
        None,
        0,
        SCHEMA_VERSION,
        payload,
        display_payload=payload,
    )


def prepare_update(
    session: Session, record_id: str, payload: dict[str, Any], max_text: int
) -> Preview:
    with session.lock:
        entry = session.notebook.get(record_id)
        if entry is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        merged = {**entry.model_dump(mode="json"), **payload}
        merged = _validate_payload(merged, max_text)
        return create_preview(
            session,
            "notebook.update",
            record_id,
            entry.revision,
            SCHEMA_VERSION,
            merged,
        )


def prepare_delete(session: Session, record_id: str) -> Preview:
    with session.lock:
        entry = session.notebook.get(record_id)
        if entry is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return create_preview(
            session,
            "notebook.delete",
            record_id,
            entry.revision,
            SCHEMA_VERSION,
            {"record_id": record_id},
            display_payload={
                "location_address": entry.location_address,
                "experience_date": entry.experience_date.isoformat(),
                "activity_text": entry.activity_text,
                "companion_aliases": entry.companion_aliases,
                "amount_value": entry.amount_value,
                "amount_unit": entry.amount_unit,
            },
        )


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    payload = preview.canonical_payload
    now = utcnow()
    if preview.action == "notebook.create":
        entry = NotebookEntry(
            record_id=preview.target_id,
            revision=1,
            experience_date=date.fromisoformat(payload["experience_date"]),
            companion_aliases=list(payload.get("companion_aliases", [])),
            activity_text=payload["activity_text"],
            amount_value=Decimal(str(payload["amount_value"]))
            if payload.get("amount_value") is not None
            else None,
            amount_unit=payload.get("amount_unit"),
            location_address=payload.get("location_address"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            private_region_id=payload.get("private_region_id"),
            public_evidence_ids=list(payload.get("public_evidence_ids", [])),
            created_at=now,
            updated_at=now,
        )
        session.notebook[entry.record_id] = entry
        return entry.record_id, entry.revision
    entry = session.notebook.get(preview.target_id)
    if entry is None:
        raise GosariError("RESOURCE_NOT_FOUND")
    if entry.revision != preview.expected_revision:
        raise GosariError("REVISION_CONFLICT")
    if preview.action == "notebook.delete":
        del session.notebook[entry.record_id]
        return entry.record_id, entry.revision
    updated = entry.model_copy(
        update={
            "experience_date": date.fromisoformat(payload["experience_date"]),
            "companion_aliases": list(payload.get("companion_aliases", [])),
            "activity_text": payload["activity_text"],
            "amount_value": Decimal(str(payload["amount_value"]))
            if payload.get("amount_value") is not None
            else None,
            "amount_unit": payload.get("amount_unit"),
            "location_address": payload.get("location_address"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "private_region_id": payload.get("private_region_id"),
            "public_evidence_ids": list(payload.get("public_evidence_ids", [])),
            "revision": entry.revision + 1,
            "updated_at": now,
        }
    )
    session.notebook[updated.record_id] = updated
    return updated.record_id, updated.revision


def search(
    session: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    alias: str | None = None,
) -> list[NotebookEntry]:
    results = []
    for entry in session.notebook.values():
        if start and entry.experience_date < start:
            continue
        if end and entry.experience_date > end:
            continue
        if alias and alias not in entry.companion_aliases:
            continue
        results.append(entry)
    return sorted(results, key=lambda e: e.experience_date, reverse=True)
