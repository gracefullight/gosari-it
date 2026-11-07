"""Synthetic, hermetic acceptance regressions: retry budget and end/commit ordering."""

import threading
from contextlib import contextmanager
from typing import Any

import httpx
import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import notebook
from gosari.personal.approval import commit, issue_consent
from gosari.sessions import SessionStore
from gosari.sources.live import TransmissionGate


def test_retry_attempts_consume_the_source_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    gate = TransmissionGate(
        Settings(external_requests_enabled=True, source_daily_budget=1, max_retries=3)
    )
    monkeypatch.setattr(gate, "_pause", lambda _: None)

    def limited(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        return httpx.Response(429, headers={"Retry-After": "60"}, request=httpx.Request("GET", url))

    monkeypatch.setattr("gosari.sources.live.httpx.get", limited)
    with pytest.raises(GosariError) as error:
        gate.get_json("https://apis.data.go.kr/example", {})
    assert error.value.code == "BUDGET_EXCEEDED"
    assert len(calls) == 1


def test_retry_after_is_not_shortened(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    pauses: list[float] = []
    gate = TransmissionGate(
        Settings(external_requests_enabled=True, source_daily_budget=10, max_retries=1)
    )
    monkeypatch.setattr(gate, "_pause", pauses.append)

    def upstream(url: str, **kwargs: Any) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429 if calls == 1 else 200,
            headers={"Retry-After": "60"},
            json={"ok": True},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("gosari.sources.live.httpx.get", upstream)
    gate.get_json("https://apis.data.go.kr/example", {})
    assert pauses == [60.0]
    assert calls == 2


def test_session_end_cannot_be_undone_by_concurrent_commit_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The synthetic DB mirrors the relevant PostgreSQL ordering only: DELETE commits
    # before a later INSERT/UPSERT, which would recreate an active session.
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    store = SessionStore(Settings(db_password=None, db_password_file=None))
    session = store.create()
    database: dict[str, str] = {session.session_id: "active"}
    delete_seen = threading.Event()
    executor_entered = threading.Event()
    release_commit = threading.Event()
    failures: list[Exception] = []

    def save(current: Any) -> None:
        database[current.session_id] = current.lifecycle

    monkeypatch.setattr(store, "save", save)
    monkeypatch.setattr("gosari.personal.approval.get_session_store", lambda: store)
    preview = notebook.prepare_create(
        session,
        {"experience_date": "2026-04-15", "activity_text": "SYNTHETIC_ACCEPTANCE_RECORD"},
        2000,
    )
    consent = issue_consent(session, preview.preview_id, preview.preview_hash, "confirm")

    class Connection:
        def execute(self, statement: str, args: Any) -> None:
            assert "DELETE FROM app_session" in statement
            database.pop(args[0], None)
            delete_seen.set()

        def commit(self) -> None:
            pass

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr("gosari.sessions.db_available", lambda: True)
    monkeypatch.setattr("gosari.sessions.connection", connection)

    def execute(current: Any, draft: Any):
        executor_entered.set()
        assert release_commit.wait(2)
        return notebook.execute(current, draft)

    def commit_thread() -> None:
        try:
            commit(
                session,
                consent.consent_id,
                preview.preview_id,
                preview.action,
                preview.target_id,
                preview.expected_revision,
                preview.preview_hash,
                execute,
            )
        except Exception as error:
            failures.append(error)

    def end_thread() -> None:
        try:
            store.end(session.session_id)
        except Exception as error:
            failures.append(error)

    writer = threading.Thread(target=commit_thread)
    ending = threading.Thread(target=end_thread)
    writer.start()
    assert executor_entered.wait(2)
    ending.start()
    delete_seen.wait(0.1)
    release_commit.set()
    writer.join(2)
    ending.join(2)
    assert not writer.is_alive() and not ending.is_alive()
    assert not failures
    assert session.lifecycle == "closed"
    assert session.session_id not in store._sessions
    assert session.session_id not in database, (
        "end() deleted before commit's save; the active DB session was resurrected"
    )
