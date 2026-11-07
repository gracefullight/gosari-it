"""Exact public coordinate → containing cadastral parcel → public ownership class."""

import math
import re
from collections.abc import Callable
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gosari.config import Settings
from gosari.domain import DataStatus
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest, json_hash, now_utc
from gosari.sources.live import TransmissionGate
from gosari.sources.locations import resolve_public_place

PARCEL_URL = "https://api.vworld.kr/req/data"
OWNERSHIP_URL = "https://api.vworld.kr/ned/data/getPossessionAttr"
DOC_URL = "https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do?apiNum=47"


class OwnershipFields(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pnu: str = Field(pattern=r"^\d{19}$")
    posesnSeCode: str = Field(pattern=r"^\d{1,2}$")
    posesnSeCodeNm: str = Field(min_length=1, max_length=50)
    stdrYm: str = Field(pattern=r"^\d{4}-?\d{2}$")
    lastUpdtDt: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


def classify_ownership(name: str) -> tuple[str, bool | None]:
    normalized = re.sub(r"[\s,·ㆍ./]", "", name)
    if normalized in {"개인", "개인소유", "사유", "사유지"}:
        return "private", True
    if normalized in {
        "국유",
        "국유지",
        "공유",
        "공유지",
        "국공유",
        "국공유지",
        "시유",
        "시유지",
        "도유",
        "도유지",
        "군유",
        "군유지",
        "구유",
        "구유지",
        "시도유",
        "시도유지",
        "시군구유",
        "시군구유지",
    }:
        return "public", False
    return "unknown", None


def _ring_contains(x: float, y: float, ring: list[Any]) -> bool:
    inside = False
    if len(ring) < 4:
        raise GosariError("UPSTREAM_SCHEMA_CHANGED")
    for index, vertex in enumerate(ring):
        previous = ring[index - 1]
        if len(vertex) < 2 or len(previous) < 2:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        ax, ay, bx, by = map(float, (*previous[:2], *vertex[:2]))
        if not all(math.isfinite(value) for value in (ax, ay, bx, by)):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        if not (-180 <= ax <= 180 and -180 <= bx <= 180 and -90 <= ay <= 90 and -90 <= by <= 90):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if (
            abs(cross) < 1e-12
            and min(ax, bx) <= x <= max(ax, bx)
            and min(ay, by) <= y <= max(ay, by)
        ):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def contains_point(geometry: dict[str, Any], longitude: float, latitude: float) -> bool:
    polygons = geometry.get("coordinates")
    if geometry.get("type") == "Polygon":
        polygons = [polygons]
    elif geometry.get("type") != "MultiPolygon":
        raise GosariError("UPSTREAM_SCHEMA_CHANGED")
    if not isinstance(polygons, list):
        raise GosariError("UPSTREAM_SCHEMA_CHANGED")
    return any(
        isinstance(rings, list)
        and bool(rings)
        and _ring_contains(longitude, latitude, rings[0])
        and not any(_ring_contains(longitude, latitude, hole) for hole in rings[1:])
        for rings in polygons
    )


def _response_error(payload: dict[str, Any]) -> None:
    response = payload.get("response", payload)
    if isinstance(response, dict) and (
        response.get("status") in ("ERROR", "FAIL") or response.get("error")
    ):
        error = response.get("error", {})
        code = str(error.get("code", "")) if isinstance(error, dict) else ""
        auth = code in {"INVALID_KEY", "INCORRECT_KEY", "UNREGISTERED_KEY", "INVALID_DOMAIN"}
        raise GosariError(
            "CAPABILITY_DISABLED" if auth else "UPSTREAM_FAILED",
            {
                "reason": "VWORLD_AUTH_REJECTED" if auth else "VWORLD_SERVICE_ERROR",
            },
        )


def query_land_ownership(
    spec: dict[str, Any],
    request_id: str,
    settings: Settings,
    checkpoint: Callable[[], None] | None = None,
) -> ResultEnvelope:
    check = checkpoint or (lambda: None)
    place = resolve_public_place(str(spec.get("location_id") or ""))
    public: dict[str, Any] = {
        "location_id": place[0],
        "location_name": place[1],
        "latitude": place[2],
        "longitude": place[3],
        "pnu": None,
        "ownership_class": "unknown",
        "is_private": None,
        "owner_type_code": None,
        "owner_type_name": None,
        "reference_month": None,
        "last_updated": None,
        "source_name": "브이월드",
        "source_url": DOC_URL,
    }
    manifests: list[SourceManifest] = []

    def finish(
        status: str, reason: str | None = None, error: GosariError | None = None
    ) -> ResultEnvelope:
        from gosari.agent.analysis import get_evidence_store

        evidence = {
            "public_query_spec": spec,
            "source_manifests": [m.to_dict() for m in manifests],
            "result_values": {"land_ownership": public, "reason": reason},
            "created_at": now_utc().isoformat(),
        }
        return ResultEnvelope(
            request_id=request_id,
            data_status=DataStatus(status),
            source_mode="fetched" if manifests else None,
            fetched_at=now_utc(),
            requested_scope=spec,
            effective_scope={"location_id": place[0], "pnu": public["pnu"]},
            result={"land_ownership": public, "reason": reason},
            observed_period={
                "reference_month": public["reference_month"],
                "updated_on": public["last_updated"],
            },
            errors=[{"code": error.code, "message": error.safe_message}] if error else [],
            evidence_ids=[get_evidence_store().put(evidence)],
        )

    key = settings.resolved_vworld_api_key
    if not key:
        return finish("unavailable", "VWORLD_KEY_MISSING", GosariError("CAPABILITY_DISABLED"))
    gate = TransmissionGate(settings.model_copy(update={"max_retries": 0}), checkpoint=check)
    auth = {"key": key, **({"domain": settings.vworld_domain} if settings.vworld_domain else {})}
    try:
        check()
        parcel_params = {
            "service": "data",
            "request": "GetFeature",
            "version": "2.0",
            "data": "LP_PA_CBND_BUBUN",
            "geomFilter": f"POINT({place[3]} {place[2]})",
            "crs": "EPSG:4326",
            "format": "json",
            "geometry": "true",
            "attribute": "true",
            "columns": "pnu",
            "size": 100,
            "page": 1,
        }
        response, _ = gate.get_json(PARCEL_URL, {**parcel_params, **auth}, timeout=12)
        _response_error(response)
        result = response.get("response", {})
        if result.get("status") == "NOT_FOUND":
            return finish("no_data", "PARCEL_NOT_FOUND")
        features = result.get("result", {}).get("featureCollection", {}).get("features")
        if not isinstance(features, list):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        record_count = result.get("record", {}).get("total", len(features))
        if int(record_count) > len(features):
            return finish("partial", "PARCEL_PAGES_INCOMPLETE")
        parcels = sorted(
            {
                str(feature.get("properties", {}).get("pnu") or "")
                for feature in features
                if contains_point(feature.get("geometry", {}), place[3], place[2])
            }
        )
        if any(not re.fullmatch(r"\d{19}", pnu) for pnu in parcels):
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        manifests.append(
            SourceManifest(
                source_id="vworld_cadastral",
                dataset_id="LP_PA_CBND_BUBUN",
                operation="point_parcel",
                sanitized_parameters=parcel_params,
                fetched_at=now_utc(),
                returned_count=len(parcels),
                content_hash=json_hash({"pnus": parcels, "point": [place[3], place[2]]}),
            )
        )
        if not parcels:
            return finish("no_data", "PARCEL_NOT_FOUND")
        if len(parcels) != 1:
            return finish("conflict", "AMBIGUOUS_PARCEL")
        public["pnu"] = parcels[0]
        rows: list[OwnershipFields] = []
        for page in (1, 2):
            check()
            params = {"pnu": parcels[0], "format": "json", "numOfRows": 1000, "pageNo": page}
            payload, _ = gate.get_json(OWNERSHIP_URL, {**params, **auth}, timeout=12)
            _response_error(payload)
            container = payload.get("possessions", payload.get("possessionAttrs"))
            if not isinstance(container, dict):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            fields = container.get("field", [])
            if isinstance(fields, dict):
                fields = [fields]
            if not isinstance(fields, list):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            clean = [OwnershipFields.model_validate(row) for row in fields]
            if any(row.pnu != parcels[0] for row in clean):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            for row in clean:
                date.fromisoformat(row.lastUpdtDt)
                month = row.stdrYm.replace("-", "")
                date.fromisoformat(f"{month[:4]}-{month[4:]}-01")
                if not re.fullmatch(r"[가-힣 ,·ㆍ./()]+", row.posesnSeCodeNm):
                    raise GosariError("UPSTREAM_SCHEMA_CHANGED")
            rows.extend(clean)
            total = int(container.get("totalCount", len(rows)))
            manifests.append(
                SourceManifest(
                    source_id="vworld_ownership",
                    dataset_id="possession",
                    operation="ownership_class",
                    sanitized_parameters=params,
                    fetched_at=now_utc(),
                    returned_count=len(clean),
                    total_count=total,
                    page_number=page,
                    page_size=1000,
                    has_more=len(rows) < total,
                    content_hash=json_hash([row.model_dump() for row in clean]),
                )
            )
            if len(rows) >= total:
                break
        if manifests[-1].has_more:
            return finish("partial", "OWNERSHIP_PAGES_INCOMPLETE")
        if not rows:
            return finish("no_data", "OWNERSHIP_NOT_FOUND")
        latest = max(row.stdrYm.replace("-", "") for row in rows)
        current = [row for row in rows if row.stdrYm.replace("-", "") == latest]
        types = {(row.posesnSeCode, row.posesnSeCodeNm) for row in current}
        if len(types) != 1:
            return finish("conflict", "OWNERSHIP_CLASS_CONFLICT")
        code, name = next(iter(types))
        classification, private = classify_ownership(name)
        public.update(
            owner_type_code=code,
            owner_type_name=name,
            ownership_class=classification,
            is_private=private,
            reference_month=f"{latest[:4]}-{latest[4:]}",
            last_updated=max(row.lastUpdtDt for row in current),
        )
        return finish("complete")
    except GosariError as error:
        if error.code in {"ACTION_NOT_ALLOWED", "JOB_DEADLINE_EXCEEDED"}:
            raise
        return finish("unavailable", str(error.extra.get("reason") or error.code), error)
    except ValueError, TypeError, KeyError, AttributeError, IndexError:
        return finish(
            "unavailable", "UPSTREAM_SCHEMA_CHANGED", GosariError("UPSTREAM_SCHEMA_CHANGED")
        )
