from datetime import date
from secrets import token_hex

import pytest

from gosari.agent.coordinator import Coordinator
from gosari.config import Settings
from gosari.sessions import Session


@pytest.fixture
def prepare(monkeypatch):
    settings = Settings(openai_api_key=token_hex(24), external_requests_enabled=True)
    coordinator = Coordinator(settings)
    session = Session(settings)
    monkeypatch.setattr("gosari.agent.public_planner.korea_today", lambda: date(2026, 11, 7))
    monkeypatch.setattr(
        coordinator.llm, "structure_question", lambda *a: pytest.fail("prepare called model")
    )
    monkeypatch.setattr("httpx.get", lambda *a, **k: pytest.fail("prepare called source"))
    monkeypatch.setattr("httpx.post", lambda *a, **k: pytest.fail("prepare called model HTTP"))
    return lambda text: coordinator.prepare(session, {"text": text})


@pytest.mark.parametrize(
    "text", ["제주 고사리가격", "제주 고사리 가격", "고사리 얼마야?", "고사리 시세"]
)
def test_generic_price_stays_in_chat_and_asks_price_conditions(prepare, text):
    result = prepare(text)
    assert result["feature"] == "price"
    assert result["needs_confirmation"]
    assert "spec" not in result
    form = result["form"]
    assert form["kind"] == "price_conditions"
    assert form["inline"] is True
    assert form["feature_hint"] == "price"
    assert [choice["value"] for choice in form["price_channels"]] == [
        "wholesale",
        "survey",
        "retail",
    ]
    assert "연도" not in str(form["questions"])
    assert "navigate" not in result and "route" not in result


@pytest.mark.parametrize(
    ("text", "operation"),
    [
        ("탐나오 고사리 보여줘", "retail_lookup"),
        ("오아시스 고사리 얼마야", "retail_lookup"),
        ("제주 고사리 소매가격", "retail_lookup"),
        ("제주 고사리 판매가", "retail_lookup"),
        ("산림조합 고사리 알려줘", "survey_link"),
        ("제주 고사리 조사가", "survey_link"),
    ],
)
def test_explicit_read_intent_is_ready_for_inline_job(prepare, text, operation):
    result = prepare(text)
    assert result["feature"] == "price"
    assert result["needs_confirmation"] is False
    assert result["spec"]["operation"] == operation
    assert "form" not in result


def test_wholesale_missing_date_and_market_stays_in_inline_conditions(prepare):
    result = prepare("제주 생고사리 도매 정산 가격")
    assert result["needs_confirmation"] is True
    assert "spec" not in result
    assert result["form"]["kind"] == "price_conditions"
    assert result["form"]["initial_values"]["fresh_or_dried"] == "생고사리"
    assert result["form"]["initial_values"]["origin_filter"] == "제주"
    assert set(result["form"]["missing_fields"]) >= {"settlement_date", "market_ids"}


def test_explicit_wholesale_conditions_are_preserved_without_weather_questions(prepare):
    result = prepare("2026-11-04부터 2026-11-05까지 시장코드 110001 제주 건고사리 도매가격")
    assert result["needs_confirmation"] is False
    assert result["spec"]["settlement_date"] == "2026-11-04"
    assert result["spec"]["settlement_date_end"] == "2026-11-05"
    assert result["spec"]["market_ids"] == ["110001"]
    assert result["spec"]["fresh_or_dried"] == "건고사리"


def test_ambiguous_channels_are_chosen_inside_chat(prepare):
    result = prepare("제주 고사리 도매랑 소매 가격")
    assert result["needs_confirmation"] is True
    assert "spec" not in result
    assert "price_channel" in result["form"]["missing_fields"]


def test_private_hints_stay_local_and_raw_text_is_not_a_public_spec(prepare):
    result = prepare("우리 엄마와 나눈 제주 고사리가격 010-9724-6381")
    assert result["classification"] == "personal"
    assert "spec" not in result


def test_invalid_explicit_trade_date_is_not_replaced_by_today(prepare):
    result = prepare("2026-02-30 시장코드110001 제주 고사리 도매 가격")
    assert result["needs_confirmation"] is True
    assert "spec" not in result
    assert "settlement_date" in result["form"]["missing_fields"]


def test_relative_wholesale_day_uses_korean_date_and_keeps_known_market(prepare):
    result = prepare("어제 서울 가락시장 생고사리 도매가격")
    assert result["needs_confirmation"] is False
    assert result["spec"]["settlement_date"] == "2026-11-06"
    assert result["spec"]["market_ids"] == ["110001"]


def test_explicit_retail_weight_and_provider_are_preserved(prepare):
    result = prepare("탐나오 건고사리200g판매가")
    assert result["needs_confirmation"] is False
    assert result["spec"]["package_weight_unit"] == "200 g"
    assert result["spec"]["fresh_or_dried"] == "건고사리"
    assert result["spec"]["source_ids"] == ["retail_sample", "tamnao"]
