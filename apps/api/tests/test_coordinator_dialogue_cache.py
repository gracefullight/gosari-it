"""Chat cache hits skip the model and retain the public conversation and all UI results."""

import copy
import json
import sys
from contextlib import nullcontext, suppress
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from gosari.agent import build_public_spec
from gosari.agent.coordinator import Coordinator, Job
from gosari.config import Settings
from gosari.domain import CacheResolution, JobStage
from gosari.domain.envelope import ResultEnvelope, UiElement, UiSpec
from gosari.domain.errors import GosariError
from gosari.sessions import Session


def source(weight):
    return ResultEnvelope(
        request_id="previous-request",
        data_status="complete",
        source_mode="fetched",
        evidence_ids=[f"public-{weight}"],
        result={"price_cards": [{"product_option": weight, "price_value": 17000}]},
    )


def spec(weight):
    return {
        "operation": "retail_lookup",
        "source_ids": ["retail_sample"],
        "package_weight_unit": weight,
    }


def payload():
    specs = [spec("100g"), spec("200g")]
    first, second = source("100g"), source("200g")
    ui = UiSpec(
        root="root",
        elements={
            "root": UiElement(type="ResultLayout", children=["one", "two"]),
            "one": UiElement(type="PriceResults", props={"resultRef": "result_1"}),
            "two": UiElement(type="PriceResults", props={"resultRef": "result_2"}),
        },
    )
    results = {
        "result_1": first.model_copy(update={"requested_scope": build_public_spec(specs[0])}),
        "result_2": second.model_copy(update={"requested_scope": build_public_spec(specs[1])}),
    }
    continuation = []
    for index, public in enumerate(specs, 1):
        continuation.extend(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"original-{index}",
                            "type": "function",
                            "function": {
                                "name": "retail_lookup",
                                "arguments": json.dumps(
                                    {"package_weight_unit": public["package_weight_unit"]}
                                ),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": f"original-{index}",
                    "content": json.dumps(
                        {
                            "operation": "retail_lookup",
                            "conditions": public,
                            "facts": {
                                f"f{index}": {
                                    "value": 17000,
                                    "label": f"{public['package_weight_unit']} 가격",
                                    "unit": "원",
                                    "as_of": "2026-11-08",
                                }
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ]
        )
    continuation.append({"role": "assistant", "content": "두 규격의 가격을 확인했어요."})
    answer = {
        **second.model_dump(mode="json"),
        "assistant_text": "두 규격의 가격을 확인했어요.",
        "ui_spec": ui.model_dump(mode="json") if ui else None,
        "ui_results": {key: value.model_dump(mode="json") for key, value in results.items()},
        "dialogue_tool_results": [
            {"spec": value, "envelope": output.model_dump(mode="json")}
            for value, output in zip(specs, [first, second], strict=True)
        ],
        "dialogue_continuation": continuation,
    }
    return {"specs": specs, "answer": answer, "evidence_ids": ["public-100g", "public-200g"]}


@pytest.fixture
def scenario(monkeypatch):
    settings = Settings(external_requests_enabled=False, response_cache_enabled=True)
    coordinator = Coordinator(settings)
    session = Session(settings)
    job = Job("cache-job", "current-request")
    job.conversation_id = "conversation"
    job.dialogue_messages = [{"role": "user", "content": "고사리 가격을 알려줘"}]
    job.general_help = True
    state = {"hit": None, "lookups": [], "stores": [], "enrichments": [], "model_turns": 0}

    def lookup(question, history, *, now):
        state["lookups"].append((question, copy.deepcopy(history)))
        return CacheResolution.EXACT_HIT if state["hit"] else CacheResolution.MISS, state["hit"]

    def store(question, history, specs, answer, evidence_ids, *, now, valid_until):
        state["stores"].append(copy.deepcopy((question, history, specs, answer, evidence_ids)))
        return True

    cache = SimpleNamespace(
        lookup_response=lookup,
        store_response=store,
        context_hash=lambda history: json.dumps(history, ensure_ascii=False, sort_keys=True),
        lifespan=lambda specs, now: now + timedelta(minutes=5),
        enrich_response_embedding=lambda *args, **kwargs: state["enrichments"].append(args),
    )
    monkeypatch.setitem(sys.modules, "gosari.cache.dialogue_response", cache)
    monkeypatch.setattr(
        "gosari.cache.semantic.response_cache_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr(
        "gosari.cache.public_source.public_source_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda *a: None)
    monkeypatch.setattr("gosari.cache.public_source.put_source_result", lambda *a, **k: True)

    def model(*args, **kwargs):
        state["model_turns"] += 1
        raise AssertionError("A cached complete response must not call the model")

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", model)
    monkeypatch.setattr(coordinator.llm, "begin_job", lambda: None)
    monkeypatch.setattr(coordinator.llm, "usage_snapshot", lambda: {"calls": state["model_turns"]})
    yield coordinator, session, job, state, cache
    coordinator._executor.shutdown(wait=True, cancel_futures=True)
    indexer = getattr(coordinator, "_cache_executor", None)
    if indexer is not None:
        indexer.shutdown(wait=True, cancel_futures=True)


def test_first_public_hit_skips_model_and_restores_all_tool_results(scenario):
    from gosari.cache.dialogue_guards import context_hash

    coordinator, session, job, state, _ = scenario
    state["hit"] = payload()
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.COMPLETED
    assert job.model_usage["calls"] == 0
    assert job.assistant_text == state["hit"]["answer"]["assistant_text"]
    assert len(state["lookups"]) == 1
    assert len(job.ui_results) == 2
    assert all(result.request_id == job.request_id for result in job.ui_results.values())
    history = coordinator._public_contexts[(session.session_id, job.conversation_id)][
        "dialogue_messages"
    ]
    tools = [json.loads(message["content"]) for message in history if message["role"] == "tool"]
    assert len(tools) == 2
    assert [item["conditions"]["package_weight_unit"] for item in tools] == ["100g", "200g"]
    assert job.result.cache_resolution == CacheResolution.EXACT_HIT
    original = [*job.dialogue_messages, *state["hit"]["answer"]["dialogue_continuation"]]
    assert context_hash(history) == context_hash(original) is not None
    assert history[1]["tool_calls"][0]["id"] != "original-1"
    assert tools[1]["facts"]["f2"]["label"] == "200g 가격"


def test_public_follow_up_uses_its_prior_context_before_the_model(scenario):
    coordinator, session, job, state, _ = scenario
    history = [
        {"role": "user", "content": "탐나오 100g 가격이 궁금해"},
        {"role": "assistant", "content": "어느 날짜의 표시가를 볼까요?"},
    ]
    job.dialogue_messages = [*history, {"role": "user", "content": "오늘 기준으로 알려줘"}]
    state["hit"] = payload()
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.COMPLETED
    assert state["lookups"] == [("오늘 기준으로 알려줘", history)]
    assert job.model_usage["calls"] == 0


def test_cancelled_cache_lookup_does_not_publish_cached_ui_or_answer(scenario):
    coordinator, session, job, _state, cache = scenario

    def cancel(*args, **kwargs):
        job.cancelled = True
        return CacheResolution.EXACT_HIT, payload()

    cache.lookup_response = cancel
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.CANCELLED
    assert not job.assistant_text and job.ui_spec is None
    assert not any(event.event_type in ("ui_spec", "assistant_completed") for event in job.events)


def test_complete_multiple_tool_reply_is_stored_as_one_bundle(scenario, monkeypatch):
    coordinator, session, job, state, _ = scenario

    def model(_client, incoming, execute, emit, checkpoint, **kwargs):
        state["model_turns"] += 1
        execute(spec("100g"))
        second = execute(spec("200g"))
        p = payload()
        emit("ui_spec", {"spec": p["answer"]["ui_spec"], "results": p["answer"]["ui_results"]})
        answer = p["answer"]["assistant_text"]
        return (
            second,
            answer,
            [*incoming, *p["answer"]["dialogue_continuation"]],
            [spec("100g"), spec("200g")],
        )

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", model)
    monkeypatch.setattr(
        "gosari.agent.coordinator.AnalysisEngine.run",
        lambda self, public, request: source(public["package_weight_unit"]),
    )
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.COMPLETED
    assert len(state["stores"]) == 1
    question, history, specs, answer, evidence = state["stores"][0]
    assert question == "고사리 가격을 알려줘"
    assert history == [] and len(specs) == 2
    assert len(answer["dialogue_tool_results"]) == 2
    assert [
        record["envelope"]["requested_scope"]["package_weight_unit"]
        for record in answer["dialogue_tool_results"]
    ] == ["100g", "200g"]
    assert all(
        record["envelope"]["requested_scope"]["operation"] == "retail_lookup"
        for record in answer["dialogue_tool_results"]
    )
    assert answer["dialogue_continuation"] == payload()["answer"]["dialogue_continuation"]
    assert all(message["role"] != "user" for message in answer["dialogue_continuation"])
    assert set(evidence) == {"public-100g", "public-200g"}


def test_a_failed_scope_is_not_hidden_by_a_later_complete_tool(scenario, monkeypatch):
    coordinator, session, job, state, _ = scenario

    def execute(self, public, request):
        if public["package_weight_unit"] == "100g":
            raise GosariError("SOURCE_UNAVAILABLE")
        return source("200g")

    def model(_client, incoming, perform, emit, checkpoint, **kwargs):
        with suppress(GosariError):
            perform(spec("100g"))
        final = perform(spec("200g"))
        return final, "200g 자료를 확인했어요.", incoming, [spec("200g")]

    monkeypatch.setattr("gosari.agent.coordinator.AnalysisEngine.run", execute)
    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", model)
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.COMPLETED
    assert not state["stores"]


def test_shared_flight_uses_the_same_whitespace_normalization_as_exact_keys(scenario, monkeypatch):
    coordinator, session, job, state, _ = scenario
    state["hit"] = payload()
    flights = []

    def flight(spec, question, **kwargs):
        flights.append(question)
        return nullcontext()

    monkeypatch.setattr("gosari.cache.semantic.response_cache_singleflight", flight)
    job.dialogue_messages = [{"role": "user", "content": "고사리  가격을 알려줘"}]
    coordinator._execute_dialogue_job(session, job)
    second = Job("second", "second-request")
    second.dialogue_messages = [{"role": "user", "content": "고사리 가격을 알려줘"}]
    coordinator._execute_dialogue_job(session, second)
    assert job.stage == second.stage == JobStage.COMPLETED
    assert len(flights) == 2 and flights[0] == flights[1]


def test_an_answer_crossing_korean_midnight_is_not_stored_under_a_new_day(scenario, monkeypatch):
    coordinator, session, job, state, _ = scenario
    clock = [datetime(2026, 11, 8, 14, 59, 59, tzinfo=UTC)]
    monkeypatch.setattr("gosari.agent.coordinator.utcnow", lambda: clock[0])

    def model(_client, incoming, execute, emit, checkpoint, **kwargs):
        result = execute(spec("100g"))
        clock[0] += timedelta(seconds=2)
        return result, "조회한 가격입니다.", incoming, [spec("100g")]

    monkeypatch.setattr("gosari.agent.dialogue.run_dialogue", model)
    monkeypatch.setattr("gosari.agent.coordinator.AnalysisEngine.run", lambda *args: source("100g"))
    coordinator._execute_dialogue_job(session, job)
    assert job.stage == JobStage.COMPLETED
    assert state["lookups"] and not state["stores"]
