"""Acceptance regressions for consent binding and successful receipt retry."""

from datetime import timedelta

import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import notebook
from gosari.personal.approval import commit, issue_consent
from gosari.sessions import Session, utcnow


@pytest.fixture
def approval_session(monkeypatch):
    class MemoryStore:
        def save(self, session):
            pass

    monkeypatch.setattr("gosari.personal.approval.get_session_store", lambda: MemoryStore())
    return Session(Settings())


def args(preview, consent):
    return {
        "consent_id": consent.consent_id,
        "preview_id": preview.preview_id,
        "action": preview.action,
        "target_id": preview.target_id,
        "target_revision": preview.expected_revision,
        "hash_from_client": preview.preview_hash,
        "executor": notebook.execute,
    }


def create_committed(session):
    preview = notebook.prepare_create(
        session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(session, preview.preview_id, preview.preview_hash, "confirm")
    body = args(preview, consent)
    result = commit(session, **body)
    return preview, consent, body, result


@pytest.mark.parametrize(
    "change",
    [
        {"action": "notebook.delete"},
        {"target_id": "different-target"},
        {"target_revision": 99},
        {"hash_from_client": "different-hash"},
    ],
)
def test_success_receipt_rejects_changed_binding_fields(approval_session, change):
    _, _, body, _ = create_committed(approval_session)
    with pytest.raises(GosariError) as error:
        commit(approval_session, **{**body, **change})
    assert error.value.code == "PREVIEW_MISMATCH"
    assert len(approval_session.notebook) == 1
    assert len(approval_session.actions) == 1


def test_identical_success_receipt_is_retrievable_after_consent_expiry(approval_session):
    _, consent, body, first = create_committed(approval_session)
    consent.expires_at = utcnow() - timedelta(seconds=1)
    replayed = commit(approval_session, **body)
    assert replayed.action_id == first.action_id
    assert replayed.result_id == first.result_id
    assert len(approval_session.notebook) == 1


def test_consent_cannot_be_rebound_to_a_distinct_identical_preview(approval_session):
    _, _, _, saved = create_committed(approval_session)
    first = notebook.prepare_update(
        approval_session, saved.result_id, {"activity_text": "수정"}, 2000
    )
    other = notebook.prepare_update(
        approval_session, saved.result_id, {"activity_text": "수정"}, 2000
    )
    assert first.preview_hash == other.preview_hash
    consent = issue_consent(approval_session, first.preview_id, first.preview_hash, "confirm")
    with pytest.raises(GosariError) as error:
        commit(approval_session, **args(other, consent))
    assert error.value.code == "PREVIEW_MISMATCH"
    assert approval_session.notebook[saved.result_id].activity_text == "합성 수첩"


def test_an_uncommitted_preview_cannot_outlive_its_own_expiry(approval_session):
    preview = notebook.prepare_create(
        approval_session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(approval_session, preview.preview_id, preview.preview_hash, "confirm")
    preview.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(GosariError) as error:
        commit(approval_session, **args(preview, consent))
    assert error.value.code == "PREVIEW_EXPIRED"
    assert approval_session.notebook == {}


def test_twenty_identical_concurrent_commits_have_one_result(approval_session):
    from concurrent.futures import ThreadPoolExecutor

    preview = notebook.prepare_create(
        approval_session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(approval_session, preview.preview_id, preview.preview_hash, "confirm")
    body = args(preview, consent)
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: commit(approval_session, **body), range(20)))
    assert len({result.result_id for result in results}) == 1
    assert len({result.action_id for result in results}) == 1
    assert len(approval_session.notebook) == len(approval_session.actions) == 1


def test_two_concurrent_updates_cannot_apply_the_same_revision(approval_session):
    from concurrent.futures import ThreadPoolExecutor

    _, _, _, saved = create_committed(approval_session)
    bodies = []
    for text in ("첫 변경", "두 번째 변경"):
        preview = notebook.prepare_update(
            approval_session, saved.result_id, {"activity_text": text}, 2000
        )
        consent = issue_consent(
            approval_session, preview.preview_id, preview.preview_hash, "confirm"
        )
        bodies.append(args(preview, consent))

    def apply(body):
        try:
            return commit(approval_session, **body).state
        except GosariError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(apply, bodies))
    assert sorted(outcomes) == ["REVISION_CONFLICT", "committed"]
    assert approval_session.notebook[saved.result_id].revision == 2


@pytest.mark.parametrize("field", ["consent_id", "preview_id"])
def test_forged_approval_record_ids_cannot_change_records(approval_session, field):
    preview = notebook.prepare_create(
        approval_session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(approval_session, preview.preview_id, preview.preview_hash, "confirm")
    body = {**args(preview, consent), field: "model-invented-id"}
    with pytest.raises(GosariError):
        commit(approval_session, **body)
    assert not approval_session.notebook


def test_another_session_cannot_use_a_valid_approval(approval_session):
    preview = notebook.prepare_create(
        approval_session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(approval_session, preview.preview_id, preview.preview_hash, "confirm")
    other = Session(Settings())
    with pytest.raises(GosariError):
        commit(other, **args(preview, consent))
    assert not approval_session.notebook
    assert not other.notebook


def test_an_uncommitted_consent_cannot_outlive_its_expiry(approval_session):
    preview = notebook.prepare_create(
        approval_session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 수첩",
        },
        2000,
    )
    consent = issue_consent(approval_session, preview.preview_id, preview.preview_hash, "confirm")
    consent.expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(GosariError) as error:
        commit(approval_session, **args(preview, consent))
    assert error.value.code == "PREVIEW_EXPIRED"
    assert not approval_session.notebook
