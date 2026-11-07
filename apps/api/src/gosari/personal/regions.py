"""사용자가 선택한 관심 지역과 지도 핀을 보관한다."""

import math
from datetime import date
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
    visited_on = payload.get("visited_on")
    if visited_on is not None:
        try:
            if (
                not isinstance(visited_on, str)
                or date.fromisoformat(visited_on).isoformat() != visited_on
            ):
                raise ValueError
        except ValueError:
            raise GosariError("INVALID_INPUT", {"fields": ["visited_on"]}) from None
    latitude, longitude = payload.get("latitude"), payload.get("longitude")
    if (latitude is None) != (longitude is None):
        raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]})
    if latitude is not None and longitude is not None:
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]})
        try:
            latitude, longitude = float(latitude), float(longitude)
        except ValueError, TypeError, OverflowError:
            raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]}) from None
        if (
            not math.isfinite(latitude)
            or not math.isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            raise GosariError("INVALID_INPUT", {"fields": ["latitude", "longitude"]})
        payload = {**payload, "latitude": latitude, "longitude": longitude}
    if not payload.get("public_area_code") and not payload.get("coarse_grid") and latitude is None:
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
            display_payload={
                "kind": region.kind,
                "local_alias": region.local_alias,
                "visited_on": region.visited_on.isoformat() if region.visited_on else None,
                "public_area_code": region.public_area_code,
                "latitude": region.latitude,
                "longitude": region.longitude,
            },
        )


def execute(session: Session, preview: Preview) -> tuple[str, int]:
    payload = preview.canonical_payload
    now = utcnow()
    if preview.action == "region.create":
        region = PrivateRegion(
            region_id=preview.target_id,
            revision=1,
            kind=payload["kind"],
            visited_on=date.fromisoformat(payload["visited_on"])
            if payload.get("visited_on")
            else None,
            public_area_code=payload.get("public_area_code"),
            coarse_grid=payload.get("coarse_grid"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
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
            "visited_on": date.fromisoformat(payload["visited_on"])
            if payload.get("visited_on")
            else None,
            "public_area_code": payload.get("public_area_code"),
            "coarse_grid": payload.get("coarse_grid"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "local_alias": payload["local_alias"],
            "selected_station_mapping_ids": list(payload.get("selected_station_mapping_ids", [])),
            "revision": region.revision + 1,
            "updated_at": now,
        }
    )
    session.regions[updated.region_id] = updated
    return updated.region_id, updated.revision
