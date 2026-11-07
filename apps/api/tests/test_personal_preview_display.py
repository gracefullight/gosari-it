from gosari.config import Settings
from gosari.personal import notebook, regions
from gosari.sessions import Session


def test_notebook_delete_preview_identifies_the_record_by_content() -> None:
    session = Session(Settings())
    created = notebook.prepare_create(
        session, {"experience_date": "2026-04-12", "activity_text": "선흘 채취 기록"}, 2000
    )
    record_id, revision = notebook.execute(session, created)
    preview = notebook.prepare_delete(session, record_id)
    assert preview.display_payload["activity_text"] == "선흘 채취 기록"
    assert preview.display_payload["experience_date"] == "2026-04-12"
    assert "record_id" not in preview.display_payload
    assert preview.canonical_payload == {"record_id": record_id}
    assert preview.target_id == record_id
    assert preview.expected_revision == revision
    notebook.execute(session, preview)
    assert record_id not in session.notebook


def test_region_delete_preview_identifies_the_region_by_name() -> None:
    session = Session(Settings())
    created = regions.prepare_create(
        session, {"kind": "interest", "local_alias": "선흘", "public_area_code": "조천읍"}
    )
    region_id, revision = regions.execute(session, created)
    preview = regions.prepare_delete(session, region_id)
    assert preview.display_payload["local_alias"] == "선흘"
    assert preview.display_payload["public_area_code"] == "조천읍"
    assert "region_id" not in preview.display_payload
    assert preview.canonical_payload == {"region_id": region_id}
    assert preview.target_id == region_id
    assert preview.expected_revision == revision
    regions.execute(session, preview)
    assert region_id not in session.regions
