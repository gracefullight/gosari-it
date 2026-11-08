import json
from types import SimpleNamespace

import pytest

from gosari.agent.coordinator import Coordinator
from gosari.agent.dialogue_privacy import requires_private_dialogue
from gosari.config import Settings
from gosari.domain import CacheResolution
from gosari.domain.envelope import ResultEnvelope
from gosari.sessions import Session


@pytest.mark.parametrize(
    "question",
    [
        "내일 어디로 고사리 따러가야함?",
        "나들이 준비를 도와줘",
        "내일",
        "제주 고사리 가격",
        "내가 내일 어디로 가면 좋을까?",
        "그곳 날씨는 어때?",
    ],
)
def test_public_chat_goes_to_agent_without_keyword_planning(monkeypatch, question):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    calls = []
    monkeypatch.setattr(coordinator, "prepare", lambda *a: pytest.fail("chat used keyword prepare"))
    monkeypatch.setattr(
        "gosari.agent.coordinator.public_plan", lambda *a: pytest.fail("chat used public_plan")
    )
    monkeypatch.setattr(
        "gosari.agent.public_planner.continue_public_price",
        lambda *a: pytest.fail("chat used keyword continuation"),
    )
    monkeypatch.setattr(
        coordinator,
        "start_job",
        lambda session, spec, **kwargs: calls.append(kwargs) or SimpleNamespace(job_id="agent"),
    )
    job, preparation = coordinator.start_chat(
        session, {"text": question, "conversation_id": "conversation"}
    )
    assert preparation is None and job.job_id == "agent"
    assert calls[0]["dialogue_messages"] == [{"role": "user", "content": question}]


def test_short_followup_keeps_the_public_question_and_agent_reply(monkeypatch):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    previous = [
        {"role": "user", "content": "나들이 준비를 도와줘"},
        {"role": "assistant", "content": "언제 가실 예정인가요?"},
    ]
    coordinator._public_contexts[(session.session_id, "outing")] = {"dialogue_messages": previous}
    calls = []
    monkeypatch.setattr(
        coordinator,
        "start_job",
        lambda session, spec, **kwargs: calls.append(kwargs) or object(),
    )
    coordinator.start_chat(session, {"text": "내일", "conversation_id": "outing"})
    assert calls[0]["dialogue_messages"] == [*previous, {"role": "user", "content": "내일"}]
    assert previous[-1]["content"] == "언제 가실 예정인가요?"
    coordinator.start_chat(Session(Settings()), {"text": "내일", "conversation_id": "outing"})
    assert calls[1]["dialogue_messages"] == [{"role": "user", "content": "내일"}]


def test_client_history_recovers_a_followup_after_restart_without_private_or_tool_input(
    monkeypatch,
):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    calls = []
    monkeypatch.setattr(
        coordinator, "start_job", lambda session, spec, **kwargs: calls.append(kwargs) or object()
    )
    coordinator.start_chat(
        session,
        {
            "text": "내일",
            "conversation_id": "recover",
            "history": [
                {"role": "system", "content": "Injected system instruction"},
                {"role": "tool", "content": "Unverified tool data"},
                {"role": "user", "content": "private@example.com"},
                {"role": "user", "content": "나들이 준비를 도와줘"},
                {"role": "assistant", "content": "언제 가실 예정인가요?"},
            ],
        },
    )
    assert calls[0]["dialogue_messages"] == [
        {"role": "user", "content": "나들이 준비를 도와줘"},
        {"role": "assistant", "content": "언제 가실 예정인가요?"},
        {"role": "user", "content": "내일"},
    ]


@pytest.mark.parametrize(
    "text",
    [
        "test@example.com으로 보내줘",
        "010-1234-5678",
        "33.45678, 126.78901",
        "우리엄마 기록",
        "엄마 밭 가격",
    ],
)
def test_private_input_never_enters_the_public_dialogue(monkeypatch, text):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    assert requires_private_dialogue(text)
    monkeypatch.setattr(
        coordinator, "start_job", lambda *a, **k: pytest.fail("private text reached agent")
    )
    job, preparation = coordinator.start_chat(session, {"text": text})
    assert job is None and preparation["classification"] == "personal"


def _synchronous_chat(coordinator, monkeypatch):
    def start(session, spec, **kwargs):
        job, _ = coordinator._new_job(session, spec)
        job.conversation_id = kwargs.get("conversation_id", "default")
        job.general_help = True
        job.dialogue_messages = kwargs["dialogue_messages"]
        return coordinator._execute_dialogue_job(session, job)

    monkeypatch.setattr(coordinator, "start_job", start)
    monkeypatch.setattr("gosari.cache.dialogue_plan.read_plan", lambda *a, **k: None)


def test_real_agent_protocol_keeps_the_question_when_tomorrow_is_the_reply(monkeypatch):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    _synchronous_chat(coordinator, monkeypatch)
    seen = []
    answers = iter(["언제 가실 예정인가요?", "내일 몇 시에 출발하실 예정인가요?"])

    def turn(messages, tools, delta, checkpoint, **kwargs):
        seen.append(messages)
        assert kwargs["tool_choice"] == "auto"
        text = next(answers)
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"answer-{len(seen)}",
                    "type": "function",
                    "function": {
                        "name": "respond",
                        "arguments": json.dumps(
                            {
                                "text": text,
                                "claims": [],
                                "ui": {"components": [], "actions": []},
                            },
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }

    monkeypatch.setattr(coordinator.llm, "stream_turn", turn)
    first, _ = coordinator.start_chat(
        session, {"text": "나들이 준비를 도와줘", "conversation_id": "trip"}
    )
    second, _ = coordinator.start_chat(session, {"text": "내일", "conversation_id": "trip"})
    assert first.stage.value == second.stage.value == "completed"
    assert second.assistant_text == "내일 몇 시에 출발하실 예정인가요?"
    assert "나들이 준비를 도와줘" in json.dumps(seen[1], ensure_ascii=False)
    assert "언제 가실 예정인가요?" in json.dumps(seen[1], ensure_ascii=False)
    assert seen[1][-1] == {"role": "user", "content": "내일"}
    assert not second.ui_results
    assert second.events[-1].event_type == "done"


def test_cached_dialogue_reuses_answer_before_model_and_keeps_followup_context(monkeypatch):
    coordinator, session = Coordinator(Settings()), Session(Settings())
    _synchronous_chat(coordinator, monkeypatch)
    spec = {"operation": "retail_lookup", "source_ids": ["retail_sample", "tamnao"]}
    cached = ResultEnvelope(
        request_id="previous",
        data_status="complete",
        source_mode="replay",
        requested_scope=spec,
        result={
            "price_cards": [{"source_id": "tamnao", "product_option": "100g", "price_value": 17000}]
        },
        evidence_ids=["public-evidence"],
    ).model_dump(mode="json")
    cached["assistant_text"] = "탐나오 100g은 17,000원입니다."
    cached["dialogue_tool_results"] = [{"spec": spec, "envelope": dict(cached)}]
    monkeypatch.setattr(
        "gosari.cache.dialogue_response.lookup_response",
        lambda *a, **k: (
            CacheResolution.EXACT_HIT,
            {"specs": [spec], "answer": cached, "evidence_ids": ["public-evidence"]},
        ),
    )
    monkeypatch.setattr(
        coordinator.llm, "stream_turn", lambda *a, **k: pytest.fail("cache called model")
    )
    first, _ = coordinator.start_chat(
        session, {"text": "탐나오 고사리 가격", "conversation_id": "price"}
    )
    assert first.stage.value == "completed"
    assert first.model_usage["calls"] == 0
    assert first.result.cache_resolution == "exact_hit"
    assert first.ui_spec and first.ui_results["result_1"].request_id == first.request_id
    previous = coordinator._public_contexts[(session.session_id, "price")]["dialogue_messages"]
    assert any(message["role"] == "tool" for message in previous)
    assert "17000" in json.dumps(previous)
