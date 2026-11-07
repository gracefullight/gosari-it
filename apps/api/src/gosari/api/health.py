"""건강·준비·기능 가용성. 외부 유료 호출을 하지 않는다."""

from typing import Literal

from litestar import Controller, get
from pydantic import BaseModel

from gosari.config import get_settings
from gosari.db import db_available, get_pool


class LiveStatus(BaseModel):
    """생존 확인 응답."""

    status: str


class ReadinessResponse(BaseModel):
    """준비 상태 응답 — DB·프로필·외부 요청·LLM 구성 여부."""

    status: str
    database: str
    profile: str
    external_requests: bool
    llm: str


class MapCapabilities(BaseModel):
    tiles: bool
    osm_attribution_required: bool


class LlmCapabilities(BaseModel):
    available: bool
    model: str


class CacheCapabilities(BaseModel):
    response_cache: bool
    semantic: bool


class CapabilitiesResponse(BaseModel):
    """기능 가용성 응답 — 클라이언트가 모드별 UI를 분기하는 근거."""

    profile: str
    runtime_mode: Literal["live", "replay", "limited"]
    map: MapCapabilities
    llm: LlmCapabilities
    sources: dict[str, bool]
    files: dict[str, bool]
    cache: CacheCapabilities


class HealthController(Controller):
    path = "/health"

    @get("/live", sync_to_thread=True)
    def live(self) -> LiveStatus:
        return LiveStatus(status="ok")

    @get("/ready", sync_to_thread=True)
    def ready(self) -> ReadinessResponse:
        settings = get_settings()
        pool_configured = get_pool() is not None
        db_ok = db_available() if pool_configured else False
        return ReadinessResponse(
            status="ready" if (db_ok or not pool_configured) else "limited",
            database="ok"
            if db_ok
            else ("not_configured" if not pool_configured else "unavailable"),
            profile=settings.app_profile,
            external_requests=settings.external_requests_enabled,
            llm="configured" if settings.resolved_openai_api_key else "not_configured",
        )


class CapabilitiesController(Controller):
    path = "/capabilities"

    @get("/", sync_to_thread=True)
    def capabilities(self) -> CapabilitiesResponse:
        settings = get_settings()
        return CapabilitiesResponse(
            profile=settings.app_profile,
            runtime_mode="replay"
            if settings.app_profile == "replay"
            else ("live" if settings.external_requests_enabled else "limited"),
            map=MapCapabilities(
                tiles=bool(settings.tile_provider_config),
                osm_attribution_required=True,
            ),
            llm=LlmCapabilities(
                available=bool(settings.resolved_openai_api_key)
                and settings.external_requests_enabled,
                model=settings.llm_model,
            ),
            sources={
                "jeju_hub": bool(settings.jeju_project_key) and settings.external_requests_enabled,
                "kma_portal": bool(settings.kma_service_key) and settings.external_requests_enabled,
                "kma_hub": bool(settings.kma_hub_key) and settings.external_requests_enabled,
                "at": bool(settings.at_service_key) and settings.external_requests_enabled,
                "replay": True,
            },
            files={
                "notebook_export": settings.allow_notebook_export,
                "notebook_import": settings.allow_notebook_import,
                "share_file": settings.allow_share_file,
            },
            cache=CacheCapabilities(
                response_cache=settings.response_cache_enabled,
                semantic=bool(settings.domain_threshold_config),
            ),
        )
