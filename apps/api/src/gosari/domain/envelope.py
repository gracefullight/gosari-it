"""SRS §8.5 공통 결과 Envelope (result-v1)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from gosari.domain import CacheResolution, DataStatus, LinkStatus, SourceMode


class ResultEnvelope(BaseModel):
    schema_version: str = "result-v1"
    request_id: str
    data_status: DataStatus | None = None
    source_mode: SourceMode | None = None
    action_status: str | None = None
    link_status: LinkStatus = LinkStatus.NOT_REQUESTED
    cache_resolution: CacheResolution = CacheResolution.BYPASS
    requested_scope: dict[str, Any] = Field(default_factory=dict)
    effective_scope: dict[str, Any] = Field(default_factory=dict)
    observed_period: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime | None = None
    verified_on: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class ProgressEvent(BaseModel):
    """SRS §8.6 진행 이벤트. 개인 원문·프롬프트·키·정확 좌표 금지."""

    event_id: str
    job_id: str
    stage: str
    timestamp: datetime
    completed_units: int | None = None
    total_units: int | None = None
    unit_kind: str | None = None
    safe_message: str = ""
