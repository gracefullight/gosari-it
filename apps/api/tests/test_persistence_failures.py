"""A failed durable write must never appear as a committed personal change."""

from secrets import token_hex

import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import approval, notebook
from gosari.sessions import Session, SessionStore


def test_configured_store_does_not_silently_skip_unavailable_database(monkeypatch):
    store = SessionStore(Settings(db_password=token_hex(16)))
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    with pytest.raises(GosariError, match="자료") as error:
        store.create()
    assert error.value.code == "DATABASE_UNAVAILABLE"
    assert not store._sessions


def test_commit_rolls_back_failed_save_and_allows_same_approval_retry(monkeypatch):
    class Store:
        fail = False

        def save(self, session):
            if self.fail:
                raise GosariError("DATABASE_UNAVAILABLE")

    store = Store()
    monkeypatch.setattr(approval, "get_session_store", lambda: store)
    session = Session(Settings())
    preview = notebook.prepare_create(
        session, {"experience_date": "2026-04-12", "activity_text": "합성 기록"}, 2000
    )
    consent = approval.issue_consent(session, preview.preview_id, preview.preview_hash, "confirm")
    args = (
        session,
        consent.consent_id,
        preview.preview_id,
        preview.action,
        preview.target_id,
        preview.expected_revision,
        preview.preview_hash,
        notebook.execute,
    )
    store.fail = True
    with pytest.raises(GosariError) as error:
        approval.commit(*args)
    assert error.value.code == "DATABASE_UNAVAILABLE"
    assert not session.notebook
    assert not session.actions
    assert not session.consents[consent.consent_id].used
    assert session.previews[preview.preview_id].state == "confirmed"
    store.fail = False
    committed = approval.commit(*args)
    assert committed.state == "committed"
    assert len(session.notebook) == 1
    assert approval.commit(*args).action_id == committed.action_id
    assert len(session.notebook) == 1


def test_database_failure_does_not_create_a_new_identity(monkeypatch):
    store = SessionStore(Settings())

    def fail(_session_id):
        raise GosariError("DATABASE_UNAVAILABLE")

    monkeypatch.setattr(store, "get", fail)
    with pytest.raises(GosariError) as error:
        store.get_or_create("existing-session")
    assert error.value.code == "DATABASE_UNAVAILABLE"
    assert not store._sessions


def test_failed_reset_preserves_the_current_session(monkeypatch):
    store = SessionStore(Settings(db_password=token_hex(16)))
    session = Session(Settings())
    store._sessions[session.session_id] = session
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    with pytest.raises(GosariError):
        store.end(session.session_id)
    assert store.get(session.session_id).lifecycle == "active"


def test_failed_preview_save_removes_unsaved_preview(monkeypatch):
    class Store:
        def save(self, session):
            raise GosariError("DATABASE_UNAVAILABLE")

    monkeypatch.setattr(approval, "get_session_store", lambda: Store())
    session = Session(Settings())
    with pytest.raises(GosariError):
        notebook.prepare_create(
            session, {"experience_date": "2026-04-12", "activity_text": "합성 기록"}, 2000
        )
    assert not session.previews
