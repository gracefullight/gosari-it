"""SRS §9.4~9.6 개인 엔터티. 세션 메모리 전용 — 공개 DB/로그 이동 금지."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class NotebookEntry(BaseModel):
    record_id: str
    revision: int = 1
    experience_date: date
    companion_aliases: list[str] = Field(default_factory=list)
    activity_text: str
    amount_value: Decimal | None = None
    amount_unit: str | None = None
    location_address: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    private_region_id: str | None = None
    public_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PrivateRegion(BaseModel):
    region_id: str
    revision: int = 1
    kind: Literal["existing", "interest"]
    visited_on: date | None = None
    public_area_code: str | None = None
    coarse_grid: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    local_alias: str
    selected_station_mapping_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PersonalContact(BaseModel):
    contact_id: str
    revision: int = 1
    name: str
    relationship: str
    notes: str = ""
    created_at: datetime
    updated_at: datetime


class ShareItem(BaseModel):
    contact_id: str | None = None
    recipient_alias: str
    amount_value: Decimal
    amount_unit: str
    planned_delivery: str | None = None
    optional_role_note: str | None = None
    occurred_on: date | None = None
    status: Literal["planned", "delivered"] = "planned"


class ShareDraft(BaseModel):
    share_draft_id: str
    revision: int = 1
    items: list[ShareItem]
    message_enabled: bool = False
    editable_message: str | None = None
    source_record_ids: list[str] = Field(default_factory=list)
    public_evidence_ids: list[str] = Field(default_factory=list)
    prepared_at: datetime


class Preview(BaseModel):
    preview_id: str
    action: str
    target_id: str
    expected_revision: int
    schema_version: str
    canonical_payload: dict[str, Any]
    display_payload: dict[str, Any]
    preview_hash: str
    created_at: datetime
    expires_at: datetime
    state: Literal["preview", "confirmed", "committed", "cancelled", "failed"] = "preview"


class Consent(BaseModel):
    consent_id: str
    preview_id: str
    action: str
    target_id: str
    target_revision: int
    preview_hash: str
    issued_at: datetime
    expires_at: datetime
    decision: Literal["confirm"] = "confirm"
    used: bool = False


class ActionResult(BaseModel):
    action_id: str
    consent_id: str
    canonical_command_hash: str
    state: Literal["committed", "failed"]
    result_id: str | None = None
    resulting_revision: int | None = None
    safe_error: str | None = None
    committed_at: datetime | None = None
