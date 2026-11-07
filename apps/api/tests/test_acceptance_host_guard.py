"""Host validation applies before API routing and SPA/static responses."""

import asyncio
import json
from pathlib import Path

import pytest
from litestar.testing import TestClient

from gosari.app import LocalHostMiddleware, SPAStaticMiddleware, create_app


def test_forged_host_is_rejected_on_read_only_api(monkeypatch) -> None:
    monkeypatch.setattr("gosari.app.open_pool", lambda *_: None)
    monkeypatch.setattr("gosari.app.close_pool", lambda: None)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get("/api/v1/health/live", headers={"Host": "attacker.invalid"})
    assert response.status_code == 403
    assert response.json()["error"] == "ORIGIN_DENIED"


def run_guard(headers: list[tuple[bytes, bytes]], path: str, ui_dir: Path | None = None):
    called = []
    sent = []

    async def downstream(scope, receive, send):
        called.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"api"})

    app = SPAStaticMiddleware(downstream, ui_dir) if ui_dir else downstream
    guarded = LocalHostMiddleware(app)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(
        guarded({"type": "http", "method": "GET", "path": path, "headers": headers}, receive, send)
    )
    return sent, called


@pytest.mark.parametrize(
    "host",
    [
        b"127.0.0.1",
        b"127.0.0.1:8765",
        b"localhost",
        b"LOCALHOST:5173",
        b"[::1]",
        b"[::1]:8000",
        b"0.0.0.0",
        b"app:8765",
    ],
)
def test_exact_local_hosts_remain_allowed(host: bytes) -> None:
    sent, called = run_guard([(b"host", host)], "/api/v1/health/live")
    assert sent[0]["status"] == 200
    assert called == ["/api/v1/health/live"]


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [(b"host", b"")],
        [(b"host", b"attacker.invalid")],
        [(b"host", b"localhost.attacker.invalid")],
        [(b"host", b"localhost@attacker.invalid")],
        [(b"host", b"localhost/anything")],
        [(b"host", b"localhost#fragment")],
        [(b"host", b"localhost:bad")],
        [(b"host", b"localhost:65536")],
        [(b"host", b"localhost:0")],
        [(b"host", b" localhost")],
        [(b"host", b"localhost,attacker.invalid")],
        [(b"host", b"[::1]garbage")],
        [(b"host", b"localhost"), (b"host", b"attacker.invalid")],
        [(b"host", b"local\xffhost")],
    ],
)
@pytest.mark.parametrize("path", ["/api/v1/health/live", "/", "/notebook/new", "/assets/app.js"])
def test_bad_or_missing_hosts_are_rejected_before_api_and_static(
    headers, path, tmp_path: Path
) -> None:
    (tmp_path / "index.html").write_text("<p>SYNTHETIC_STATIC</p>")
    sent, called = run_guard(headers, path, tmp_path)
    assert sent[0]["status"] == 403
    assert not called
    assert json.loads(sent[1]["body"])["error"] == "ORIGIN_DENIED"
    assert b"SYNTHETIC_STATIC" not in sent[1]["body"]


def test_allowed_static_response_still_works(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<p>SYNTHETIC_STATIC</p>")
    sent, called = run_guard([(b"host", b"127.0.0.1:8765")], "/notebook/new", tmp_path)
    assert sent[0]["status"] == 200
    assert not called
    assert b"SYNTHETIC_STATIC" in sent[1]["body"]
