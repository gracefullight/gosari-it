"""관측소 탐색·지도 준비. 정확 채취지 저장 없음, OSM 편집 없음."""

from typing import Any

from litestar import Controller, Request, get, post

from gosari.agent.analysis import AnalysisEngine
from gosari.api.deps import check_origin, current_session
from gosari.config import get_settings
from gosari.sessions import new_id


class StationsController(Controller):
    path = "/stations"

    @get("/")
    async def list_stations(self, request: Request[Any, Any, Any]) -> dict[str, Any]:
        current_session(request)
        engine = AnalysisEngine()
        envelope = engine.run(
            {"operation": "station_search", "source_ids": ["jeju_578"]}, new_id("req")
        )
        return envelope.model_dump(mode="json")


class MapsController(Controller):
    path = "/maps"

    @post("/prepare")
    async def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        check_origin(request)
        session = current_session(request)
        settings = get_settings()
        engine = AnalysisEngine()
        envelope = engine.run(
            {"operation": "station_search", "source_ids": ["jeju_578"]}, new_id("req")
        )
        stations = envelope.result.get("stations", [])
        return {
            "map": {
                "center": {"lat": 33.38, "lng": 126.55},
                "zoom": 10,
                "tile_provider_configured": bool(settings.tile_provider_config),
                "attribution": "© OpenStreetMap contributors (ODbL)",
                "notice": "관측소 위치는 공개 지점이며 개인 채취지가 아닙니다.",
            },
            "stations": stations,
            "selected_regions": [r.model_dump(mode="json") for r in session.regions.values()],
        }
