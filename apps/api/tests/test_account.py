"""회원 가입·로그인과 익명 기록 병합 계약."""

from typing import Any

import pytest
from litestar.testing import TestClient

from gosari.app import create_app
from gosari.domain.errors import GosariError
from gosari.members import MemberStore, validate_credentials


@pytest.fixture
def client(monkeypatch):
    from gosari.agent.coordinator import Coordinator
    from gosari.api import account
    from gosari.config import Settings

    monkeypatch.setattr(
        "gosari.agent.coordinator._coordinator", Coordinator(Settings(app_profile="replay"))
    )
    monkeypatch.setattr("gosari.members._store", MemberStore(Settings(app_profile="replay")))
    account.limiter.reset()
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


def _session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions/")
    assert response.status_code == 201
    return response.json()["session_id"]


def _create_contact(client: TestClient, name: str) -> None:
    prepared = client.post(
        "/api/v1/contacts/prepare",
        json={"action": "create", "payload": {"name": name, "relationship": "이웃"}},
    )
    assert prepared.status_code in (200, 201), prepared.text
    preview = prepared.json()
    consent = client.post(
        "/api/v1/consents/",
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
            "decision": "confirm",
        },
    )
    assert consent.status_code == 201, consent.text
    committed = client.post(
        "/api/v1/contacts/commit",
        json={
            "consent_id": consent.json()["consent_id"],
            "preview_id": preview["preview_id"],
            "action": preview["action"],
            "target_id": preview["target_id"],
            "target_revision": preview["target_revision"],
            "preview_hash": preview["preview_hash"],
        },
    )
    assert committed.status_code == 200, committed.text


def _contact_names(client: TestClient) -> list[str]:
    response = client.get("/api/v1/contacts/")
    assert response.status_code == 200
    return [c["name"] for c in response.json()["contacts"]]


def test_credentials_validation_rejects_short_or_invalid_values() -> None:
    with pytest.raises(GosariError) as short:
        validate_credentials("ab", "12345678")
    assert short.value.extra["fields"] == ["login_id"]
    with pytest.raises(GosariError) as weak:
        validate_credentials("gosari", "1234567")
    assert weak.value.extra["fields"] == ["password"]
    validate_credentials("gosari_01", "correct horse battery")


def test_anonymous_session_reports_no_login(client: TestClient) -> None:
    sid = _session(client)
    me = client.get("/api/v1/account/")
    assert me.status_code == 200
    assert me.json() == {"login_id": None, "session_id": sid, "merged": {}}


def test_signup_links_current_session_and_keeps_records(client: TestClient) -> None:
    sid = _session(client)
    _create_contact(client, "옆집 이웃")
    signed = client.post(
        "/api/v1/account/signup", json={"login_id": "Gosari", "password": "spring-2026!"}
    )
    assert signed.status_code == 201, signed.text
    body = signed.json()
    assert body["login_id"] == "gosari"
    assert body["session_id"] == sid
    assert body["merged"] == {}
    assert _contact_names(client) == ["옆집 이웃"]


def test_login_from_another_browser_merges_anonymous_records_into_member_session(
    client: TestClient,
) -> None:
    home_sid = _session(client)
    _create_contact(client, "어머니")
    assert (
        client.post(
            "/api/v1/account/signup", json={"login_id": "gosari", "password": "spring-2026!"}
        ).status_code
        == 201
    )

    client.cookies.clear()
    other_sid = _session(client)
    assert other_sid != home_sid
    _create_contact(client, "직장 동료")

    logged = client.post(
        "/api/v1/account/login", json={"login_id": "gosari", "password": "spring-2026!"}
    )
    assert logged.status_code == 200, logged.text
    body = logged.json()
    assert body["session_id"] == home_sid
    assert body["merged"] == {"notebook": 0, "regions": 0, "contacts": 1}
    assert client.cookies.get("gosari_session") == home_sid
    assert _contact_names(client) == ["어머니", "직장 동료"]

    gone = client.get("/api/v1/contacts/", headers={"x-gosari-session": other_sid})
    assert gone.status_code in (401, 410) or gone.json()["contacts"] == []


def test_wrong_password_and_duplicate_login_id_are_rejected(client: TestClient) -> None:
    _session(client)
    assert (
        client.post(
            "/api/v1/account/signup", json={"login_id": "gosari", "password": "spring-2026!"}
        ).status_code
        == 201
    )
    client.cookies.clear()
    _session(client)
    dup = client.post(
        "/api/v1/account/signup", json={"login_id": "gosari", "password": "another-pass"}
    )
    assert dup.status_code == 409
    assert dup.json()["error"] == "LOGIN_ID_TAKEN"
    wrong = client.post(
        "/api/v1/account/login", json={"login_id": "gosari", "password": "wrong-pass!"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"] == "LOGIN_FAILED"


def test_login_attempts_are_rate_limited_per_client(client: TestClient) -> None:
    from gosari.api import account

    _session(client)
    last: Any = None
    for _ in range(account.AUTH_ATTEMPT_LIMIT + 1):
        last = client.post(
            "/api/v1/account/login", json={"login_id": "nobody", "password": "wrong-pass!"}
        )
    assert last is not None
    assert last.status_code == 429
    assert last.json()["error"] == "LOCAL_BUSY"


def test_logout_issues_fresh_anonymous_session_and_keeps_member_records(
    client: TestClient,
) -> None:
    home_sid = _session(client)
    _create_contact(client, "어머니")
    assert (
        client.post(
            "/api/v1/account/signup", json={"login_id": "gosari", "password": "spring-2026!"}
        ).status_code
        == 201
    )

    out = client.post("/api/v1/account/logout")
    assert out.status_code == 200
    fresh = out.json()
    assert fresh["login_id"] is None
    assert fresh["session_id"] != home_sid
    assert _contact_names(client) == []

    back = client.post(
        "/api/v1/account/login", json={"login_id": "gosari", "password": "spring-2026!"}
    )
    assert back.status_code == 200
    assert back.json()["session_id"] == home_sid
    assert _contact_names(client) == ["어머니"]
