
import pytest
from litestar.testing import TestClient

from gosari.agent.coordinator import Coordinator
from gosari.app import create_app
from gosari.config import Settings
from gosari.personal import contacts, notebook, regions, share
from gosari.personal.search import is_personal_search, search_personal
from gosari.sessions import Session, SessionStore


@pytest.fixture
def session():
    settings = Settings()
    value = Session(settings)
    regions.execute(
        value,
        regions.prepare_create(
            value,
            {
                "kind": "existing",
                "local_alias": "선흘 스팟",
                "public_area_code": "조천읍 선흘리",
                "visited_on": "2026-04-12",
            },
        ),
    )
    notebook.execute(
        value,
        notebook.prepare_create(
            value,
            {
                "experience_date": "2026-04-12",
                "activity_text": "비 온 뒤 어머니와 고사리 채취",
                "companion_aliases": ["어머니"],
            },
            2000,
        ),
    )
    cid, _ = contacts.execute(
        value,
        contacts.prepare_create(
            value, {"name": "어머니", "relationship": "가족", "notes": "생고사리 좋아함"}
        ),
    )
    share.execute(
        value,
        share.prepare(
            value,
            {
                "items": [
                    {
                        "contact_id": cid,
                        "amount_value": 2,
                        "amount_unit": "봉지",
                        "status": "delivered",
                        "occurred_on": "2026-04-13",
                    }
                ]
            },
        )[0],
    )
    return value


def test_keyword_search_covers_private_domains_dates_and_status(session, monkeypatch):
    monkeypatch.setattr(
        "gosari.personal.search.local_ranker.similarities", lambda query, docs: None
    )
    assert search_personal(session, "선흘 스팟 찾아줘").items[0].kind == "region"
    assert search_personal(session, "선흘 스팟 찾아줘").items[0].date == "2026-04-12"
    assert search_personal(session, "어머니 수첩 찾아줘").items[0].kind == "notebook"
    assert search_personal(session, "가족 지인 찾아줘").items[0].kind == "contact"
    result = search_personal(session, "전달 완료 나눔 이력")
    assert result.mode == "keyword"
    assert result.items[0].kind == "share"
    assert result.items[0].date == "2026-04-13"
    assert "2봉지" in result.items[0].snippet
    assert len(search_personal(session, "내 관심지역 알려줘").items) == 1


def test_search_never_reads_another_session(session, monkeypatch):
    monkeypatch.setattr(
        "gosari.personal.search.local_ranker.similarities", lambda query, docs: None
    )
    assert search_personal(Session(Settings()), "선흘").items == []
    assert search_personal(session, "없는고유명사").items == []


def test_hybrid_combines_keyword_and_local_semantic_rank(session, monkeypatch):
    monkeypatch.setattr(
        "gosari.personal.search.local_ranker.similarities", lambda query, docs: [0.9] * len(docs)
    )
    result = search_personal(session, "우리 가족에게 나눠준 기록")
    assert result.mode == "hybrid"
    assert result.items[0].kind == "share"


@pytest.mark.parametrize(
    "query",
    [
        "내 등록스팟 찾아줘",
        "내 관심지역 알려줘",
        "우리 어머니께 드린거 언제",
        "내 수첩 회고",
        "지인 목록 보여줘",
        "내 명당 찾아줘",
    ],
)
def test_retrieval_intents_are_local_and_skip_llm(query, monkeypatch):
    coordinator = Coordinator(Settings())
    monkeypatch.setattr(
        coordinator.llm,
        "structure_question",
        lambda text: pytest.fail("private retrieval reached external model"),
    )
    result = coordinator.prepare(Session(Settings()), {"text": query})
    assert result["classification"] == "personal"
    assert result["feature"] == "personal_search"
    assert result["form"]["query"] == query


@pytest.mark.parametrize(
    "query", ["내일 날씨 알려줘", "수첩 기록해", "내 지역 새로 등록해", "내 수첩 수정 방법 알려줘"]
)
def test_public_weather_and_write_intents_keep_existing_route(query):
    assert not is_personal_search(query)


def test_private_search_http_is_session_scoped_and_no_store(session, monkeypatch):
    store = SessionStore(Settings())
    store._sessions[session.session_id] = session
    monkeypatch.setattr("gosari.app.open_pool", lambda settings: None)
    monkeypatch.setattr("gosari.sessions._store", store)
    monkeypatch.setattr("gosari.sessions.db_available", lambda: False)
    monkeypatch.setattr(
        "gosari.personal.search.local_ranker.similarities", lambda query, docs: None
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/v1/personal/search", json={"query": "선흘"}).status_code == 401
        response = client.post(
            "/api/v1/personal/search",
            headers={"X-Gosari-Session": session.session_id},
            json={"query": "선흘", "limit": 1},
        )
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["title"] == "선흘 스팟"
        assert session.notebook
