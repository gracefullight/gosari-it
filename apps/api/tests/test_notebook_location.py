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
