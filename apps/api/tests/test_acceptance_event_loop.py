import asyncio
import threading

import httpx

from gosari.app import create_app


def test_slow_database_probe_does_not_block_other_requests(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    probe_threads = []
    loop_thread = threading.get_ident()

    def slow_database_probe():
        probe_threads.append(threading.get_ident())
        entered.set()
        release.wait(timeout=1)
        return True

    monkeypatch.setattr("gosari.api.health.get_pool", lambda: object())
    monkeypatch.setattr("gosari.api.health.db_available", slow_database_probe)

    async def scenario():
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            pending = asyncio.create_task(client.get("/api/v1/health/ready"))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                assert not pending.done(), "DB 지연이 이벤트 루프를 차단했습니다"
                live = await asyncio.wait_for(client.get("/api/v1/health/live"), timeout=0.5)
                assert live.json() == {"status": "ok"}
                assert probe_threads[0] != loop_thread
            finally:
                release.set()
                response = await pending
            assert response.json()["database"] == "ok"

    asyncio.run(scenario())
