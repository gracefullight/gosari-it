"""Actual Litestar/ASGI chat and event framing without a provider or database."""

import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from gosari.agent.coordinator import Coordinator, Job
from gosari.app import create_app
from gosari.config import Settings
from gosari.domain import JobStage
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.sessions import Session


@pytest.fixture
def chat_api(monkeypatch):
    owner = Session(Settings(), session_id="sse-owner")
    other = Session(Settings(), session_id="sse-other")
    job = Job("job-sse", "request-sse")
    job.stage = JobStage.RUNNING
    owner.jobs[job.job_id] = job.to_dict()
    # Keep the real ownership check, replacing only job execution.
    coordinator = object.__new__(Coordinator)
    coordinator._lock = threading.Lock()
    coordinator._jobs = {job.job_id: job}
    calls = []

    def start_chat(session, payload):
        calls.append((session.session_id, payload))
        return job, None

    def session_for(session_id):
        if not session_id:
            raise GosariError("SESSION_REQUIRED")
        sessions = {owner.session_id: owner, other.session_id: other}
        if session_id not in sessions:
            raise GosariError("SESSION_EXPIRED")
        return sessions[session_id]

    monkeypatch.setattr(coordinator, "start_chat", start_chat)
    monkeypatch.setattr("gosari.api.analysis.get_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        "gosari.api.deps.get_session_store", lambda: SimpleNamespace(get=session_for)
    )
    return SimpleNamespace(
        app=create_app(), job=job, owner=owner, other=other, coordinator=coordinator, calls=calls
    )


def client(api, session=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app),
        base_url="http://localhost",
        headers={"x-gosari-session": session or api.owner.session_id},
    )


def frames(response):
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    parsed = []
    for block in response.text.replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line and not line.startswith(":"):
                key, value = line.split(":", 1)
                fields[key] = value.lstrip(" ")
        if "data" in fields:
            fields["data"] = json.loads(fields["data"])
            parsed.append(fields)
    return parsed


def finish(job):
    job.stage = JobStage.COMPLETED
    job.result = ResultEnvelope(
        request_id=job.request_id, data_status="complete", result={"station_count": 43}
    )
    job.emit_event("done", {"stage": "completed", "result": job.result.model_dump(mode="json")})


def test_chat_accepts_conversation_and_returns_pollable_job(chat_api):
    async def run():
        async with client(chat_api) as http:
            payload = {"text": "제주 현재 날씨", "conversation_id": "conversation-public"}
            response = await http.post("/api/v1/analysis/chat", json=payload)
            assert response.status_code == 202
            body = response.json()
            assert body["kind"] == "job"
            assert body["job_id"] == chat_api.job.job_id
            assert body["request_id"] == chat_api.job.request_id
            assert body["stage"] == "running"
            assert chat_api.calls == [(chat_api.owner.session_id, payload)]
            polled = await http.get(f"/api/v1/jobs/{body['job_id']}")
            assert polled.status_code == 200
            assert polled.json()["job_id"] == body["job_id"]

    asyncio.run(run())


def test_chat_condition_request_is_a_confirmation_without_an_event_job(chat_api, monkeypatch):
    preparation = {
        "classification": "public",
        "feature": "price",
        "needs_confirmation": True,
        "form": {"questions": ["거래일을 선택해 주세요."]},
    }
    monkeypatch.setattr(chat_api.coordinator, "start_chat", lambda *args: (None, preparation))

    async def run():
        async with client(chat_api) as http:
            response = await http.post("/api/v1/analysis/chat", json={"text": "가격"})
            assert response.status_code == 200
            assert response.json() == {
                "kind": "confirmation",
                "preparation": preparation | {"spec": None},
            }

    asyncio.run(run())


def test_events_preserve_id_type_json_delta_tools_and_terminal_result(chat_api):
    job = chat_api.job
    job.emit("accepted", "요청을 받았습니다.")
    job.emit_event("assistant_delta", {"delta": "제주\n날씨"})
    job.emit_event("tool_started", {"tool_call_id": "call-1", "name": "current_observation"})
    job.emit_event("tool_completed", {"tool_call_id": "call-1", "summary": "관측 43곳"})
    job.emit_event("assistant_completed", {"text": "제주 날씨를 확인했습니다."})
    finish(job)

    async def run():
        async with client(chat_api) as http:
            result = frames(await http.get(f"/api/v1/jobs/{job.job_id}/events"))
        assert [item["event"] for item in result] == [event.event_type for event in job.events]
        assert [item["id"] for item in result] == [event.event_id for event in job.events]
        assert len({item["id"] for item in result}) == len(job.events)
        for item in result:
            assert item["data"]["event_id"] == item["id"]
            assert item["data"]["job_id"] == job.job_id
            assert item["data"]["request_id"] == job.request_id
            assert item["data"]["timestamp"]
        assert result[0]["data"]["message"] == "요청을 받았습니다."
        assert result[1]["data"]["delta"] == "제주\n날씨"
        assert result[2]["data"]["tool_call_id"] == result[3]["data"]["tool_call_id"]
        assert result[-1]["data"]["result"]["result"]["station_count"] == 43

    asyncio.run(run())


@pytest.mark.parametrize("last", ["middle", "done", "unknown"])
def test_last_event_id_replays_only_unseen_events(chat_api, last):
    job = chat_api.job
    job.emit_event("assistant_delta", {"delta": "제주"})
    job.emit_event("assistant_completed", {"text": "제주 날씨"})
    finish(job)
    index = {"middle": 0, "done": 2}.get(last)
    last_id = job.events[index].event_id if index is not None else "unknown-event"
    expected = job.events[index + 1 :] if index is not None else job.events

    async def run():
        async with client(chat_api) as http:
            response = await asyncio.wait_for(
                http.get(f"/api/v1/jobs/{job.job_id}/events", headers={"Last-Event-ID": last_id}),
                timeout=2,
            )
        assert [item["id"] for item in frames(response)] == [event.event_id for event in expected]

    asyncio.run(run())


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_other_session_cannot_read_job_or_event_stream(chat_api, suffix):
    finish(chat_api.job)

    async def run():
        async with client(chat_api, chat_api.other.session_id) as http:
            response = await http.get(f"/api/v1/jobs/{chat_api.job.job_id}{suffix}")
        assert response.status_code == 404
        assert response.json()["error"] == "RESOURCE_NOT_FOUND"
        assert chat_api.job.request_id not in response.text

    asyncio.run(run())


def test_terminal_stage_does_not_close_stream_before_delayed_done(chat_api):
    job = chat_api.job
    job.stage = JobStage.COMPLETED
    job.emit_event("assistant_delta", {"delta": "제주"})

    async def run():
        async with client(chat_api) as http:
            pending = asyncio.create_task(http.get(f"/api/v1/jobs/{job.job_id}/events"))
            try:
                await asyncio.sleep(0.12)
                assert not pending.done(), "A terminal stage alone must not truncate final events"
                job.emit_event("assistant_completed", {"text": "제주 날씨"})
                finish(job)
                response = await asyncio.wait_for(pending, timeout=2)
                assert [item["event"] for item in frames(response)] == [
                    "assistant_delta",
                    "assistant_completed",
                    "done",
                ]
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

    asyncio.run(run())
