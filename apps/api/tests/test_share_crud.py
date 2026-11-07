from datetime import date

import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import contacts, notebook, share
from gosari.sessions import Session


def make_draft(session):
    record, _ = notebook.execute(
        session,
        notebook.prepare_create(
            session,
            {
                "experience_date": "2026-04-12",
                "activity_text": "봄 채취",
                "public_evidence_ids": ["public-weather"],
            },
            2000,
        ),
    )
    contact, _ = contacts.execute(
        session,
        contacts.prepare_create(
            session,
            {
                "name": "어머니",
                "relationship": "가족",
            },
        ),
    )
    draft, _ = share.execute(
        session,
        share.prepare(
            session,
            {
                "items": [
                    {
                        "contact_id": contact,
                        "amount_value": 2,
                        "amount_unit": "봉지",
                        "status": "planned",
                    }
                ],
                "source_record_ids": [record],
            },
        )[0],
    )
    return draft, record, contact


def test_share_update_deliver_and_delete_preserve_references_and_revision():
    session = Session(Settings())
    draft_id, record, _ = make_draft(session)
    original = session.share_drafts[draft_id]
    assert original.public_evidence_ids == ["public-weather"]
    item = original.items[0].model_dump(mode="json")
    preview, _ = share.prepare(
        session,
        {"items": [{**item, "status": "delivered", "occurred_on": "2026-04-15"}]},
        "update",
        draft_id,
    )
    assert session.share_drafts[draft_id].items[0].status == "planned"
    assert preview.expected_revision == 1
    share.execute(session, preview)
    updated = session.share_drafts[draft_id]
    assert updated.revision == 2
    assert updated.items[0].occurred_on == date(2026, 4, 15)
    assert updated.source_record_ids == [record]
    assert updated.public_evidence_ids == ["public-weather"]
    assert updated.prepared_at == original.prepared_at
    with pytest.raises(GosariError) as error:
        share.execute(session, preview)
    assert error.value.code == "REVISION_CONFLICT"
    delete, display = share.prepare(session, {}, "delete", draft_id)
    assert display["items"][0]["recipient_alias"] == "어머니"
    assert draft_id in session.share_drafts
    share.execute(session, delete)
    assert draft_id not in session.share_drafts
    assert record in session.notebook


def test_share_history_can_be_corrected_after_contact_and_notebook_deletion():
    session = Session(Settings())
    draft_id, record, contact = make_draft(session)
    del session.contacts[contact]
    del session.notebook[record]
    preview, _ = share.prepare(session, {"message_enabled": False}, "update", draft_id)
    share.execute(session, preview)
    saved = session.share_drafts[draft_id]
    assert saved.items[0].recipient_alias == "어머니"
    assert saved.source_record_ids == [record]
    assert saved.public_evidence_ids == ["public-weather"]


def test_share_cannot_link_other_session_records_or_contacts():
    session = Session(Settings())
    draft_id, record, _ = make_draft(session)
    other = Session(Settings())
    with pytest.raises(GosariError):
        share.prepare(other, {}, "update", draft_id)
    with pytest.raises(GosariError):
        share.prepare(
            other,
            {
                "items": [{"recipient_alias": "친구", "amount_value": 1, "amount_unit": "kg"}],
                "source_record_ids": [record],
            },
        )


@pytest.mark.parametrize("refs", ["id", [1], [""], None])
def test_reference_lists_are_validated(refs):
    session = Session(Settings())
    with pytest.raises(GosariError):
        share.prepare(
            session,
            {
                "items": [{"recipient_alias": "친구", "amount_value": 1, "amount_unit": "kg"}],
                "public_evidence_ids": refs,
            },
        )
    with pytest.raises(GosariError):
        notebook.prepare_create(
            session,
            {"experience_date": "2026-04-12", "activity_text": "채취", "public_evidence_ids": refs},
            2000,
        )


def test_stale_form_cannot_overwrite_a_newer_share_revision():
    session = Session(Settings())
    draft_id, _, _ = make_draft(session)
    share.execute(
        session, share.prepare(session, {"message_enabled": False}, "update", draft_id)[0]
    )
    with pytest.raises(GosariError) as error:
        share.prepare(
            session, {"expected_revision": 1, "message_enabled": False}, "update", draft_id
        )
    assert error.value.code == "REVISION_CONFLICT"


def test_share_http_crud_requires_confirmation_and_keeps_other_records(monkeypatch):
    from litestar.testing import TestClient

    from gosari.app import create_app
    from gosari.sessions import SessionStore

    monkeypatch.setattr("gosari.app.open_pool", lambda settings: None)
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    monkeypatch.setattr("gosari.sessions._store", SessionStore(Settings()))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/sessions/")

        def confirm(preview):
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
            response = client.post("/api/v1/share/commit", json=body)
            assert response.status_code == 200
            assert response.json()["state"] == "committed"
            return response.json()

        created = client.post(
            "/api/v1/share/prepare",
            json={
                "items": [
                    {
                        "recipient_alias": "친구",
                        "amount_value": 1,
                        "amount_unit": "봉지",
                        "status": "planned",
                    }
                ]
            },
        ).json()
        assert client.get("/api/v1/share/").json()["drafts"] == []
        result = confirm(created)
        share_id = result["result_id"]
        update = client.post(
            "/api/v1/share/prepare",
            json={
                "action": "update",
                "share_draft_id": share_id,
                "payload": {
                    "expected_revision": 1,
                    "items": [
                        {
                            "recipient_alias": "친구",
                            "amount_value": 2,
                            "amount_unit": "봉지",
                            "status": "delivered",
                            "occurred_on": "2026-04-13",
                        }
                    ],
                },
            },
        )
        assert update.status_code == 200
        confirm(update.json())
        saved = client.get("/api/v1/share/").json()["drafts"][0]
        assert saved["revision"] == 2
        assert saved["items"][0]["status"] == "delivered"
        delete = client.post(
            "/api/v1/share/prepare",
            json={
                "action": "delete",
                "share_draft_id": share_id,
                "payload": {"expected_revision": 2},
            },
        ).json()
        assert len(client.get("/api/v1/share/").json()["drafts"]) == 1
        confirm(delete)
        assert client.get("/api/v1/share/").json()["drafts"] == []
