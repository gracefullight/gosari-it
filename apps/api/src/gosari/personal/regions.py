"""지역 등록 — 대략 지역·별칭만. 정확 채취 좌표·지오로케이션 이력은 필드로 만들지 않는다."""

from typing import Any

from gosari.domain.errors import GosariError
from gosari.personal import Preview, PrivateRegion
from gosari.personal.approval import create_preview
from gosari.sessions import Session, utcnow

SCHEMA_VERSION = "region-v1"


def _validate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("kind") not in ("existing", "interest"):
        raise GosariError("INVALID_INPUT", {"fields": ["kind"]})
    if not payload.get("local_alias"):
        raise GosariError("INVALID_INPUT", {"fields": ["local_alias"]})
    if not payload.get("public_area_code") and not payload.get("coarse_grid"):
        raise GosariError("INVALID_INPUT", {"fields": ["public_area_code|coarse_grid"]})
    return payload


def prepare_create(session: Session, payload: dict[str, Any]) -> Preview:
    payload = _validate(payload)
    return create_preview(session, "region.create", None, 0, SCHEMA_VERSION, payload)


def prepare_update(session: Session, region_id: str, payload: dict[str, Any]) -> Preview:
    with session.lock:
        region = session.regions.get(region_id)
        if region is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        merged = _validate({**region.model_dump(mode="json"), **payload})
        return create_preview(
            session, "region.update", region_id, region.revision, SCHEMA_VERSION, merged
        )


def prepare_delete(session: Session, region_id: str) -> Preview:
    with session.lock:
        region = session.regions.get(region_id)
        if region is None:
            raise GosariError("RESOURCE_NOT_FOUND")
        return create_preview(
            session,
            "region.delete",
            region_id,
            region.revision,
            SCHEMA_VERSION,
            {"region_id": region_id},
        )


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    payload = preview.canonical_payload
    now = utcnow()
    if preview.action == "region.create":
        region = PrivateRegion(
            region_id=preview.target_id,
            revision=1,
            kind=payload["kind"],
            public_area_code=payload.get("public_area_code"),
            coarse_grid=payload.get("coarse_grid"),
            local_alias=payload["local_alias"],
            selected_station_mapping_ids=list(payload.get("selected_station_mapping_ids", [])),
            created_at=now,
            updated_at=now,
        )
        session.regions[region.region_id] = region
        return region.region_id, region.revision
    region = session.regions.get(preview.target_id)
    if region is None:
        raise GosariError("RESOURCE_NOT_FOUND")
    if region.revision != preview.expected_revision:
        raise GosariError("REVISION_CONFLICT")
    if preview.action == "region.delete":
        del session.regions[region.region_id]
        return region.region_id, region.revision
    updated = region.model_copy(
        update={
            "kind": payload["kind"],
            "public_area_code": payload.get("public_area_code"),
            "coarse_grid": payload.get("coarse_grid"),
            "local_alias": payload["local_alias"],
            "selected_station_mapping_ids": list(payload.get("selected_station_mapping_ids", [])),
            "revision": region.revision + 1,
            "updated_at": now,
        }
    )
    session.regions[updated.region_id] = updated
    return updated.region_id, updated.revision
