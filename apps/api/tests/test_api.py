"""HTTP 계약 통합 테스트 — SRS §8, §12 승인 프로토콜·세션 격리."""

import time
from typing import Any

import pytest
from litestar.testing import TestClient

from gosari.app import create_app


@pytest.fixture
def client(monkeypatch):
    from gosari.agent.coordinator import Coordinator
    from gosari.config import Settings
    from gosari.domain import CacheResolution

    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *args, **kwargs: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr(
        "gosari.agent.coordinator._coordinator", Coordinator(Settings(app_profile="replay"))
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as c:
        yield c


def _run_analysis(client: TestClient, *, json: dict[str, Any]):
    response = client.post("/api/v1/analysis/jobs", json=json)
    if response.status_code not in (200, 202):
        return response
    job = response.json()
    deadline = time.monotonic() + 10
    while job["stage"] not in ("completed", "failed", "cancelled", "partial"):
        assert time.monotonic() < deadline
        time.sleep(0.05)
        response = client.get(f"/api/v1/jobs/{job['job_id']}")
        job = response.json()
    return response


def _create_session(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/sessions/")
    assert response.status_code == 201
    return response.json()


def _notebook_preview(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/notebook/prepare",
        json={
            "action": "create",
            "payload": {
                "experience_date": "2026-04-12",
                "companion_aliases": ["가상 동행자"],
                "activity_text": "합성 시연용 기록입니다.",
                "amount_value": 1,
                "amount_unit": "봉지",
            },
        },
    )
    assert response.status_code == 201 or response.status_code == 200
    return response.json()


def _consent(client: TestClient, preview: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/consents/",
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": preview["preview_hash"],
            "decision": "confirm",
        },
    )
    assert response.status_code == 201
    return response.json()


def _commit_body(preview: dict[str, Any], consent: dict[str, Any]) -> dict[str, Any]:
    return {
        "consent_id": consent["consent_id"],
        "preview_id": preview["preview_id"],
        "action": preview["action"],
        "target_id": preview["target_id"],
        "target_revision": preview["target_revision"],
        "preview_hash": preview["preview_hash"],
    }


def test_health_and_capabilities(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    caps = client.get("/api/v1/capabilities/").json()
    assert caps["sources"]["replay"] is True
    assert caps["files"]["notebook_export"] is False


def test_session_required(client: TestClient) -> None:
    response = client.get("/api/v1/notebook/")
    assert response.status_code == 401
    assert response.json()["error"] == "SESSION_REQUIRED"


def test_history_compare_replay(client: TestClient) -> None:
    _create_session(client)
    response = _run_analysis(
        client,
        json={
            "spec": {
                "operation": "history_compare",
                "source_ids": ["jeju_579"],
                "station_selections": [{"source_id": "jeju_579", "station_name": "선흘"}],
                "years": [2023, 2024],
                "month_day_start": "04-01",
                "month_day_end": "05-31",
                "elements": ["daily_rainfall"],
                "comparison_scope": "common_valid_month_days",
                "aggregation": "count_positive_days",
                "unit": "day",
                "timezone": "Asia/Seoul",
            },
            "safe_text": "선흘 2023년과 2024년 4월에서 5월 강수 양수일 비교",
        },
    )
    assert response.status_code == 200
    job = response.json()
    result = job["result"]
    assert result["source_mode"] == "replay"
    rain = result["result"]["daily_rainfall"]
    assert rain["common_day_count"] == 51
    assert rain["per_year"]["2023"]["positive_days"] == 21
    assert rain["per_year"]["2024"]["positive_days"] == 20
    assert result["evidence_ids"]
    evidence = client.get(f"/api/v1/evidence/{result['evidence_ids'][0]}")
    assert evidence.status_code == 200


def test_notebook_approval_flow_and_idempotency(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    assert preview["action_status"] == "preview"
    # 승인 전에는 기록이 없어야 한다
    assert client.get("/api/v1/notebook/").json()["entries"] == []
    consent = _consent(client, preview)
    body = _commit_body(preview, consent)
    first = client.post("/api/v1/notebook/commit", json=body)
    assert first.status_code == 200
    assert first.json()["state"] == "committed"
    record_id = first.json()["result_id"]
    entries = client.get("/api/v1/notebook/").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["activity_text"] == "합성 시연용 기록입니다."
    # 같은 승인 재요청 → 기존 결과 반환, 변경 0건
    second = client.post("/api/v1/notebook/commit", json=body)
    assert second.status_code == 200
    assert second.json()["action_id"] == first.json()["action_id"]
    assert len(client.get("/api/v1/notebook/").json()["entries"]) == 1
    # action 결과 조회
    action = client.get(f"/api/v1/actions/{first.json()['action_id']}")
    assert action.status_code == 200
    assert action.json()["state"] == "committed"
    assert record_id


def test_consent_hash_mismatch_rejected(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    response = client.post(
        "/api/v1/consents/",
        json={
            "preview_id": preview["preview_id"],
            "preview_hash": "0" * 64,
            "decision": "confirm",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == "PREVIEW_MISMATCH"


def test_commit_rejects_new_payload(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    consent = _consent(client, preview)
    body = _commit_body(preview, consent)
    body["payload"] = {"activity_text": "몰래 바꾸는 내용"}
    response = client.post("/api/v1/notebook/commit", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "UNKNOWN_FIELD"


def test_revision_conflict(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    consent = _consent(client, preview)
    committed = client.post("/api/v1/notebook/commit", json=_commit_body(preview, consent)).json()
    record_id = committed["result_id"]
    # 두 개의 수정 초안
    p1 = client.post(
        "/api/v1/notebook/prepare",
        json={"action": "update", "record_id": record_id, "payload": {"activity_text": "첫 수정"}},
    ).json()
    p2 = client.post(
        "/api/v1/notebook/prepare",
        json={
            "action": "update",
            "record_id": record_id,
            "payload": {"activity_text": "둘째 수정"},
        },
    ).json()
    c1 = _consent(client, p1)
    r1 = client.post("/api/v1/notebook/commit", json=_commit_body(p1, c1))
    assert r1.status_code == 200
    c2 = _consent(client, p2)
    r2 = client.post("/api/v1/notebook/commit", json=_commit_body(p2, c2))
    assert r2.status_code == 409
    assert r2.json()["error"] == "REVISION_CONFLICT"


def test_session_isolation(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    consent = _consent(client, preview)
    committed = client.post("/api/v1/notebook/commit", json=_commit_body(preview, consent)).json()
    record_id = committed["result_id"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as other:
        _create_session(other)
        assert other.get(f"/api/v1/notebook/{record_id}").status_code == 404
        assert other.get("/api/v1/notebook/").json()["entries"] == []


def test_session_end_wipes_data(client: TestClient) -> None:
    _create_session(client)
    preview = _notebook_preview(client)
    consent = _consent(client, preview)
    client.post("/api/v1/notebook/commit", json=_commit_body(preview, consent))
    end = client.delete("/api/v1/sessions/current")
    assert end.status_code == 200
    assert client.get("/api/v1/notebook/").status_code == 401


def test_session_resume_preserves_personal_records(client: TestClient) -> None:
    first_session = _create_session(client)
    preview = _notebook_preview(client)
    consent = _consent(client, preview)
    client.post("/api/v1/notebook/commit", json=_commit_body(preview, consent))
    # 사용자가 다시 돌아와 /api/v1/sessions/ 를 재호출해도 서버에 저장된 기록이 유지되어야 한다
    resumed = _create_session(client)
    assert resumed["session_id"] == first_session["session_id"]
    entries = client.get("/api/v1/notebook/").json()["entries"]
    assert len(entries) == 1
    assert entries[0]["activity_text"] == "합성 시연용 기록입니다."


def test_share_prepare_and_commit(client: TestClient) -> None:
    _create_session(client)
    response = client.post(
        "/api/v1/share/prepare",
        json={
            "items": [
                {"recipient_alias": "어머니", "amount_value": 1, "amount_unit": "봉지"},
                {
                    "recipient_alias": "이웃",
                    "amount_value": 2,
                    "amount_unit": "봉지",
                    "planned_delivery": "이번 주말",
                },
            ],
            "message_enabled": True,
        },
    )
    assert response.status_code == 200
    preview = response.json()
    assert preview["display"]["editable_message"]
    assert "어머니" in preview["display"]["editable_message"]
    consent = _consent(client, preview)
    committed = client.post("/api/v1/share/commit", json=_commit_body(preview, consent))
    assert committed.status_code == 200
    drafts = client.get("/api/v1/share/").json()["drafts"]
    assert len(drafts) == 1
    assert len(drafts[0]["items"]) == 2


def test_region_register_flow(client: TestClient) -> None:
    _create_session(client)
    response = client.post(
        "/api/v1/regions/prepare",
        json={
            "action": "create",
            "payload": {
                "kind": "interest",
                "local_alias": "새 관심 지역",
                "public_area_code": "제주특별자치도 제주시 조천읍",
            },
        },
    )
    preview = response.json()
    consent = _consent(client, preview)
    committed = client.post("/api/v1/regions/commit", json=_commit_body(preview, consent))
    assert committed.status_code == 200
    regions = client.get("/api/v1/regions/").json()["regions"]
    assert len(regions) == 1
    assert regions[0]["local_alias"] == "새 관심 지역"


def test_retail_lookup_cards(client: TestClient) -> None:
    _create_session(client)
    response = _run_analysis(
        client,
        json={
            "spec": {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample"],
                "price_channel": "retail",
            }
        },
    )
    result = response.json()["result"]
    cards = result["result"]["sample_cards"]
    card_200g = next(c for c in cards if c["net_weight_value"] == 200 and c["price_value"] == 32500)
    assert card_200g["price_per_kg_value"] == 162500
    assert "conversion_formula" in card_200g
    assert result["link_status"] == "link_ready"


def test_survey_link_with_sample_cards(client: TestClient) -> None:
    _create_session(client)
    response = _run_analysis(
        client,
        json={
            "spec": {
                "operation": "survey_link",
                "source_ids": ["forestinfo"],
                "price_channel": "survey",
            }
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["data_status"] == "unavailable"
    assert result["source_mode"] == "link"
    assert result["link_status"] == "link_ready"
    sample_cards = result["result"]["sample_cards"]
    prices = {c["price_value"] for c in sample_cards}
    assert {11500, 15000, 18500}.issubset(prices)
    assert result["result"]["links"]


def test_region_compare_replay(client: TestClient) -> None:
    _create_session(client)
    response = _run_analysis(
        client,
        json={
            "spec": {
                "operation": "region_compare",
                "source_ids": ["jeju_579", "kma_asos"],
                "station_selections": [
                    {"source_id": "jeju_579", "station_name": "선흘"},
                    {"source_id": "kma_asos", "station_id": "184", "station_name": "제주"},
                ],
                "years": [2024],
                "month_day_start": "04-01",
                "month_day_end": "05-31",
                "elements": ["daily_rainfall", "average_temperature"],
            }
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    per_station = result["result"]["per_station"]
    assert "선흘" in per_station
    assert "제주(184)" in per_station
    assert "full_period" in per_station["선흘"]
    assert "value_states" in per_station["선흘"]


def test_outing_compare_and_partial_failure(client: TestClient) -> None:
    _create_session(client)
    response = _run_analysis(
        client,
        json={
            "spec": {
                "operation": "outing_compare",
                "source_ids": ["kma_aws", "jeju_579", "kma_asos"],
                "candidates": [
                    {
                        "label": "토요일 오전 (선흘)",
                        "date": "2026-04-18",
                        "time_slot": "오전",
                        "station_name": "선흘",
                    },
                    {
                        "label": "일요일 오전 (미등록지점)",
                        "date": "2026-04-19",
                        "time_slot": "오전",
                        "station_name": "존재하지않는관측소",
                    },
                ],
                "preferred_elements": ["daily_rainfall", "average_temperature", "wind_speed"],
            }
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["data_status"] == "partial"
    assert len(result["result"]["candidates"]) == 1
    assert len(result["result"]["failed_candidates"]) == 1
    assert result["result"]["preparation_checklist"]


def test_out_of_scope_guardrail(client: TestClient) -> None:
    _create_session(client)
    response = client.post(
        "/api/v1/analysis/prepare",
        json={"text": "여기서 고사리 채취해도 되나요? 불법인가요?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feature"] == "out_of_scope"
    assert body["needs_confirmation"] is True


def test_disabled_file_capabilities(client: TestClient) -> None:
    _create_session(client)
    response = client.post("/api/v1/notebook/export/prepare")
    assert response.status_code == 503
    assert response.json()["error"] == "CAPABILITY_DISABLED"


def test_session_resume_and_pg18_persistence(client: TestClient, monkeypatch) -> None:
    created = client.post("/api/v1/sessions/").json()
    sid = created["session_id"]

    preview = client.post(
        "/api/v1/notebook/prepare",
        json={
            "action": "create",
            "payload": {
                "experience_date": "2026-04-20",
                "activity_text": "PostgreSQL 18 영속 보관 테스트 기록",
                "companion_aliases": ["어머니"],
                "amount_value": "2",
                "amount_unit": "봉지",
            },
        },
    ).json()
    consent = _consent(client, preview)
    committed = client.post("/api/v1/notebook/commit", json=_commit_body(preview, consent))
    assert committed.status_code == 200

    # 재방문 시 POST /api/v1/sessions/ 호출해도 기존 세션 복원
    resumed = client.post("/api/v1/sessions/", headers={"X-Gosari-Session": sid}).json()
    assert resumed["session_id"] == sid
    assert resumed["notice"] == ""

    recalled = client.post("/api/v1/notebook/recall", json={}).json()
    assert recalled["count"] == 1
    assert recalled["entries"][0]["activity_text"] == "PostgreSQL 18 영속 보관 테스트 기록"

    # PostgreSQL 18 save / _load_from_db SQL 실행 경로 검증
    from contextlib import contextmanager

    from gosari.sessions import get_session_store

    store = get_session_store()
    session_obj = store.get(sid)
    executed_sql: list[str] = []

    class FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    class FakeConn:
        def execute(self, sql: str, params=None):
            executed_sql.append(sql.strip())
            if "FROM app_session" in sql:
                return FakeCursor(
                    [
                        (
                            session_obj.session_id,
                            session_obj.created_at,
                            session_obj.expires_at,
                            session_obj.last_activity_at,
                            "active",
                        )
                    ]
                )
            if "FROM personal_notebook_entry" in sql:
                entry = next(iter(session_obj.notebook.values()))
                return FakeCursor(
                    [
                        (
                            entry.record_id,
                            entry.revision,
                            entry.experience_date,
                            entry.companion_aliases,
                            entry.activity_text,
                            str(entry.amount_value),
                            entry.amount_unit,
                            entry.created_at,
                            entry.updated_at,
                        )
                    ]
                )
            return FakeCursor([])

        def commit(self):
            executed_sql.append("COMMIT")

    @contextmanager
    def fake_connection():
        yield FakeConn()

    monkeypatch.setattr("gosari.sessions.db_available", lambda: True)
    monkeypatch.setattr("gosari.sessions.connection", fake_connection)

    store.save(session_obj)
    assert any("INSERT INTO app_session" in s for s in executed_sql)
    assert any("INSERT INTO personal_notebook_entry" in s for s in executed_sql)

    loaded = store._load_from_db(sid)
    assert loaded is not None
    assert len(loaded.notebook) == 1
    assert (
        next(iter(loaded.notebook.values())).activity_text == "PostgreSQL 18 영속 보관 테스트 기록"
    )
