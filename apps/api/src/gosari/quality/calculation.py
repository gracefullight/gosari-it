"""SRS §10.3~10.7 결정론 계산. LLM에 최종값을 위임하지 않는다."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from gosari.domain import ValueState
from gosari.quality import is_usable


@dataclass(frozen=True)
class Observation:
    source_id: str
    station_key: str
    observation_date: date
    element: str
    raw: str | None
    numeric: Decimal | None
    value_state: ValueState
    accumulation_window: str = "1d"

    @property
    def natural_key(self) -> tuple[str, str, date, str, str]:
        return (
            self.source_id,
            self.station_key,
            self.observation_date,
            self.element,
            self.accumulation_window,
        )


NaturalKey = tuple[str, str, date, str, str]


@dataclass
class DedupeResult:
    unique: list[Observation] = field(default_factory=list)
    duplicate_count: int = 0
    conflicts: list[tuple[NaturalKey, list[Observation]]] = field(default_factory=list)


def deduplicate(observations: list[Observation]) -> DedupeResult:
    """동일 자연키·동일 의미는 1회 집계, 값/품질 충돌은 봉합하지 않고 보존한다."""
    groups: dict[NaturalKey, list[Observation]] = defaultdict(list)
    for obs in observations:
        groups[obs.natural_key].append(obs)
    result = DedupeResult()
    for key, rows in groups.items():
        first = rows[0]
        same = all(
            r.numeric == first.numeric and r.value_state == first.value_state and r.raw == first.raw
            for r in rows[1:]
        )
        if same:
            result.unique.append(first)
            result.duplicate_count += len(rows) - 1
        else:
            result.conflicts.append((key, rows))
    return result


def valid_dates(
    observations: list[Observation], station_key: str, year: int, element: str
) -> set[date]:
    return {
        o.observation_date
        for o in observations
        if o.station_key == station_key
        and o.observation_date.year == year
        and o.element == element
        and is_usable(o.value_state)
    }


def common_month_days(
    observations: list[Observation], station_key: str, years: list[int], element: str
) -> tuple[set[str], dict[int, set[date]]]:
    """연도 비교: 각 연도 유효 날짜의 MM-DD 교집합. 항목별로만 계산한다."""
    per_year = {y: valid_dates(observations, station_key, y, element) for y in years}
    if not per_year:
        return set(), per_year
    md_sets = [{d.strftime("%m-%d") for d in dates} for dates in per_year.values()]
    common = set.intersection(*md_sets) if md_sets else set()
    return common, per_year


def common_actual_dates(
    observations: list[Observation], station_keys: list[str], element: str
) -> set[date]:
    """지역 비교: 실제 YYYY-MM-DD 집합의 교집합."""
    sets = []
    for station in station_keys:
        sets.append(
            {
                o.observation_date
                for o in observations
                if o.station_key == station and o.element == element and is_usable(o.value_state)
            }
        )
    return set.intersection(*sets) if sets else set()


@dataclass
class RainStats:
    positive_days: int
    valid_days: int
    ratio: Decimal | None
    requested_days: int | None = None


def rain_stats(
    observations: list[Observation],
    station_key: str,
    year: int,
    *,
    restrict_month_days: set[str] | None = None,
    requested_days: int | None = None,
) -> RainStats:
    """양수 강수일 = count(unique valid dates where dailyRainfall > 0). 분모 0이면 비율 null."""
    dates = valid_dates(observations, station_key, year, "daily_rainfall")
    if restrict_month_days is not None:
        dates = {d for d in dates if d.strftime("%m-%d") in restrict_month_days}
    positive = {
        o.observation_date
        for o in observations
        if o.station_key == station_key
        and o.observation_date.year == year
        and o.element == "daily_rainfall"
        and is_usable(o.value_state)
        and o.numeric is not None
        and o.numeric > 0
        and (
            restrict_month_days is None
            or o.observation_date.strftime("%m-%d") in restrict_month_days
        )
    }
    valid_count = len(dates)
    ratio = Decimal(len(positive)) / Decimal(valid_count) if valid_count > 0 else None
    return RainStats(
        positive_days=len(positive),
        valid_days=valid_count,
        ratio=ratio,
        requested_days=requested_days,
    )


def temperature_stats(
    observations: list[Observation],
    station_key: str,
    year: int,
    *,
    restrict_month_days: set[str] | None = None,
) -> tuple[Decimal | None, int]:
    """유효 일평균 기온의 평균과 분모. 공통 날짜가 아니면 계산하지 않는다."""
    values = [
        o.numeric
        for o in observations
        if o.station_key == station_key
        and o.observation_date.year == year
        and o.element == "average_temperature"
        and is_usable(o.value_state)
        and o.numeric is not None
        and (
            restrict_month_days is None
            or o.observation_date.strftime("%m-%d") in restrict_month_days
        )
    ]
    if not values:
        return None, 0
    return sum(values) / Decimal(len(values)), len(values)


def price_per_kg(price_won: Decimal, weight_g: Decimal) -> Decimal | None:
    """내용물만의 환산. 중량·가격 의미가 확정된 경우만 호출한다 (SRS §10.7)."""
    if weight_g <= 0:
        return None
    return price_won / (weight_g / Decimal(1000))
