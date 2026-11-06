"""건강·준비·기능 가용성. 외부 유료 호출을 하지 않는다."""

from typing import Any

from litestar import Controller, get

from gosari.config import get_settings
from gosari.db import db_available, get_pool


class HealthController(Controller):
    path = "/health"

    @get("/live")
    async def live(self) -> dict[str, str]:
        return {"status": "ok"}

    @get("/ready")
    async def ready(self) -> dict[str, Any]:
        settings = get_settings()
        pool_configured = get_pool() is not None
        db_ok = db_available() if pool_configured else False
        return {
            "status": "ready" if (db_ok or not pool_configured) else "limited",
            "database": "ok"
            if db_ok
            else ("not_configured" if not pool_configured else "unavailable"),
            "profile": settings.app_profile,
            "external_requests": settings.external_requests_enabled,
            "llm": "configured" if settings.resolved_openai_api_key else "not_configured",
        }


class CapabilitiesController(Controller):
    path = "/capabilities"

    @get("/")
    async def capabilities(self) -> dict[str, Any]:
        settings = get_settings()
        return {
            "profile": settings.app_profile,
            "runtime_mode": "replay"
            if settings.app_profile == "replay"
            else ("live" if settings.external_requests_enabled else "limited"),
            "map": {
                "tiles": bool(settings.tile_provider_config),
                "osm_attribution_required": True,
            },
            "llm": {
                "available": bool(settings.resolved_openai_api_key)
                and settings.external_requests_enabled,
                "model": settings.llm_model,
            },
            "sources": {
                "jeju_hub": bool(settings.jeju_project_key) and settings.external_requests_enabled,
                "kma_portal": bool(settings.kma_service_key) and settings.external_requests_enabled,
                "kma_hub": bool(settings.kma_hub_key) and settings.external_requests_enabled,
                "at": bool(settings.at_service_key) and settings.external_requests_enabled,
                "replay": True,
            },
            "files": {
                "notebook_export": settings.allow_notebook_export,
                "notebook_import": settings.allow_notebook_import,
                "share_file": settings.allow_share_file,
            },
            "cache": {
                "response_cache": settings.response_cache_enabled,
                "semantic": bool(settings.domain_threshold_config),
            },
        }
