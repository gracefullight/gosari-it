import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import notebook
from gosari.sessions import Session


def test_notebook_location_survives_create_update_and_recall():
    session = Session(Settings())
    payload = {
        "experience_date": "2026-04-12",
        "activity_text": "선흘 채취",
        "location_address": "제주특별자치도 제주시 조천읍",
        "latitude": 33.45,
        "longitude": 126.7,
    }
    preview = notebook.prepare_create(session, payload, 2000)
    record_id, _ = notebook.execute(session, preview)
    recalled = notebook.search(session)[0]
    assert recalled.location_address == payload["location_address"]
    assert (recalled.latitude, recalled.longitude) == (33.45, 126.7)
    changed = notebook.prepare_update(session, record_id, {"activity_text": "비 온 뒤 채취"}, 2000)
    notebook.execute(session, changed)
    assert session.notebook[record_id].latitude == 33.45
    cleared = notebook.prepare_update(
        session, record_id, {"location_address": None, "latitude": None, "longitude": None}, 2000
    )
    notebook.execute(session, cleared)
    assert session.notebook[record_id].latitude is None


@pytest.mark.parametrize(
    "coordinates",
    [
        {"latitude": 33},
        {"latitude": 91, "longitude": 126},
        {"latitude": 33, "longitude": float("nan")},
        {"latitude": "bad", "longitude": 126},
    ],
)
def test_notebook_rejects_incomplete_or_invalid_coordinates(coordinates):
    session = Session(Settings())
    with pytest.raises(GosariError):
        notebook.prepare_create(
            session, {"experience_date": "2026-04-12", "activity_text": "채취", **coordinates}, 2000
        )


@pytest.fixture(autouse=True)
def isolated_preview_store(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "gosari.personal.approval.get_session_store",
        lambda: SimpleNamespace(save=lambda session: None),
    )


@pytest.mark.parametrize("label", [None, "", "  ", "직접 붙인 위치 이름", "제주시 조천읍"])
def test_location_preview_label_preserves_canonical_coordinates_and_approved_save(label):
    from gosari.personal import approval

    session = Session(Settings())
    payload = {
        "experience_date": "2026-04-12",
        "activity_text": "합성 수첩 메모",
        "location_address": label,
        "latitude": 33.456789123,
        "longitude": 126.705432198,
    }
    original = dict(payload)
    preview = notebook.prepare_create(session, payload, 2000)
    expected_label = label.strip() if label and label.strip() else "지도에서 선택한 위치"
    assert preview.display_payload["location_address"] == expected_label
    assert "latitude" not in preview.display_payload and "longitude" not in preview.display_payload
    assert preview.canonical_payload == {**original, "public_evidence_ids": []}
    assert payload == original
    assert preview.preview_hash == approval.preview_hash(
        preview.action,
        preview.target_id,
        preview.expected_revision,
        preview.schema_version,
        preview.canonical_payload,
    )
    consent = approval.issue_consent(session, preview.preview_id, preview.preview_hash, "confirm")
    result = approval.commit(
        session,
        consent.consent_id,
        preview.preview_id,
        preview.action,
        preview.target_id,
        preview.expected_revision,
        preview.preview_hash,
        notebook.execute,
    )
    entry = session.notebook[result.result_id]
    assert result.state == "committed"
    assert (entry.latitude, entry.longitude) == (original["latitude"], original["longitude"])
    assert entry.location_address == label


def test_coordinate_only_update_delete_preview_preserves_targets_and_hides_coordinates():
    from gosari.personal.approval import preview_hash

    session = Session(Settings())
    created = notebook.prepare_create(
        session,
        {
            "experience_date": "2026-04-12",
            "activity_text": "합성 기록",
            "latitude": 33.456789123,
            "longitude": 126.705432198,
        },
        2000,
    )
    record_id, _ = notebook.execute(session, created)
    changed = notebook.prepare_update(session, record_id, {"activity_text": "합성 수정"}, 2000)
    assert changed.display_payload["location_address"] == "지도에서 선택한 위치"
    assert changed.expected_revision == 1
    assert changed.canonical_payload["latitude"] == 33.456789123
    assert changed.canonical_payload["longitude"] == 126.705432198
    assert "latitude" not in changed.display_payload and "longitude" not in changed.display_payload
    assert changed.preview_hash == preview_hash(
        changed.action,
        record_id,
        1,
        changed.schema_version,
        changed.canonical_payload,
    )
    moved = notebook.prepare_update(session, record_id, {"latitude": 33.456789124}, 2000)
    assert moved.preview_hash != changed.preview_hash
    deleted = notebook.prepare_delete(session, record_id)
    assert deleted.display_payload["location_address"] == "지도에서 선택한 위치"
    assert deleted.canonical_payload == {"record_id": record_id}


def test_linked_region_label_is_resolved_only_from_current_session():
    from gosari.personal import PrivateRegion
    from gosari.sessions import utcnow

    owner, other = Session(Settings()), Session(Settings())
    now = utcnow()
    owner.regions["qa-region"] = PrivateRegion(
        region_id="qa-region",
        kind="interest",
        local_alias="합성 관심 위치",
        created_at=now,
        updated_at=now,
    )
    payload = {
        "experience_date": "2026-04-12",
        "activity_text": "합성 기록",
        "private_region_id": "qa-region",
        "latitude": 33.45,
        "longitude": 126.7,
    }
    preview = notebook.prepare_create(owner, payload, 2000)
    assert preview.display_payload["location_address"] == "합성 관심 위치"
    isolated = notebook.prepare_create(other, payload, 2000)
    assert isolated.display_payload["location_address"] == "지도에서 선택한 위치"
    absent = notebook.prepare_create(
        owner,
        {
            "experience_date": "2026-04-12",
            "activity_text": "위치 없는 합성 기록",
        },
        2000,
    )
    assert not absent.display_payload.get("location_address")
