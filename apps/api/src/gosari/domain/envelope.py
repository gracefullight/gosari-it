"""SRS §8.5 공통 결과 Envelope (result-v1)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    event_type: str = "stage"
    payload: dict[str, Any] = Field(default_factory=dict)


class UiElement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "ResultLayout",
        "PriceResults",
        "WeatherMap",
        "WeatherComparison",
        "OutingResults",
        "StationResults",
        "FollowupActions",
    ]
    props: dict[str, Any] = Field(default_factory=dict)
    children: list[str] = Field(default_factory=list)


class UiSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str
    elements: dict[str, UiElement]


class PersonalSearchSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    kind: Literal["notebook", "region", "contact", "share", "all"]
    count: int


class JobResponse(BaseModel):
    """SRS §8.2 작업 상태 응답 — Job의 공개 직렬화 형태."""

    job_id: str
    request_id: str
    stage: str
    created_at: datetime
    result: ResultEnvelope | None = None
    error: str | None = None
    events: list[ProgressEvent] = Field(default_factory=list)
    model_usage: dict[str, Any] = Field(default_factory=dict)
    assistant_text: str = ""
    ui_spec: UiSpec | None = None
    ui_results: dict[str, ResultEnvelope] = Field(default_factory=dict)
    personal_search: PersonalSearchSelection | None = None
    personal_form: Literal["notebook", "region_compare", "share"] | None = None


class ChatJobResponse(JobResponse):
    kind: Literal["job"] = "job"


class PrepareResponse(BaseModel):
    """SRS §4.1 요청 분류·조건 확인 응답. 원천 호출·개인 변경 전 단계."""

    classification: Literal["public", "personal"]
    feature: str | None = None
    needs_confirmation: bool
    spec: dict[str, Any] | None = None
    form: dict[str, Any] | None = None


class ChatConfirmationResponse(BaseModel):
    kind: Literal["confirmation"] = "confirmation"
    preparation: PrepareResponse


class SessionCreated(BaseModel):
    """세션 생성 응답. 개인 데이터는 세션 메모리 한정."""

    session_id: str
    created_at: datetime
    expires_at: datetime
    idle_ttl_seconds: int
    notice: str


class SessionClosed(BaseModel):
    """세션 종료 응답."""

    status: str
    notice: str
