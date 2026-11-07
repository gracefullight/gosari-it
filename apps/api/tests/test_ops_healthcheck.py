import httpx
import pytest

from gosari.ops import healthcheck


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, {"status": "ready", "database": "ok", "llm": "not_configured"}, 0),
        (200, {"status": "limited", "database": "unavailable"}, 1),
        (200, {"status": "ready", "database": "not_configured"}, 1),
        (503, {"status": "ready", "database": "ok"}, 1),
        (200, {"error": "HTTP_ERROR"}, 1),
    ],
)
def test_healthcheck_requires_ready_database(monkeypatch, status, body, expected):
    monkeypatch.setattr(
        healthcheck.httpx, "get", lambda *args, **kwargs: httpx.Response(status, json=body)
    )
    assert healthcheck.main() == expected
