import json
from contextlib import nullcontext

import pytest

from gosari.agent.coordinator import Coordinator
from gosari.api.analysis import _job_response
from gosari.config import Settings
from gosari.personal import regions
from gosari.personal.search import search_personal
from gosari.sessions import Session


@pytest.fixture
def local_agent(monkeypatch):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    monkeypatch.setattr("gosari.cache.dialogue_plan.read_plan", lambda *a, **k: None)
    monkeypatch.setattr(
        "gosari.cache.semantic.response_cache_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr(
        "gosari.agent.coordinator.store",
        lambda *a, **k: pytest.fail("private turn reached shared cache"),
    )
    monkeypatch.setattr(
        "gosari.cache.dialogue_plan.store_plan",
        lambda *a, **k: pytest.fail("private turn reached plan cache"),
    )
    monkeypatch.setattr(
        "gosari.personal.search.local_ranker.similarities",
        lambda *a: pytest.fail("listing initialized embedding model"),
    )
    for alias in ("PRIVATE_CANARY_FIRST", "PRIVATE_CANARY_SECOND"):
        regions.execute(
            session,
            regions.prepare_create(
                session,
                {"kind": "interest", "local_alias": alias, "public_area_code": "조천읍"},
            ),
        )

    def start(owner, spec, **kwargs):
        job, _ = coordinator._new_job(owner, spec)
        job.dialogue_messages = kwargs["dialogue_messages"]
        job.conversation_id = kwargs.get("conversation_id", "default")
        return coordinator._execute_dialogue_job(owner, job)

    monkeypatch.setattr(coordinator, "start_job", start)
    return coordinator, session


def test_saved_spot_question_uses_agent_and_local_records_without_a_registration_form(
    local_agent, monkeypatch
):
    coordinator, session = local_agent
    monkeypatch.setattr(
        coordinator, "prepare", lambda *a: pytest.fail("lookup opened keyword form")
    )

    def dialogue(client, incoming, execute, emit, checkpoint, **kwargs):
        assert incoming[-1]["content"] == "내가 어느 지역을 추가해놨지 고사리 스팟"
        result = execute({"operation": "search_personal_records", "kind": "region", "query": ""})
        assert result.result == {"count": 2, "kinds": ["region"], "ui_query": ""}
        assert "PRIVATE_CANARY" not in result.model_dump_json()
        return None, "저장한 지역 2건을 찾았어요.", incoming, []

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", dialogue)
    job, preparation = coordinator.start_chat(
        session, {"text": "내가 어느 지역을 추가해놨지 고사리 스팟"}
    )
    assert preparation is None and job.stage.value == "completed"
    assert job.personal_form is None
    expected = {"query": "", "kind": "region", "count": 2}
    assert job.to_dict()["personal_search"] == expected
    assert _job_response(job).model_dump()["personal_search"] == expected
    assert job.events[-1].payload["personal_search"] == expected
    assert "PRIVATE_CANARY" not in json.dumps(job.to_dict(), ensure_ascii=False)
    assert search_personal(Session(Settings()), "", kind="region").items == []


@pytest.mark.parametrize("feature", ["notebook", "region_compare", "share"])
def test_model_selected_write_opens_existing_form_without_committing(
    local_agent, monkeypatch, feature
):
    coordinator, session = local_agent

    def dialogue(client, incoming, execute, emit, checkpoint, **kwargs):
        output = execute({"operation": "open_personal_form", "feature": feature})
        assert output.result == {"feature": feature}
        return None, "내용을 입력해 주세요.", incoming, []

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", dialogue)
    job, _ = coordinator.start_chat(session, {"text": "새 관심 지역을 등록하고 싶어"})
    assert job.stage.value == "completed" and job.private_tools_used
    assert job.personal_form == feature
    assert job.events[-1].payload["personal_form"] == feature
    assert len(session.regions) == 2 and not session.notebook and not session.share_drafts


def test_public_street_view_uses_resolved_coordinates_and_excludes_mixed_answer_cache(
    local_agent, monkeypatch
):
    coordinator, session = local_agent

    def dialogue(client, incoming, execute, emit, checkpoint, **kwargs):
        result = execute({"operation": "open_street_view", "location_id": "한라산남벽"})
        links = result.result["street_view_links"]
        assert result.requested_scope["location_id"] == "aws:965"
        assert links[0]["location_name"] == "한라산남벽"
        assert "viewpoint=33.3524%2C126.533" in links[0]["url"]
        emit(
            "tool_completed",
            {
                "tool_call_id": "public-link",
                "name": "open_street_view",
                "summary": "거리뷰",
                "result": result.model_dump(mode="json"),
            },
        )
        # A public read in the same turn does not make a link-bearing response
        # reusable under the read's narrower condition fingerprint.
        return (
            result,
            "한라산남벽 거리뷰를 열 수 있어요.",
            incoming,
            [{"operation": "retail_lookup", "source_ids": ["retail_sample"]}],
        )

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", dialogue)
    job, preparation = coordinator.start_chat(session, {"text": "한라산남벽 거리뷰를 열어줘"})
    assert preparation is None and job.stage.value == "completed"
    assert job.link_tools_used and not job.private_tools_used
    assert job.result.result["street_view_links"][0]["provider"] == "google"
    assert job.events[-1].payload["result"]["requested_scope"]["location_id"] == "aws:965"
