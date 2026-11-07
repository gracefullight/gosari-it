"""Actual failed-job token receipt replayed through HTTP-mocked streaming."""

import json
from secrets import token_hex

import httpx
import pytest

from gosari.agent.dialogue import dialogue_tools
from gosari.agent.llm import LlmClient
from gosari.config import Settings
from gosari.domain.errors import GosariError


def failed_job_record():
    return {
        "model": "gpt-6-luna",
        "request_sent": True,
        "status": "completed",
        "usage_status": "reported",
        "input_tokens_estimate": 10344,
        "input_tokens_heuristic_estimate": 10344,
        "input_tokens": 5917,
        "output_tokens": 14,
        "total_tokens": 5931,
        "reasoning_tokens": 0,
        "provider_cached_input_tokens": 0,
        "elapsed_ms": 0,
    }


def client(budget=None):
    settings = {"openai_api_key": token_hex(24), "external_requests_enabled": True}
    if budget is not None:
        settings["model_job_token_budget"] = budget
    result = LlmClient(Settings(**settings))
    result.begin_job()
    result._local.records = [failed_job_record()]
    result._local.remaining = result.settings.model_job_token_budget - 5931
    return result


def messages():
    # A longer follow-up after the first tool response: the whole prior conversation
    # is valid input, including the actual fixed-schema overhead.
    return [{"role": "system", "content": "공개 대화 문맥을 이어갑니다. " * 300}]


@pytest.fixture
def provider(monkeypatch):
    calls = []

    def stream(method, url, **kwargs):
        calls.append(kwargs["json"])
        body = (
            "data: "
            + json.dumps({"choices": [{"delta": {"content": "확인한 날씨를 비교했어요."}}]})
            + "\n\n"
        )
        body += (
            "data: "
            + json.dumps(
                {
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 7000,
                        "completion_tokens": 500,
                        "total_tokens": 7500,
                    },
                }
            )
            + "\n\ndata: [DONE]\n\n"
        )

        class Response:
            def __enter__(self):
                return httpx.Response(
                    200, request=httpx.Request(method, url), content=body.encode()
                )

            def __exit__(self, *args):
                pass

        return Response()

    monkeypatch.setattr("gosari.agent.llm.httpx.stream", stream)
    return calls


def test_old_16k_budget_reproduces_block_after_actual_5931_token_first_round(provider):
    model = client(16000)
    with pytest.raises(GosariError) as error:
        model.stream_turn(messages(), dialogue_tools(), lambda text: None, lambda: None)
    assert error.value.code == "BUDGET_EXCEEDED" and provider == []
    assert model.usage_snapshot()["remaining_token_budget"] == 10069


def test_default_finite_budget_allows_three_rounds_with_same_long_context_and_exact_usage(provider):
    model = client()
    assert model.settings.model_job_token_budget == 64000
    for _ in range(2):
        model.stream_turn(messages(), dialogue_tools(), lambda text: None, lambda: None)
    usage = model.usage_snapshot()
    assert len(provider) == 2 and usage["calls"] == 3
    assert usage["total_tokens"] == 20931 and usage["remaining_token_budget"] == 43069
    assert usage["token_budget"] == 64000 and model.settings.max_plan_steps == 8
    assert all(call["max_completion_tokens"] == 1800 for call in provider)


def test_larger_budget_still_stops_unknown_usage_and_plan_limit_before_provider(provider):
    model = client()
    model._local.remaining = None
    with pytest.raises(GosariError) as unknown:
        model.stream_turn(messages(), dialogue_tools(), lambda text: None, lambda: None)
    assert unknown.value.code == "BUDGET_EXCEEDED" and provider == []
    model._local.remaining = 64000
    model._local.records = [failed_job_record() for _ in range(8)]
    with pytest.raises(GosariError) as exhausted:
        model.stream_turn(messages(), dialogue_tools(), lambda text: None, lambda: None)
    assert exhausted.value.code == "BUDGET_EXCEEDED" and provider == []
