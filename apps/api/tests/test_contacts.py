from contextlib import contextmanager
from datetime import date

import pytest
from litestar.testing import TestClient

from gosari.app import create_app
from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import contacts, share
from gosari.sessions import Session, SessionStore


def test_contact_updates_and_deletion_preserve_share_history() -> None:
    session = Session(Settings())
    create = contacts.prepare_create(
        session, {"name": "이웃", "relationship": "이웃", "notes": "봄에 나눔"}
    )
    assert session.contacts == {}
    id_, _ = contacts.execute(session, create)
    preview, _ = share.prepare(
        session,
        {
            "items": [
                {
                    "contact_id": id_,
                    "recipient_alias": "잘못된 이름",
                    "amount_value": 2,
                    "amount_unit": "봉지",
                    "occurred_on": "2026-04-12",
                    "status": "delivered",
                }
            ]
        },
    )
    share_id, _ = share.execute(session, preview)
    item = session.share_drafts[share_id].items[0]
    assert item.recipient_alias == "이웃"
    assert item.occurred_on == date(2026, 4, 12)
    assert item.status == "delivered"
    update = contacts.prepare_update(session, id_, {"name": "이웃 별칭"})
    contacts.execute(session, update)
    assert session.contacts[id_].revision == 2
    assert item.recipient_alias == "이웃"
    delete = contacts.prepare_delete(session, id_)
    assert delete.display_payload["name"] == "이웃 별칭"
    contacts.execute(session, delete)
    assert not session.contacts
    assert session.share_drafts[share_id].items[0].contact_id == id_
    assert session.share_drafts[share_id].items[0].recipient_alias == "이웃"


@pytest.mark.parametrize(
    "patch",
    [
        {"occurred_on": "2026-02-30"},
        {"status": "other"},
        {"status": "delivered"},
        {"amount_value": "NaN"},
        {"amount_value": -1},
    ],
)
def test_share_history_rejects_invalid_dates_status_and_amount(patch) -> None:
    session = Session(Settings())
    with pytest.raises(GosariError):
        share.prepare(
            session,
            {
                "items": [
                    {"recipient_alias": "친구", "amount_value": 1, "amount_unit": "봉지", **patch}
                ]
            },
        )


def test_contact_scope_and_revision_are_checked() -> None:
    session = Session(Settings())
    other = Session(Settings())
    id_, _ = contacts.execute(
        session, contacts.prepare_create(session, {"name": "친구", "relationship": "친구"})
    )
    with pytest.raises(GosariError):
        contacts.prepare_update(other, id_, {"name": "침범"})
    with pytest.raises(GosariError):
        share.prepare(
            other, {"items": [{"contact_id": id_, "amount_value": 1, "amount_unit": "봉지"}]}
        )
    first = contacts.prepare_update(session, id_, {"notes": "첫 수정"})
    second = contacts.prepare_update(session, id_, {"notes": "다른 수정"})
    contacts.execute(session, first)
    with pytest.raises(GosariError) as error:
        contacts.execute(session, second)
    assert error.value.code == "REVISION_CONFLICT"


def test_contact_and_share_persistence_roundtrip(monkeypatch) -> None:
    session = Session(Settings())
    id_, _ = contacts.execute(
        session,
        contacts.prepare_create(
            session, {"name": "친구", "relationship": "친구", "notes": "봄 고사리"}
        ),
    )
    share.execute(
        session,
        share.prepare(
            session,
            {
                "items": [
                    {
                        "contact_id": id_,
                        "amount_value": 1,
                        "amount_unit": "kg",
                        "status": "delivered",
                        "occurred_on": "2026-04-12",
                    }
                ]
            },
        )[0],
    )
    stored = {}

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Connection:
        def execute(self, sql, params=None):
            if "INSERT INTO app_session" in sql:
                stored["session"] = params
            if "INSERT INTO personal_contact" in sql:
                stored["contact"] = params
            if "INSERT INTO personal_share_draft" in sql:
                stored["share"] = params
            if "FROM app_session" in sql:
                return Cursor([stored["session"]])
            if "SELECT contact_id" in sql:
                p = stored["contact"]
                return Cursor([(p[0], *p[2:])])
            if "SELECT share_draft_id" in sql:
                p = stored["share"]
                return Cursor([(p[0], p[2], p[3].obj, p[4], p[5], p[6].obj, p[7].obj, p[8])])
            return Cursor([])

        def commit(self):
            pass

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr("gosari.sessions.db_available", lambda: True)
    monkeypatch.setattr("gosari.sessions.connection", connection)
    store = SessionStore(Settings())
    store.save(session)
    loaded = store._load_from_db(session.session_id)
    assert loaded is not None
    assert loaded.contacts[id_].name == "친구"
    assert loaded.contacts[id_].notes == "봄 고사리"
    restored_item = next(iter(loaded.share_drafts.values())).items[0]
    assert restored_item.contact_id == id_
    assert restored_item.occurred_on == date(2026, 4, 12)
    assert restored_item.status == "delivered"
    loaded.close()
    assert loaded.contacts == {}


def test_contact_http_approval_and_idempotency(monkeypatch) -> None:
    monkeypatch.setattr("gosari.app.open_pool", lambda settings: None)
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    monkeypatch.setattr("gosari.sessions._store", SessionStore(Settings()))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/sessions/")
        preview = client.post(
            "/api/v1/contacts/prepare", json={"payload": {"name": "어머니", "relationship": "가족"}}
        ).json()
        assert client.get("/api/v1/contacts/").json()["contacts"] == []
        consent = client.post(
            "/api/v1/consents/",
            json={
                "preview_id": preview["preview_id"],
                "preview_hash": preview["preview_hash"],
                "decision": "confirm",
            },
        ).json()
        body = {
            key: preview[key]
            for key in ("preview_id", "preview_hash", "action", "target_id", "target_revision")
        }
        body["consent_id"] = consent["consent_id"]
        first = client.post("/api/v1/contacts/commit", json=body)
        second = client.post("/api/v1/contacts/commit", json=body)
        assert first.status_code == second.status_code == 200
        assert first.json()["action_id"] == second.json()["action_id"]
        assert len(client.get("/api/v1/contacts/").json()["contacts"]) == 1
