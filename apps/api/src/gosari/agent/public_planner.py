"""자연어에서 확인 가능한 공개 값만 새 DTO로 만든다. 원문은 모델에 보내지 않는다."""

import calendar
import re
from datetime import date, timedelta
from typing import Any

from gosari.sources.weather import JEJU_LOCATIONS, korea_today


def public_plan(text: str) -> dict[str, Any] | None:
    public_names = [row[1] for row in JEJU_LOCATIONS] + ["선흘", "제주"]
    region_pattern = "|".join(
        re.escape(name) for name in sorted(public_names, key=len, reverse=True)
    )
    regions = list(re.finditer(region_pattern, text))
    names = [match.group() for match in regions]
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", text)})
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if any(word in text for word in ("가격", "얼마", "도매", "소매", "조사가", "상품")):
        if "도매" in text or "정산" in text:
            return {
                "operation": "market_query",
                "source_ids": ["at_settlement"],
                "price_channel": "wholesale",
            }
        if "조사가" in text or "산림조합" in text:
            return {
                "operation": "survey_link",
                "source_ids": ["forestinfo"],
                "price_channel": "survey",
            }
        if "소매" in text or "상품" in text or "판매" in text:
            return {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample"],
                "price_channel": "retail",
            }
        return None
    if names and len(years) >= 2 and not dates:
        period = _history_period(text, years)
        if period is None or len(set(names)) != 1:
            return None
        elements = []
        if any(word in text for word in ("강수", "비", "날씨")):
            elements.append("daily_rainfall")
        if any(word in text for word in ("기온", "온도", "날씨")):
            elements.append("average_temperature")
        return {
            "operation": "history_compare",
            "source_ids": ["jeju_579"],
            "station_selections": [{"source_id": "jeju_579", "station_name": names[0]}],
            "years": years,
            "month_day_start": period[0],
            "month_day_end": period[1],
            "elements": elements or ["daily_rainfall", "average_temperature"],
            "comparison_scope": "common_valid_month_days",
            "aggregation": "count_positive_days",
            "unit": "day",
            "timezone": "Asia/Seoul",
        }
    if (dates or any(day in text for day in ("오늘", "내일", "모레"))) and any(
        word in text for word in ("날씨", "나들이", "예보", "비교")
    ):
        candidates = _outing_candidates(text, regions)
        if candidates is None:
            return None
        return {
            "operation": "outing_compare",
            "source_ids": ["open_meteo"],
            "candidates": candidates,
            "preferred_elements": ["low_rain", "mild_temperature", "low_wind"],
        }
    if any(word in text for word in ("당일", "현재", "지금")):
        return {"operation": "current_observation", "source_ids": ["kma_aws"]}
    if "관측소" in text or "지역 목록" in text:
        return {"operation": "station_search", "source_ids": ["jeju_578"]}
    return None


def _history_period(text: str, years: list[int]) -> tuple[str, str] | None:
    shorthand = re.search(r"(\d{1,2})월\s*(\d{1,2})\s*[~∼-]\s*(\d{1,2})일?", text)  # noqa: RUF001
    if shorthand:
        parts = [(int(shorthand[1]), int(shorthand[2])), (int(shorthand[1]), int(shorthand[3]))]
    else:
        days = list(re.finditer(r"(?:(\d{1,2})월\s*)?(\d{1,2})일", text))
        parts = []
        month = None
        for match in days:
            if match[1]:
                month = int(match[1])
            if month is None:
                return None
            parts.append((month, int(match[2])))
        if len(parts) == 1:
            parts *= 2
        if not parts:
            month_range = re.search(r"(\d{1,2})\s*[~∼-]\s*(\d{1,2})월", text)  # noqa: RUF001
            months = [int(value) for value in re.findall(r"(\d{1,2})월", text)]
            if month_range:
                months = [int(month_range[1]), int(month_range[2])]
            if months:
                if len(months) > 2 or any(not 1 <= value <= 12 for value in months):
                    return None
                parts = [
                    (months[0], 1),
                    (months[-1], min(calendar.monthrange(y, months[-1])[1] for y in years)),
                ]
            elif "봄" in text:
                parts = [(4, 1), (5, 31)]
    if len(parts) != 2 or parts[0] > parts[1]:
        return None
    try:
        for year in years:
            for month, day in parts:
                date(year, month, day)
    except ValueError:
        return None
    return f"{parts[0][0]:02d}-{parts[0][1]:02d}", f"{parts[1][0]:02d}-{parts[1][1]:02d}"


_HOUR = re.compile(r"(?:(오전|오후)\s*)?(\d{1,2})(?::(\d{2})|\s*시)(?:\s*(?:(\d{1,2})분|(반)))?")


def _hours(text: str) -> list[str] | None:
    values = []
    for match in _HOUR.finditer(text):
        period, raw, minutes, spoken_minutes, half = match.groups()
        hour = int(raw)
        if (
            (minutes is not None and minutes != "00")
            or spoken_minutes not in (None, "0", "00")
            or half
        ):
            return None
        if period:
            if not 1 <= hour <= 12:
                return None
            hour = hour % 12 + (12 if period == "오후" else 0)
        elif minutes is None:
            # A bare 3시 does not establish morning versus afternoon.
            return None
        if not 0 <= hour < 24:
            return None
        values.append(f"{hour:02d}:00")
    return values


def _outing_candidates(text: str, regions: list[re.Match[str]]) -> list[dict[str, Any]] | None:
    if not regions:
        return None
    date_mentions = []
    for match in re.finditer(r"\d{4}-\d{2}-\d{2}|오늘|내일|모레", text):
        raw = match.group()
        try:
            day = (
                (korea_today() + timedelta(days={"오늘": 0, "내일": 1, "모레": 2}[raw])).isoformat()
                if raw in ("오늘", "내일", "모레")
                else date.fromisoformat(raw).isoformat()
            )
        except ValueError:
            return None
        date_mentions.append((match.start(), day))
    unique_dates = {day for _, day in date_mentions}
    all_hours = _hours(text)
    if not all_hours or not date_mentions:
        return None
    candidates = []
    for index, region in enumerate(regions):
        end = regions[index + 1].start() if index + 1 < len(regions) else len(text)
        local_hours = _hours(text[region.end() : end])
        if local_hours is None:
            return None
        if not local_hours:
            if len(set(all_hours)) != 1:
                return None
            local_hours = [all_hours[0]]
        if len(unique_dates) == 1:
            day = next(iter(unique_dates))
        else:
            preceding = [day for position, day in date_mentions if position < region.start()]
            following = [day for position, day in date_mentions if region.end() <= position < end]
            if preceding:
                day = preceding[-1]
            elif len(following) == 1:
                day = following[0]
            else:
                return None
        for hour in local_hours:
            candidates.append({"station_name": region.group(), "date": day, "time_slot": hour})
    return candidates if 1 <= len(candidates) <= 12 else None
