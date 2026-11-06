"""분석 준비·작업 실행·상태·취소·이벤트 (SRS §8.2, §8.6)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from litestar import Controller, Request, get, post
from litestar.response import Response, ServerSentEvent

from gosari.agent.coordinator import get_coordinator
from gosari.api.deps import check_origin, current_session


class AnalysisController(Controller):
    path = "/analysis"

    @post("/prepare")
    async def prepare(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> dict[str, Any]:
        check_origin(request)
        session = current_session(request)
        return get_coordinator().prepare(session, data)

    @post("/jobs")
    async def create_job(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[dict[str, Any]]:
        check_origin(request)
        session = current_session(request)
        spec = data.get("spec", data)
        job = get_coordinator().run_job(session, spec)
        status = 200 if job.result is not None else 202
        return Response(job.to_dict(), status_code=status)


class JobsController(Controller):
    path = "/jobs"

    @get("/{job_id:str}")
    async def get_job(self, request: Request[Any, Any, Any], job_id: str) -> dict[str, Any]:
        session = current_session(request)
        return get_coordinator().get_job(session, job_id).to_dict()

    @post("/{job_id:str}/cancel")
    async def cancel(self, request: Request[Any, Any, Any], job_id: str) -> dict[str, Any]:
        check_origin(request)
        session = current_session(request)
        return get_coordinator().cancel_job(session, job_id).to_dict()

    @get("/{job_id:str}/events")
    async def events(self, request: Request[Any, Any, Any], job_id: str) -> ServerSentEvent:
        session = current_session(request)
        job = get_coordinator().get_job(session, job_id)

        async def stream() -> AsyncIterator[dict[str, str]]:
            sent = 0
            while True:
                events = job.events[sent:]
                for event in events:
                    yield {"data": json.dumps(event.model_dump(mode="json"), ensure_ascii=False)}
                sent = len(job.events)
                if job.stage.value in ("completed", "failed", "cancelled", "partial"):
                    break
                await asyncio.sleep(0.5)

        return ServerSentEvent(stream())
