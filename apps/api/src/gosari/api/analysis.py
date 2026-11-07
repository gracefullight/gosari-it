"""분석 준비·작업 실행·상태·취소·이벤트 (SRS §8.2, §8.6)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from litestar import Controller, Request, get, post
from litestar.concurrency import sync_to_thread
from litestar.response import Response, ServerSentEvent

from gosari.agent.coordinator import Job, get_coordinator
from gosari.api.deps import check_origin, current_session
from gosari.domain.envelope import JobResponse, PrepareResponse


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        request_id=job.request_id,
        stage=job.stage.value,
        created_at=job.created_at,
        result=job.result,
        error=job.error,
        events=job.events,
        model_usage=job.model_usage,
    )


class AnalysisController(Controller):
    path = "/analysis"

    @post("/prepare", sync_to_thread=True, status_code=200)
    def prepare(self, request: Request[Any, Any, Any], data: dict[str, Any]) -> PrepareResponse:
        check_origin(request)
        session = current_session(request)
        return PrepareResponse.model_validate(get_coordinator().prepare(session, data))

    @post("/jobs", sync_to_thread=True)
    def create_job(
        self, request: Request[Any, Any, Any], data: dict[str, Any]
    ) -> Response[JobResponse]:
        check_origin(request)
        session = current_session(request)
        spec = data.get("spec", data)
        job = get_coordinator().start_job(session, spec)
        status = 200 if job.result is not None else 202
        return Response(_job_response(job), status_code=status)


class JobsController(Controller):
    path = "/jobs"

    @get("/{job_id:str}", sync_to_thread=True)
    def get_job(self, request: Request[Any, Any, Any], job_id: str) -> JobResponse:
        session = current_session(request)
        return _job_response(get_coordinator().get_job(session, job_id))

    @post("/{job_id:str}/cancel", sync_to_thread=True)
    def cancel(self, request: Request[Any, Any, Any], job_id: str) -> JobResponse:
        check_origin(request)
        session = current_session(request)
        return _job_response(get_coordinator().cancel_job(session, job_id))

    @get("/{job_id:str}/events")
    async def events(self, request: Request[Any, Any, Any], job_id: str) -> ServerSentEvent:
        session = await sync_to_thread(current_session, request)
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
