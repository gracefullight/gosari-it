from typing import Any

import pytest

from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.personal import regions
from gosari.sessions import Session


def test_region_pin_can_be_saved_without_an_address_and_updated() -> None:
    session = Session(Settings())
    preview = regions.prepare_create(
        session, {"kind": "interest", "local_alias": "새 핀", "latitude": 33.4, "longitude": 126.7}
    )
    region_id, _ = regions.execute(session, preview)
    saved = session.regions[region_id]
    assert saved.public_area_code is None
    assert (saved.latitude, saved.longitude) == (33.4, 126.7)
    changed = regions.prepare_update(session, region_id, {"latitude": 33.5, "longitude": 126.8})
    regions.execute(session, changed)
    assert session.regions[region_id].latitude == 33.5
    deletion = regions.prepare_delete(session, region_id)
    assert deletion.display_payload["latitude"] == 33.5
    assert deletion.display_payload["longitude"] == 126.8
    regions.execute(session, deletion)
    assert region_id not in session.regions


@pytest.mark.parametrize(
    "payload", [{"public_area_code": "제주시 조천읍"}, {"coarse_grid": "제주 동부"}]
)
def test_legacy_region_without_pin_is_still_valid(payload: dict[str, Any]) -> None:
    session = Session(Settings())
    preview = regions.prepare_create(
        session, {"kind": "interest", "local_alias": "선흘", **payload}
    )
    region_id, _ = regions.execute(session, preview)
    assert session.regions[region_id].latitude is None


@pytest.mark.parametrize(
    "coordinates",
    [
        {},
        {"latitude": 33},
        {"latitude": 91, "longitude": 126},
        {"latitude": 33, "longitude": 181},
        {"latitude": 33, "longitude": float("nan")},
        {"latitude": float("inf"), "longitude": 126},
        {"latitude": "bad", "longitude": 126},
        {"latitude": True, "longitude": 126},
    ],
)
def test_region_rejects_invalid_or_missing_locations(coordinates: dict[str, Any]) -> None:
    session = Session(Settings())
    with pytest.raises(GosariError):
        regions.prepare_create(session, {"kind": "interest", "local_alias": "핀", **coordinates})


def test_region_visit_date_survives_create_update_and_delete_preview() -> None:
    session = Session(Settings())
    created = regions.prepare_create(
        session,
        {
            "kind": "existing",
            "local_alias": "선흘",
            "public_area_code": "조천읍",
            "visited_on": "2026-04-12",
        },
    )
    region_id, _ = regions.execute(session, created)
    assert session.regions[region_id].visited_on.isoformat() == "2026-04-12"
    changed = regions.prepare_update(session, region_id, {"local_alias": "선흘 입구"})
    regions.execute(session, changed)
    assert session.regions[region_id].visited_on.isoformat() == "2026-04-12"
    assert regions.prepare_delete(session, region_id).display_payload["visited_on"] == "2026-04-12"
    changed_date = regions.prepare_update(session, region_id, {"visited_on": "2026-04-15"})
    regions.execute(session, changed_date)
    assert session.regions[region_id].visited_on.isoformat() == "2026-04-15"
    cleared = regions.prepare_update(session, region_id, {"visited_on": None})
    regions.execute(session, cleared)
    assert session.regions[region_id].visited_on is None


@pytest.mark.parametrize("visited_on", ["2026-02-30", "20260412", "12/04/2026", "", True, 123])
def test_region_rejects_invalid_visit_dates(visited_on: Any) -> None:
    with pytest.raises(GosariError):
        regions.prepare_create(
            Session(Settings()),
            {
                "kind": "existing",
                "local_alias": "선흘",
                "public_area_code": "조천읍",
                "visited_on": visited_on,
            },
        )


def test_region_visit_date_is_written_and_restored_by_sql_adapter(monkeypatch) -> None:
    from contextlib import contextmanager

    from gosari.sessions import SessionStore

    settings = Settings()
    session = Session(settings)
    prepared = regions.prepare_create(
        session,
        {
            "kind": "existing",
            "local_alias": "선흘",
            "public_area_code": "조천읍",
            "visited_on": "2026-04-12",
            "latitude": 33.4,
            "longitude": 126.7,
        },
    )
    region_id, _ = regions.execute(session, prepared)
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
            if "INSERT INTO personal_private_region" in sql:
                assert "visited_on" in sql
                stored["region"] = params
            if "FROM app_session" in sql:
                return Cursor(
                    [
                        (
                            session.session_id,
                            session.created_at,
                            session.expires_at,
                            session.last_activity_at,
                            "active",
                        )
                    ]
                )
            if "SELECT region_id" in sql and "FROM personal_private_region" in sql:
                assert "visited_on" in sql
                row = stored["region"]
                return Cursor(
                    [
                        (
                            row[0],
                            row[2],
                            row[3],
                            row[4],
                            row[5],
                            row[6],
                            row[7].obj,
                            row[8],
                            row[9],
                            row[10],
                            row[11],
                            row[12],
                        )
                    ]
                )
            return Cursor([])

        def commit(self):
            return None

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr("gosari.sessions.db_available", lambda: True)
    monkeypatch.setattr("gosari.sessions.connection", connection)
    store = SessionStore(settings)
    store.save(session)
    assert stored["region"][-1].isoformat() == "2026-04-12"
    loaded = store._load_from_db(session.session_id)
    assert loaded is not None
    assert loaded.regions[region_id].visited_on.isoformat() == "2026-04-12"
    assert loaded.regions[region_id].latitude == 33.4
