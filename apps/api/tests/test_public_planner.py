from datetime import date

import pytest

from gosari.agent.public_planner import public_plan


def test_region_clauses_keep_their_own_morning_and_afternoon_times(monkeypatch):
    monkeypatch.setattr("gosari.agent.public_planner.korea_today", lambda: date(2026, 11, 7))
    result = public_plan("내일 제주시 오전 9시랑 서귀포 오후 3시 비교해줘")
    assert result is not None
    assert result["candidates"] == [
        {"station_name": "제주시", "date": "2026-11-08", "time_slot": "09:00"},
        {"station_name": "서귀포", "date": "2026-11-08", "time_slot": "15:00"},
    ]


def test_korean_month_and_inherited_day_range_are_preserved():
    result = public_plan("선흘 2023년과 2024년 4월 11일부터 12일까지 강수 비교")
    assert result is not None
    assert result["years"] == [2023, 2024]
    assert result["month_day_start"] == "04-11"
    assert result["month_day_end"] == "04-12"
    assert result["elements"] == ["daily_rainfall"]


@pytest.mark.parametrize(
    "period,expected",
    [
        ("4월 11~12일", ("04-11", "04-12")),
        ("4~5월", ("04-01", "05-31")),
        ("4월부터 5월까지", ("04-01", "05-31")),
        ("5월 31일부터 6월 2일까지", ("05-31", "06-02")),
        ("봄", ("04-01", "05-31")),
    ],
)
def test_explicit_comparison_period_variants(period, expected):
    result = public_plan(f"선흘 2023년과 2024년 {period} 기온 비교")
    assert result is not None
    assert (result["month_day_start"], result["month_day_end"]) == expected


@pytest.mark.parametrize(
    "query",
    [
        "내일 제주시 오전이랑 서귀포 오후 비교해줘",
        "내일 제주시 3시 날씨",
        "내일 제주시 오후 3시 반 날씨",
        "선흘 2023년과 2024년 강수 비교",
        "선흘 2023년과 2024년 4월 31일 비교",
        "선흘 2023년과 2024년 5월 12일부터 4월 11일까지 비교",
    ],
)
def test_unresolved_or_invalid_conditions_require_confirmation(query):
    assert public_plan(query) is None


def test_unambiguous_shared_hour_applies_to_both_regions(monkeypatch):
    monkeypatch.setattr("gosari.agent.public_planner.korea_today", lambda: date(2026, 11, 7))
    result = public_plan("내일 오전 9시 제주시랑 서귀포 날씨 비교")
    assert result is not None
    assert [candidate["time_slot"] for candidate in result["candidates"]] == ["09:00", "09:00"]


def test_ambiguous_outing_asks_for_outing_conditions_without_sending_raw_text(monkeypatch):
    from gosari.agent.coordinator import Coordinator
    from gosari.config import Settings
    from gosari.sessions import Session

    coordinator = Coordinator(Settings(external_requests_enabled=True, openai_api_key="test"))
    monkeypatch.setattr(
        coordinator.llm,
        "structure_question",
        lambda *args: pytest.fail("unresolved input reached model"),
    )
    result = coordinator.prepare(
        Session(Settings()), {"text": "내일 제주시 오전이랑 서귀포 오후 비교해줘"}
    )
    assert result["feature"] == "outing"
    assert result["needs_confirmation"]
    assert result["form"]["feature_hint"] == "outing"
    assert "시각" in result["form"]["questions"][0]
    assert "spec" not in result
