"""SRS §10.6 고정 회귀 표본 기대값. 마크다운이 아닌 코드·테스트로 판정한다."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from gosari.domain import ValueState
from gosari.quality import interpret_numeric
from gosari.quality.calculation import (
    Observation,
    common_month_days,
    deduplicate,
    price_per_kg,
    rain_stats,
    temperature_stats,
    valid_dates,
)
from gosari.sources.replay import (
    load_at_summary,
    load_current_observations,
    load_kma184,
    load_retail_products,
    load_seonheul,
)


def test_seonheul_2023_expected(fixtures_dir: Path) -> None:
    observations, meta = load_seonheul(fixtures_dir)
    rain = rain_stats(observations, "선흘", 2023, requested_days=61)
    assert rain.valid_days == 51
    assert rain.positive_days == 21
    temp_dates = valid_dates(observations, "선흘", 2023, "average_temperature")
    assert len(temp_dates) == 50
    assert meta["file_hash"] == "9e7751d74fe3fcb21a905aa7dd6e8beb228679837e56a78b1219d1d1cf4ac145"


def test_seonheul_2024_expected(fixtures_dir: Path) -> None:
    observations, _ = load_seonheul(fixtures_dir)
    rain = rain_stats(observations, "선흘", 2024, requested_days=61)
    assert rain.valid_days == 61
    assert rain.positive_days == 24
    temp_dates = valid_dates(observations, "선흘", 2024, "average_temperature")
    assert len(temp_dates) == 60


def test_seonheul_common_month_days(fixtures_dir: Path) -> None:
    observations, _ = load_seonheul(fixtures_dir)
    common, per_year = common_month_days(observations, "선흘", [2023, 2024], "daily_rainfall")
    assert len(common) == 51
    assert min(common) == "04-11"
    assert max(common) == "05-31"
    rain_2023 = rain_stats(observations, "선흘", 2023, restrict_month_days=common)
    rain_2024 = rain_stats(observations, "선흘", 2024, restrict_month_days=common)
    assert rain_2023.positive_days == 21
    assert rain_2024.positive_days == 20
    assert rain_2023.valid_days == rain_2024.valid_days == 51
    assert len(per_year[2023]) == 51
    assert len(per_year[2024]) == 61


def test_kma184_value_states(fixtures_dir: Path) -> None:
    observations, _ = load_kma184(fixtures_dir)
    temp = [o for o in observations if o.element == "average_temperature"]
    rain = [o for o in observations if o.element == "daily_rainfall"]
    assert len(temp) == 61
    assert all(o.value_state in (ValueState.VALID, ValueState.VALID_ZERO) for o in temp)
    positive = [
        o for o in rain if o.value_state == ValueState.VALID and o.numeric and o.numeric > 0
    ]
    zeros = [o for o in rain if o.value_state == ValueState.VALID_ZERO]
    blanks = [o for o in rain if o.value_state == ValueState.UNRESOLVED_BLANK]
    assert len(positive) == 24
    assert len(zeros) == 8
    assert len(blanks) == 29


def test_current_observation_table(fixtures_dir: Path) -> None:
    stations, meta = load_current_observations(fixtures_dir)
    assert len(stations) == 43
    assert meta["verified_on"] == "2026-11-05"
    jeju184 = next(s for s in stations if s["station_code"] == "184")
    assert jeju184["temperature_c"] == Decimal("16.5")
    assert jeju184["day_rain_mm"] == Decimal("5")


def test_at_summary_sample(fixtures_dir: Path) -> None:
    rows, _ = load_at_summary(fixtures_dir)
    apr21 = [r for r in rows if r["settlement_date"] == "2026-04-21"]
    may12 = [r for r in rows if r["settlement_date"] == "2026-05-12"]
    assert sum(int(r["total_bracken_rows"]) for r in apr21) == 181
    assert sum(int(r["total_bracken_rows"]) for r in may12) == 126
    assert all(int(r["origin_name_contains_jeju"]) == 0 for r in rows)


def test_retail_price_conversion(fixtures_dir: Path) -> None:
    products, _ = load_retail_products(fixtures_dir)
    tamnao200 = next(p for p in products if p.get("weight_g") == 200)
    assert tamnao200["displayPriceWon"] == 32500
    assert price_per_kg(Decimal(32500), Decimal(200)) == Decimal(162500)
    assert tamnao200["shippingWon"] == 4000
    assert tamnao200["transactionVerified"] is False


def test_value_interpretation_rules() -> None:
    assert interpret_numeric("0").state == ValueState.VALID_ZERO
    assert interpret_numeric("0.0").state == ValueState.VALID_ZERO
    assert interpret_numeric("").state == ValueState.UNRESOLVED_BLANK
    assert interpret_numeric(None).state == ValueState.MISSING
    assert interpret_numeric("abc").state == ValueState.ERROR
    assert interpret_numeric("-3.5").state == ValueState.VALID
    assert interpret_numeric("5.2").numeric == Decimal("5.2")


def test_zero_denominator_is_null() -> None:
    stats = rain_stats([], "없는지점", 2023)
    assert stats.valid_days == 0
    assert stats.ratio is None
    avg, count = temperature_stats([], "없는지점", 2023)
    assert avg is None
    assert count == 0


def test_dedupe_and_conflict() -> None:
    base = Observation(
        "jeju_579",
        "선흘",
        date(2023, 5, 16),
        "daily_rainfall",
        "3",
        Decimal(3),
        ValueState.VALID,
    )
    same = Observation(
        "jeju_579",
        "선흘",
        date(2023, 5, 16),
        "daily_rainfall",
        "3",
        Decimal(3),
        ValueState.VALID,
    )
    conflict = Observation(
        "jeju_579",
        "선흘",
        date(2023, 5, 16),
        "daily_rainfall",
        "5",
        Decimal(5),
        ValueState.VALID,
    )
    result = deduplicate([base, same])
    assert len(result.unique) == 1
    assert result.duplicate_count == 1
    assert not result.conflicts
    result = deduplicate([base, conflict])
    assert len(result.conflicts) == 1


def test_leap_day_only_in_leap_year() -> None:
    obs = [
        Observation(
            "x",
            "s",
            date(2024, 2, 29),
            "daily_rainfall",
            "1",
            Decimal(1),
            ValueState.VALID,
        ),
        Observation(
            "x",
            "s",
            date(2023, 3, 1),
            "daily_rainfall",
            "1",
            Decimal(1),
            ValueState.VALID,
        ),
        Observation(
            "x",
            "s",
            date(2024, 3, 1),
            "daily_rainfall",
            "1",
            Decimal(1),
            ValueState.VALID,
        ),
    ]
    common, _ = common_month_days(obs, "s", [2023, 2024], "daily_rainfall")
    assert common == {"03-01"}
