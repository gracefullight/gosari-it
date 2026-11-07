import json
from secrets import token_hex

import httpx
import pytest

from gosari.agent.coordinator import Coordinator
from gosari.agent.llm import LlmClient
from gosari.agent.public_planner import continue_public_price, public_dialogue_intent
from gosari.agent.runtime import compact_result, run_agent, supported_answer, tools
from gosari.config import Settings
from gosari.domain.envelope import ResultEnvelope
from gosari.sessions import Session


def call(name, args=None, identifier="c1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": identifier,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)},
            }
        ],
    }


def result():
    return ResultEnvelope(
        request_id="r",
        data_status="complete",
        source_mode="replay",
        result={
            "price_cards": [
                {
                    "source_id": "tamnao",
                    "form": "건고사리",
                    "product_option": "100g",
                    "price_value": 7900,
                    "price_as_of": "2026-11-04",
                }
            ]
        },
    )


def test_real_tool_then_model_followup_and_fact_association():
    events, executed, seen = [], [], []
    responses = iter(
        [
            call("retail_lookup"),
            call(
                "respond",
                {
                    "text": "탐나오 100g 표시가는 7,900원입니다.",
                    "claims": [{"fact_id": "f1", "quote": "탐나오 100g 표시가는 7,900원"}],
                },
            ),
        ]
    )

    class Model:
        def stream_turn(self, messages, definitions, delta, checkpoint, **kwargs):
            seen.append(json.loads(json.dumps(messages)))
            delta("실제 조각")
            return next(responses)

    output, text = run_agent(
        Model(),
        {
            "retail_lookup": {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample", "tamnao"],
            }
        },
        lambda spec: executed.append(spec) or result(),
        lambda name, data: events.append((name, data)),
        lambda: None,
    )
    assert output.data_status == "complete"
    assert text == "탐나오 100g 표시가는 7,900원입니다."
    assert len(executed) == 1
    assert any(message["role"] == "tool" for message in seen[1])
    assert [name for name, _ in events].count("tool_started") == 1
    assert [name for name, _ in events].count("tool_completed") == 1
    facts = {}
    compact_result(result(), facts)
    assert not supported_answer(
        "오아시스 100g은 7,900원", [{"fact_id": "f1", "quote": "오아시스 100g은 7,900원"}], facts
    )


def test_respond_before_read_is_returned_to_model_not_completed():
    responses = iter(
        [
            call("respond", {"text": "조회해볼게요", "claims": []}),
            call("current_observation"),
            call("respond", {"text": "확인했습니다.", "claims": []}),
        ]
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            return next(responses)

    calls = []
    run_agent(
        Model(),
        {"current_observation": {"operation": "current_observation", "source_ids": ["kma_aws"]}},
        lambda spec: calls.append(spec) or ResultEnvelope(request_id="r"),
        lambda *a: None,
        lambda: None,
    )
    assert len(calls) == 1


def test_repeat_tool_memo_has_no_duplicate_real_trace():
    responses = iter(
        [
            call("retail_lookup"),
            call("retail_lookup", identifier="c2"),
            call("respond", {"text": "확인했습니다.", "claims": []}),
        ]
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            return next(responses)

    events, calls = [], []
    run_agent(
        Model(),
        {"retail_lookup": {"operation": "retail_lookup", "source_ids": ["retail_sample"]}},
        lambda spec: calls.append(spec) or result(),
        lambda name, data: events.append(name),
        lambda: None,
    )
    assert len(calls) == 1 and events.count("tool_started") == 1


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("안녕", "greeting"),
        ("오늘 날짜가 뭐야", "current_date"),
        ("초보인데 준비물 알려줘", "preparation_help"),
    ],
)
def test_general_question_semantics_are_preserved_without_raw_text(text, intent):
    value = public_dialogue_intent(text)
    assert value["intent"] == intent
    assert text not in json.dumps(value, ensure_ascii=False)


def test_chat_complete_public_read_does_not_require_redundant_confirmation(monkeypatch):
    coordinator = Coordinator(Settings())
    session = Session(Settings())
    started = []
    monkeypatch.setattr(
        coordinator,
        "start_job",
        lambda session, spec, **kwargs: started.append((spec, kwargs)) or object(),
    )
    job, preparation = coordinator.start_chat(
        session, {"text": "현재 제주날씨", "conversation_id": "a"}
    )
    assert job is not None and preparation is None
    assert started[0][1]["dialogue_messages"] == [{"role": "user", "content": "현재 제주날씨"}]


def test_followup_public_options_and_stage_switch():
    previous = {
        "operation": "retail_lookup",
        "source_ids": ["retail_sample", "tamnao"],
        "package_weight_unit": "100 g",
        "fresh_or_dried": "건고사리",
    }
    assert continue_public_price(previous, "그럼 200g은?")["package_weight_unit"] == "200 g"
    survey = continue_public_price(previous, "그럼 생산지는?")
    assert survey["operation"] == "survey_link" and survey["survey_stage"] == "생산지"
    assert "package_weight_unit" not in survey


def test_provider_stream_fragments_usage_and_three_round_budget(monkeypatch):
    payloads = []

    def stream(method, url, **kwargs):
        payloads.append(kwargs["json"])
        fragments = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "c1",
                                    "function": {"name": "respond", "arguments": '{"text":"안'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": '녕하세요","claims":[]}'}}
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 1800,
                    "completion_tokens": 100,
                    "total_tokens": 1900,
                    "prompt_tokens_details": {"cached_tokens": 1500},
                    "completion_tokens_details": {"reasoning_tokens": 0},
                },
            },
        ]
        body = (
            "".join(
                "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in fragments
            )
            + "data: [DONE]\n\n"
        )

        class Context:
            def __enter__(self):
                return httpx.Response(
                    200, request=httpx.Request(method, url), content=body.encode()
                )

            def __exit__(self, *args):
                pass

        return Context()

    monkeypatch.setattr("gosari.agent.llm.httpx.stream", stream)
    client = LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    deltas = []
    messages = [
        {"role": "system", "content": "고정 시스템"},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "available_scopes": {
                        "retail_lookup": {
                            "operation": "retail_lookup",
                            "source_ids": ["retail_sample"],
                        }
                    }
                }
            ),
        },
    ]
    for _ in range(3):
        message = client.stream_turn(messages, tools(), deltas.append, lambda: None)
        assert json.loads(message["tool_calls"][0]["function"]["arguments"])["text"] == "안녕하세요"
    assert deltas == ["안", "녕하세요"] * 3
    assert client.usage_snapshot()["calls"] == 3
    assert client.usage_snapshot()["total_tokens"] == 5700
    assert client.usage_snapshot()["provider_cached_input_tokens"] == 4500
    assert payloads[0]["stream_options"]["include_usage"] is True


def test_cache_hit_keeps_public_context_for_next_weight_without_model(monkeypatch):
    from gosari.domain import CacheResolution

    coordinator = Coordinator(Settings())
    session = Session(Settings())
    cached = result().model_dump(mode="json")
    cached["assistant_text"] = "탐나오 100g 표시가는 7,900원입니다."
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup",
        lambda *args, **kwargs: (CacheResolution.EXACT_HIT, {"answer": cached, "evidence_ids": []}),
    )
    monkeypatch.setattr(
        coordinator,
        "_execute_agent_turn",
        lambda *args: pytest.fail("cache hit called model/source"),
    )
    job = coordinator.run_job(
        session,
        {
            "operation": "retail_lookup",
            "source_ids": ["retail_sample", "tamnao"],
            "package_weight_unit": "100 g",
        },
    )
    assert job.stage.value == "completed"
    started = []
    monkeypatch.setattr(
        coordinator, "start_job", lambda session, spec, **kwargs: started.append(kwargs) or object()
    )
    coordinator.start_chat(session, {"text": "그럼 200g은?"})
    messages = started[0]["dialogue_messages"]
    assert messages[-1] == {"role": "user", "content": "그럼 200g은?"}
    reference = next(
        json.loads(message["content"]) for message in messages if message["role"] == "tool"
    )
    assert reference["conditions"]["package_weight_unit"] == "100 g"
    assert "tamnao" in reference["conditions"]["source_ids"]
    assert coordinator._public_contexts.get((Session(Settings()).session_id, "default")) is None


def test_multi_scope_bypasses_single_scope_response_cache(monkeypatch):

    coordinator = Coordinator(Settings())
    session = Session(Settings())
    spec = {"operation": "retail_lookup", "source_ids": ["retail_sample"]}
    job, public = coordinator._new_job(session, spec)
    job.extra_scopes = {
        "current_observation": {"operation": "current_observation", "source_ids": ["kma_aws"]}
    }
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup",
        lambda *args, **kwargs: pytest.fail("combined request used primary-only cache key"),
    )
    monkeypatch.setattr(
        "gosari.agent.coordinator.store",
        lambda *args, **kwargs: pytest.fail("combined request stored under primary-only key"),
    )
    monkeypatch.setattr(coordinator, "_execute_agent_turn", lambda *args: result())
    coordinator._execute_job(session, job, public)
    assert job.stage.value == "completed"


def test_provider_outage_preserves_confirmed_public_tool_result():
    from gosari.domain.errors import GosariError

    class Model:
        def stream_turn(self, *args, **kwargs):
            raise GosariError("MODEL_UNAVAILABLE")

    calls, events = [], []
    output, answer = run_agent(
        Model(),
        {"retail_lookup": {"operation": "retail_lookup", "source_ids": ["retail_sample"]}},
        lambda spec: calls.append(spec) or result(),
        lambda name, data: events.append((name, data)),
        lambda: None,
    )
    assert len(calls) == 1 and output.data_status == "complete"
    assert "7900" in answer
    assert events[-1][1]["model_fallback"] is True


def test_partial_outing_date_seed_is_kst_and_preserves_public_region_hour(monkeypatch):
    from datetime import date

    monkeypatch.setattr("gosari.agent.public_planner.korea_today", lambda: date(2026, 11, 7))
    coordinator = Coordinator(Settings())
    prepared = coordinator.prepare(Session(Settings()), {"text": "내일 나들이"})
    assert prepared["form"]["initial_values"] == {"date": "2026-11-08"}
    from gosari.agent.public_planner import outing_initial_values

    assert outing_initial_values("2026-11-09 제주시 오전 9시") == {
        "date": "2026-11-09",
        "location_id": "jeju",
        "time_slot": "09:00",
    }


def test_read_is_required_before_final_response_and_only_pending_scopes_are_offered():
    choices = []
    responses = iter(
        [
            call("retail_lookup"),
            call("current_observation"),
            call("respond", {"text": "확인했습니다.", "claims": []}),
        ]
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            choices.append(kwargs["tool_choice"])
            return next(responses)

    run_agent(
        Model(),
        {
            "retail_lookup": {"operation": "retail_lookup", "source_ids": ["retail_sample"]},
            "current_observation": {"operation": "current_observation", "source_ids": ["kma_aws"]},
        },
        lambda spec: result(),
        lambda *args: None,
        lambda: None,
    )
    assert choices[0]["allowed_tools"]["mode"] == "required"
    assert [tool["function"]["name"] for tool in choices[0]["allowed_tools"]["tools"]] == [
        "retail_lookup",
        "current_observation",
    ]
    assert [tool["function"]["name"] for tool in choices[1]["allowed_tools"]["tools"]] == [
        "current_observation"
    ]
    assert choices[2] == {"type": "function", "function": {"name": "respond"}}


def test_wholesale_fact_preserves_market_price_basis_and_package_denominator():
    facts = {}
    compact_result(
        ResultEnvelope(
            request_id="r",
            result={
                "channel": "wholesale",
                "price_cards": [
                    {
                        "channel": "wholesale",
                        "source_id": "at_settlement",
                        "market_name": "서울가락",
                        "form": "생고사리",
                        "product_option": "특 · 상자",
                        "price_basis": "정산 평균가",
                        "price_value": 22000,
                        "original_quantity": "4.000",
                        "original_unit": "kg",
                        "price_as_of": "2026-05-12",
                    }
                ],
            },
        ),
        facts,
    )
    first = facts["f1"]
    assert "서울가락" in first["label"] and "4kg" in first["label"]
    assert "정산 평균가" in first["label"]
    assert "표시가" not in first["label"] and "공개 판매처" not in first["label"]


def test_no_matching_sample_and_weather_region_swap_have_precise_fact_boundaries():
    facts = {}
    compact_result(ResultEnvelope(request_id="r", result={"matched_sample_count": 0}), facts)
    assert facts["f1"]["value"] == 0
    assert "표본" in facts["f1"]["label"]
    facts = {}
    compact_result(
        ResultEnvelope(
            request_id="r", result={"stations": [{"station_name": "제주시", "temperature_c": 14.4}]}
        ),
        facts,
    )
    assert not supported_answer(
        "서귀포 기온은 14.4℃입니다.", [{"fact_id": "f1", "quote": "서귀포 기온은 14.4℃"}], facts
    )


@pytest.mark.parametrize(
    ("field", "metric", "unit"),
    [
        ("shipping_value", "배송비", "원"),
        ("coupon_price", "쿠폰가", "원"),
        ("price_per_kg_value", "kg 환산가", "원/kg"),
    ],
)
def test_auxiliary_price_claim_cannot_swap_vendor_or_option(field, metric, unit):
    facts = {}
    compact_result(
        ResultEnvelope(
            request_id="r",
            result={
                "price_cards": [{"source_id": "tamnao", "product_option": "100g", field: 3000}]
            },
        ),
        facts,
    )
    wrong = f"오아시스 100g {metric}는 3000{unit}"
    assert not supported_answer(wrong, [{"fact_id": "f1", "quote": wrong}], facts)
    wrong_option = f"탐나오 200g {metric}는 3000{unit}"
    assert not supported_answer(wrong_option, [{"fact_id": "f1", "quote": wrong_option}], facts)
    correct = f"탐나오 100g {metric}는 3000{unit}"
    assert supported_answer(correct, [{"fact_id": "f1", "quote": correct}], facts)


def test_retail_source_host_and_bundle_weight_alias_keep_correct_natural_answer():
    facts = {}
    compact_result(
        ResultEnvelope(
            request_id="r",
            result={
                "price_cards": [
                    {
                        "source_id": "retail_sample",
                        "source_url": "https://www.tamnao.com/web/product/detail.do",
                        "product_option": "50g X 2봉",
                        "net_weight_value": 100,
                        "price_value": 17000,
                    }
                ]
            },
        ),
        facts,
    )
    correct = "탐나오100g은17,000원"
    assert supported_answer(correct, [{"fact_id": "f1", "quote": correct}], facts)
    for wrong in ("오아시스100g은17,000원", "탐나오200g은17,000원"):
        assert not supported_answer(wrong, [{"fact_id": "f1", "quote": wrong}], facts)


def test_failed_scope_is_attempted_once_and_next_round_allows_response():
    from gosari.domain.errors import GosariError

    choices, executed = [], []
    responses = iter(
        [
            call("retail_lookup"),
            call("respond", {"text": "가격 자료를 불러오지 못했어요.", "claims": []}),
        ]
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            choices.append(kwargs["tool_choice"])
            return next(responses)

    def execute(spec):
        executed.append(spec)
        raise GosariError("SOURCE_UNAVAILABLE")

    output, answer = run_agent(
        Model(),
        {"retail_lookup": {"operation": "retail_lookup", "source_ids": ["retail_sample"]}},
        execute,
        lambda *args: None,
        lambda: None,
    )
    assert len(executed) == 1 and output is None
    assert choices[1] == {"type": "function", "function": {"name": "respond"}}
    assert answer == "가격 자료를 불러오지 못했어요."


@pytest.mark.parametrize("respond_tool", [True, False])
def test_completed_legacy_model_body_is_preserved_without_validator_replacement(
    monkeypatch, respond_tool
):
    text = "성산 날씨를 비교했어요. 기온은 15.0℃예요."
    monkeypatch.setattr(
        "gosari.agent.runtime.supported_answer",
        lambda *args: pytest.fail("completed output must retain model body"),
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            return (
                call("respond", {"text": text})
                if respond_tool
                else {
                    "role": "assistant",
                    "content": text,
                }
            )

    events = []
    _, answer = run_agent(
        Model(),
        {},
        lambda spec: pytest.fail("no query requested"),
        lambda name, data: events.append((name, data)),
        lambda: None,
    )
    assert answer == text
    assert next(data for name, data in events if name == "assistant_completed") == {
        "text": text,
        "replacement": False,
    }


def test_system_prompts_have_service_domain_decline_and_no_standing_warning_instructions():
    from gosari.agent.dialogue import SYSTEM as dialogue_system
    from gosari.agent.llm import EXPLAIN_SYSTEM_PROMPT, STRUCTURE_SYSTEM_PROMPT
    from gosari.agent.runtime import SYSTEM as runtime_system

    for prompt in (dialogue_system, runtime_system, EXPLAIN_SYSTEM_PROMPT, STRUCTURE_SYSTEM_PROMPT):
        assert "고사리잇과 관련된 질문만 도와드릴 수 있어요." in prompt
        assert "제주 고사리" in prompt
        for removed in ("수확량", "허가", "안전도", "면책", "판정하지", "개인정보를 무시"):
            assert removed not in prompt


def test_stream_admission_calibrates_same_job_against_reported_input_without_raising_budget(
    monkeypatch,
):
    from gosari.agent.dialogue import dialogue_tools

    requests = []

    def stream(method, url, **kwargs):
        requests.append(kwargs["json"])
        usage = {"prompt_tokens": 5694, "completion_tokens": 13, "total_tokens": 5707}
        body = "data: " + json.dumps({"choices": [{"delta": {"content": "확인했어요."}}]}) + "\n\n"
        body += "data: " + json.dumps({"choices": [], "usage": usage}) + "\n\ndata: [DONE]\n\n"

        class Context:
            def __enter__(self):
                return httpx.Response(
                    200, request=httpx.Request(method, url), content=body.encode()
                )

            def __exit__(self, *args):
                pass

        return Context()

    monkeypatch.setattr("gosari.agent.llm.httpx.stream", stream)
    client = LlmClient(
        Settings(
            openai_api_key=token_hex(24),
            external_requests_enabled=True,
            model_job_token_budget=16000,
        )
    )
    messages = [{"role": "system", "content": "공개 대화 문맥입니다. " * 300}]
    for _ in range(2):
        client.stream_turn(messages, dialogue_tools(), lambda text: None, lambda: None)
    usage = client.usage_snapshot()
    assert len(requests) == 2 and usage["token_budget"] == 16000
    assert usage["total_tokens"] == 11414 and usage["remaining_token_budget"] == 4586
    first, second = usage["records"]
    assert first["input_tokens_estimate"] == first["input_tokens_heuristic_estimate"]
    assert second["input_tokens_estimate"] <= second["input_tokens_heuristic_estimate"]
    assert second["input_tokens_estimate"] >= 5694 * 1.25
    assert second["input_tokens_heuristic_estimate"] + 1800 > 16000 - 5707
    assert second["input_tokens_estimate"] + 1800 <= 16000 - 5707
