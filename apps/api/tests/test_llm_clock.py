import json
from datetime import UTC, datetime
from secrets import token_hex

import httpx
import pytest

from gosari.agent import build_public_spec, llm
from gosari.config import Settings


def test_runtime_clock_converts_utc_to_next_korean_day():
    prompt = llm.runtime_system_prompt(
        "원래 시스템 지침", datetime(2026, 11, 6, 15, 5, tzinfo=UTC)
    )
    assert "2026-11-07" in prompt
    assert "00:05" in prompt
    assert "토요일" in prompt
    assert "Asia/Seoul" in prompt
    assert "원래 시스템 지침" in prompt
    assert "자료" in prompt and "시점" in prompt


def test_runtime_clock_refreshes_each_call(monkeypatch):
    moments = iter(
        [datetime(2026, 11, 6, 14, 59, tzinfo=UTC), datetime(2026, 11, 6, 15, 1, tzinfo=UTC)]
    )
    requested_zones = []

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            requested_zones.append(str(tz))
            return next(moments).astimezone(tz)

    monkeypatch.setattr(llm, "datetime", Clock)
    before = llm.runtime_system_prompt("지침")
    after = llm.runtime_system_prompt("지침")
    assert "2026-11-06" in before and "23:59" in before
    assert "2026-11-07" in after and "00:01" in after
    assert requested_zones == ["Asia/Seoul", "Asia/Seoul"]


@pytest.mark.parametrize("path", ["chat", "structure"])
def test_both_http_paths_use_runtime_context_and_preserve_public_payload(monkeypatch, path):
    original = llm.runtime_system_prompt
    moment = datetime(2026, 11, 6, 15, 5, tzinfo=UTC)
    monkeypatch.setattr(llm, "runtime_system_prompt", lambda prompt: original(prompt, moment))
    captured = []

    def post(url, *, headers, json, timeout):
        captured.append(json)
        message = (
            {"content": "공개 자료 설명"}
            if path == "chat"
            else {
                "tool_calls": [
                    {
                        "function": {
                            "name": "run_public_analysis",
                            "arguments": '{"operation":"current_observation"}',
                        }
                    }
                ]
            }
        )
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": message}]},
        )

    monkeypatch.setattr(llm.httpx, "post", post)
    client = llm.LlmClient(Settings(openai_api_key=token_hex(24), external_requests_enabled=True))
    public = {"operation": "current_observation", "source_ids": ["kma_aws"]}
    if path == "chat":
        user = '{"observed_period":"2023-04-11","temperature_c":15.5}'
        assert client._chat("기존 설명 지침", user) == "공개 자료 설명"
        assert captured[0]["messages"][1]["content"] == user
        assert "기존 설명 지침" in captured[0]["messages"][0]["content"]
    else:
        expected = build_public_spec(public)
        assert client.structure_question(public) == expected
        assert json.loads(captured[0]["messages"][1]["content"]) == llm.public_model_data(expected)
    system = captured[0]["messages"][0]
    assert system["role"] == "system"
    assert "2026-11-07" in system["content"]
    assert "00:05" in system["content"]
    assert "Asia/Seoul" in system["content"]
