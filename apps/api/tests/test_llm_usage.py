from secrets import token_hex

import httpx
import pytest

from gosari.agent.llm import LlmClient
from gosari.config import Settings
from gosari.domain.errors import GosariError


def test_actual_usage_details_are_not_added_twice(monkeypatch):
    def post(url, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [{"message": {"content": "합성 설명"}}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 200,
                    "total_tokens": 300,
                    "prompt_tokens_details": {"cached_tokens": 70},
                    "completion_tokens_details": {"reasoning_tokens": 50},
                },
            },
        )

    monkeypatch.setattr("gosari.agent.llm.httpx.post", post)
    client = LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    client.begin_job()
    client._chat("합성 시스템", "공개 조건")
    usage = client.usage_snapshot()
    assert usage["usage_status"] == "reported"
    assert usage["calls"] == 1
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 200
    assert usage["reasoning_tokens"] == 50
    assert usage["provider_cached_input_tokens"] == 70
    assert usage["total_tokens"] == 300
    assert usage["remaining_token_budget"] == 15700
    assert usage["cost_usd"] is None
    assert "공개 조건" not in str(usage)


def test_missing_usage_is_unknown_and_prevents_another_model_call(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "합성 설명"}}]},
        )

    monkeypatch.setattr("gosari.agent.llm.httpx.post", post)
    client = LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    client._chat("합성 시스템", "공개 조건")
    with pytest.raises(GosariError) as error:
        client._chat("합성 시스템", "공개 조건")
    assert error.value.code == "BUDGET_EXCEEDED"
    assert len(calls) == 1
    usage = client.usage_snapshot()
    assert usage["usage_status"] == "unknown"
    assert usage["input_tokens"] is None
    assert usage["output_tokens"] is None
    assert usage["total_tokens"] is None
    assert usage["remaining_token_budget"] is None
    assert usage["cost_usd"] is None


def test_model_budget_stops_before_http_and_empty_job_reports_not_used(monkeypatch):
    calls = []
    monkeypatch.setattr("gosari.agent.llm.httpx.post", lambda *a, **kw: calls.append(1))
    client = LlmClient(
        Settings(
            openai_api_key=token_hex(24), external_requests_enabled=True, model_job_token_budget=32
        )
    )
    with pytest.raises(GosariError) as error:
        client._chat("합성 시스템", "공개 조건")
    assert error.value.code == "BUDGET_EXCEEDED"
    assert calls == []
    assert client.usage_snapshot()["usage_status"] == "not_used"


def test_nine_tool_calls_are_rejected(monkeypatch):
    def post(url, **kwargs):
        call = {
            "function": {
                "name": "run_public_analysis",
                "arguments": '{"operation":"current_observation"}',
            }
        }
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"tool_calls": [call] * 9}}]},
        )

    monkeypatch.setattr("gosari.agent.llm.httpx.post", post)
    client = LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    with pytest.raises(GosariError) as error:
        client.structure_question({"operation": "current_observation", "source_ids": ["kma_aws"]})
    assert error.value.code == "MODEL_UNAVAILABLE"


def test_http_failure_keeps_unknown_cost_and_no_alternate_model(monkeypatch):
    models = []

    def post(url, **kwargs):
        models.append(kwargs["json"]["model"])
        return httpx.Response(503, request=httpx.Request("POST", url))

    monkeypatch.setattr("gosari.agent.llm.httpx.post", post)
    client = LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    with pytest.raises(GosariError):
        client._chat("합성 시스템", "공개 조건")
    assert models == ["gpt-6-luna"]
    assert client.usage_snapshot()["usage_status"] == "unknown"
    assert client.usage_snapshot()["cost_usd"] is None
