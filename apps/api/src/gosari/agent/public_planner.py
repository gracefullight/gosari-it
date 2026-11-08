"""자연어에서 확인 가능한 공개 값만 새 DTO로 만든다. 원문은 모델에 보내지 않는다."""

import calendar
import re
from datetime import date, timedelta
from typing import Any

from gosari.sources.weather import JEJU_LOCATIONS, korea_today

PRICE_WORDS = (
    "가격",
    "얼마",
    "시세",
    "도매",
    "정산",
    "소매",
    "조사가",
    "상품",
    "판매가",
    "산림조합",
    "탐나오",
    "오아시스",
)


def is_price_question(text: str) -> bool:
    return any(word in text for word in PRICE_WORDS)


def price_initial_values(text: str) -> dict[str, Any]:
    """정형 공개 조건만 추출한다. 원문/개인 별칭은 반환하지 않는다."""
    values: dict[str, Any] = {}
    fresh = bool(re.search(r"생\s*고사리", text))
    dried = bool(re.search(r"건\s*고사리|말린\s*고사리|건조\s*고사리", text))
    if fresh != dried:
        values["fresh_or_dried"] = "생고사리" if fresh else "건고사리"
    elif fresh and dried:
        values["fresh_or_dried"] = ""
    if "제주" in text:
        values["origin_filter"] = "제주"
    explicit_dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    days: list[date] = []
    if explicit_dates:
        try:
            days = [date.fromisoformat(day) for day in explicit_dates]
        except ValueError:
            days = []
    else:
        relative = re.findall(r"오늘|어제|그제", text)
        days = [
            korea_today() - timedelta(days={"오늘": 0, "어제": 1, "그제": 2}[day])
            for day in relative
        ]
    if 1 <= len(days) <= 2 and days[0] <= days[-1] <= korea_today():
        values["settlement_date"] = days[0].isoformat()
        values["settlement_date_end"] = days[-1].isoformat()
    markets = re.findall(r"시장\s*코드\s*[:：]?\s*(\d{6})(?!\d)", text)  # noqa: RUF001
    if not markets and any(
        name in text for name in ("서울가락", "서울 가락", "가락시장", "가락 시장")
    ):
        markets = ["110001"]
    if markets:
        values["market_ids"] = list(dict.fromkeys(markets))
    weight = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g)(?=$|[^a-zA-Z])", text, re.IGNORECASE)
    if weight:
        values["package_weight_unit"] = f"{weight[1]} {weight[2].lower()}"
        bundle = re.search(r"50\s*g\s*[xX×]\s*2\s*봉", text)  # noqa: RUF001
        if bundle:
            values["product_option"] = "50g X 2봉"
            values.pop("package_weight_unit", None)
    stage = [name for name in ("생산지", "도매지", "소비지") if name in text]
    if len(stage) == 1:
        values["survey_stage"] = stage[0]
    return values


def _price_spec(text: str) -> dict[str, Any] | None:
    retail = any(
        word in text for word in ("소매", "상품", "판매가", "탐나오", "오아시스", "쇼핑몰")
    )
    survey = "조사가" in text or ("산림조합" in text and not retail)
    wholesale = bool(re.search(r"도매(?!지)|정산", text))
    channels = [
        name
        for name, enabled in (("retail", retail), ("survey", survey), ("wholesale", wholesale))
        if enabled
    ]
    if len(channels) != 1:
        return None
    channel = channels[0]
    operation, source = {
        "retail": ("retail_lookup", "retail_sample"),
        "survey": ("survey_link", "forestinfo"),
        "wholesale": ("market_query", "at_settlement"),
    }[channel]
    values = price_initial_values(text)
    if channel != "wholesale":
        for field in ("settlement_date", "settlement_date_end", "market_ids"):
            values.pop(field, None)
    sources = [source]
    if channel == "retail":
        sources += [
            source_id
            for label, source_id in (("탐나오", "tamnao"), ("오아시스", "oasis"))
            if label in text
        ]
    return {"operation": operation, "source_ids": sources, "price_channel": channel, **values}


def continue_public_price(previous: dict[str, Any], text: str) -> dict[str, Any] | None:
    if previous.get("operation") not in ("retail_lookup", "survey_link", "market_query"):
        return None
    changes = price_initial_values(text)
    if not changes:
        return None
    # Only recognized public selectors are inherited; no raw utterance is retained or sent.
    spec = {key: value for key, value in previous.items() if key != "contains_personal_hint"}
    explicit = _price_spec(text) if is_price_question(text) else None
    if explicit:
        spec.update(explicit)
    elif changes.get("survey_stage"):
        spec.update(operation="survey_link", source_ids=["forestinfo"], price_channel="survey")
    if "package_weight_unit" in changes:
        spec.pop("product_option", None)
    if "product_option" in changes:
        spec.pop("package_weight_unit", None)
    spec.update(changes)
    if spec.get("operation") != "market_query":
        for key in ("settlement_date", "settlement_date_end", "market_ids"):
            spec.pop(key, None)
    if spec.get("operation") == "survey_link":
        for key in ("product_id", "product_option", "package_weight_unit"):
            if key not in changes:
                spec.pop(key, None)
    return spec


def public_dialogue_intent(text: str) -> dict[str, Any]:
    intent = "service_help"
    for name, words in (
        ("greeting", ("안녕", "반가", "하이")),
        ("current_date", ("오늘 날짜", "오늘날짜", "무슨 요일", "몇일", "며칠")),
        ("preparation_help", ("준비물", "초보", "준비해야")),
        ("summarize", ("요약", "설명", "정리")),
        ("compare", ("비교", "차이")),
    ):
        if any(word in text for word in words):
            intent = name
            break
    vocabulary = ("고사리", "날씨", "가격", "나들이", "수첩", "나눔", "생산지", "도매지", "소비지")
    result: dict[str, Any] = {
        "intent": intent,
        "topics": [word for word in vocabulary if word in text],
    }
    if intent == "current_date":
        result["today"] = korea_today().isoformat()
    return result


def outing_initial_values(text: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    days: set[str] = set()
    for raw in re.findall(r"\d{4}-\d{2}-\d{2}|오늘|내일|모레", text):
        try:
            day = (
                (korea_today() + timedelta(days={"오늘": 0, "내일": 1, "모레": 2}[raw]))
                if raw in ("오늘", "내일", "모레")
                else date.fromisoformat(raw)
            )
            days.add(day.isoformat())
        except ValueError:
            continue
    if len(days) == 1:
        values["date"] = next(iter(days))
    locations = [identifier for identifier, name, *_ in JEJU_LOCATIONS if name in text]
    if len(locations) == 1:
        values["location_id"] = locations[0]
    hours = _hours(text)
    if hours and len(set(hours)) == 1:
        values["time_slot"] = hours[0]
    return values


def public_plan(text: str) -> dict[str, Any] | None:
    public_names = [row[1] for row in JEJU_LOCATIONS] + ["선흘", "제주"]
    region_pattern = "|".join(
        re.escape(name) for name in sorted(public_names, key=len, reverse=True)
    )
    regions = list(re.finditer(region_pattern, text))
    names = [match.group() for match in regions]
    years = sorted({int(y) for y in re.findall(r"(?:19|20)\d{2}", text)})
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if is_price_question(text):
        return _price_spec(text)
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
            "source_ids": ["kma_vilage", "open_meteo"],
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
