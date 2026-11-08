"""Cache equivalence only: these guards never choose or execute an agent tool."""

import json
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from gosari.agent import ALLOWED_OPERATIONS
from gosari.agent.dialogue_privacy import contains_sensitive_dialogue, requires_private_dialogue
from gosari.cache.public_source import public_payload
from gosari.sources import json_hash
from gosari.sources.locations import public_places

GUARD_VERSION = "dialogue-guards-v2"
KOREA = ZoneInfo("Asia/Seoul")
_TRANSPORT_KEYS = frozenset({"request_id", "job_id", "event_id", "tool_call_id"})
_PRIVATE_TOOLS = frozenset({"search_personal_records", "open_personal_form", "open_street_view"})
_WORD_GROUPS = {
    "weather": ("날씨", "기상"),
    "forecast": ("예보", "일기예보"),
    "observation": ("관측", "관측값", "실황"),
    "station": ("관측소", "관측지점", "지점"),
    "outing": ("나들이", "외출"),
    "recommend": ("추천", "추천해"),
    "compare": ("비교", "비교해"),
    "price": ("가격", "가격정보"),
    "retail": ("판매가", "판매가격", "소매가", "소매", "상품가격"),
    "wholesale": ("도매", "도매가", "도매가격", "정산", "정산가", "거래가격"),
    "survey": ("조사가", "조사가격", "지역조사가"),
    "producer": ("생산지",),
    "distributor": ("도매지",),
    "consumer": ("소비지",),
    "tamnao": ("탐나오",),
    "oasis": ("오아시스", "오아시스마켓"),
    "forestinfo": ("산림조합", "산림조합중앙회"),
    "rain_probability": ("강수확률", "비확률", "비올확률"),
    "rain_amount": ("강수량", "강수", "비의양"),
    "rain": ("비",),
    "temperature": ("기온", "온도"),
    "wind": ("바람", "풍속", "바람세기"),
    "mild": ("온화", "온화한"),
    "lower": ("적은", "적음", "낮은", "낮음", "최저", "가장낮은", "약한", "약함"),
    "higher": ("많은", "많음", "높은", "높음", "최고", "가장높은", "강한", "강함"),
    "less_equal": ("이하",),
    "greater_equal": ("이상",),
    "less": ("미만",),
    "greater": ("초과",),
    "priority": ("우선", "우선순위", "먼저"),
    "relative": ("보다", "더"),
    "exclude": ("말고", "제외", "빼고"),
    "negative": ("안", "않는", "아닌", "아니", "아니야", "하지마", "하지말고", "말아줘"),
    "only": ("만",),
    "all": ("전체", "모두", "전부"),
    "private_land": ("사유지",),
    "national_land": ("국유지",),
    "public_land": ("공유지", "국공유지"),
    "ownership": ("소유", "소유구분", "토지", "필지"),
    "where": ("어디", "어디가"),
    "when": ("언제",),
    "how_much": ("얼마",),
    "count": ("몇개", "몇곳", "몇건"),
    "why": ("왜", "이유"),
    "location_set": ("곳", "지역"),
    "recent": ("최근",),
    "current": ("현재", "지금"),
    "this_week": ("이번주",),
    "next_week": ("다음주",),
    "last_week": ("지난주",),
    "spring": ("봄",),
    "summer": ("여름",),
    "autumn": ("가을",),
    "winter": ("겨울",),
    "jeju_island": ("제주", "제주도", "제주특별자치도"),
    "jeju_origin": ("제주산",),
    "seoul_market": ("서울가락", "가락시장"),
    "busan_market": ("부산엄궁", "엄궁시장"),
    "grade_top": ("특등급", "특"),
    "grade_high": ("상등급", "상"),
    "grade_middle": ("중등급", "중품"),
    "box": ("상자", "박스"),
    "bag": ("봉지", "봉"),
    "shipping": ("배송비", "배송"),
    "coupon": ("쿠폰",),
    "included": ("포함",),
    "excluded": ("별도",),
}
_LIGHT_WORDS = (
    "알려줘요",
    "알려주세요",
    "알려줘",
    "알려",
    "보여주세요",
    "보여줘",
    "보여",
    "조회해줘",
    "조회",
    "확인해줘",
    "확인",
    "해주세요",
    "해줘",
    "주세요",
    "부탁해요",
    "부탁",
    "정보",
    "어때요",
    "어때",
    "어떨까",
    "좋을까",
    "좋은",
    "좋아",
    "싶어",
    "있나요",
    "인가요",
    "줘",
    "인지",
    "에대해",
    "에대한",
    "기준으로",
    "기준",
    "그리고",
    "하고",
    "이랑",
    "중에서",
    "중",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "에서",
    "으로",
    "로",
    "와",
    "과",
    "랑",
    "좀",
    "요",
    "해",
    "오는",
    "올",
    "오기",
    "될까",
    "있어",
    "있을까",
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


@lru_cache(maxsize=1)
def _words() -> tuple[tuple[str, tuple[str, ...]], ...]:
    words: dict[str, tuple[str, ...]] = {word: () for word in _LIGHT_WORDS}
    for tag, aliases in _WORD_GROUPS.items():
        words.update({word: (tag,) for word in aliases})
    words.update(
        {"고사리": ("fern",), "생고사리": ("fern", "fresh"), "건고사리": ("fern", "dried")}
    )
    for identifier, place in public_places().items():
        words.setdefault(place[1], (f"place:{place[1]}",))
        words.setdefault(identifier, (f"place:{place[1]}",))
    words["서귀포시"] = words["서귀포"]
    # Name-only ambiguous stations cannot establish semantic equivalence.
    words["강정"] = ("ambiguous",)
    return tuple(sorted(words.items(), key=lambda item: len(item[0]), reverse=True))


def guard_fingerprint(question: str, *, now: datetime) -> str | None:
    """Ordered public operands; unfamiliar conditions keep exact caching only."""
    if requires_private_dialogue(question):
        return None
    text = normalize_text(question).casefold()
    # Korean spacing variants are equivalent; digits keep their boundaries.
    text = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", text)
    day = now.astimezone(KOREA).date()
    tokens: list[str] = []
    index = 0
    try:
        while index < len(text):
            tail = text[index:]
            match = re.match(r"(\d{4})-(\d{2})-(\d{2})|(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", tail)
            if match:
                values = match.groups()[:3] if match[1] else match.groups()[3:]
                tokens.append("date:" + date(*(int(value) for value in values)).isoformat())
            else:
                match = re.match(r"(\d{1,2})월\s*(\d{1,2})일", tail)
                if match:
                    month_day = date(2000, int(match[1]), int(match[2])).strftime("%m-%d")
                    tokens.append(f"date:--{month_day}:year-unspecified")
            if match:
                index += match.end()
                continue
            relative = next(
                (
                    word
                    for word in ("그저께", "어제", "오늘", "내일", "모레")
                    if tail.startswith(word)
                ),
                None,
            )
            if relative:
                offset = {"그저께": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2}[relative]
                tokens.append("date:" + (day + timedelta(days=offset)).isoformat())
                index += len(relative)
                continue
            match = re.match(
                r"(?:(오전|오후)\s*)?(\d{1,2})(?::(\d{2})|시(?:\s*(\d{1,2})분)?)", tail
            )
            if not match:
                match = re.match(r"(오전|오후)\s*(\d{1,2})()()", tail)
            if match:
                hour = int(match[2])
                minute = int(match[3] or match[4] or 0)
                if minute > 59 or hour > (12 if match[1] else 23):
                    return None
                if match[1]:
                    hour = hour % 12 + (12 if match[1] == "오후" else 0)
                precision = "qualified" if match[1] or ":" in match[0] else "unspecified"
                tokens.append(f"time:{hour:02}:{minute:02}:{precision}")
                index += match.end()
                continue
            match = re.match(r"(\d{4})년", tail)
            if match:
                tokens.append(f"year:{int(match[1])}")
                index += match.end()
                continue
            match = re.match(
                r"(\d+(?:\.\d+)?)\s*(킬로그램|그램|kg|g|원/kg|원|%|퍼센트|℃|°c|도|km/h|kmh|m/s|mm|일|개|곳|건)",
                tail,
            )
            if match:
                number = Decimal(match[1])
                unit = match[2]
                if unit in {"킬로그램", "kg"}:
                    number *= 1000
                unit = {
                    "킬로그램": "g",
                    "kg": "g",
                    "그램": "g",
                    "퍼센트": "%",
                    "도": "℃",
                    "°c": "℃",
                    "kmh": "km/h",
                }.get(unit, unit)
                tokens.append(f"quantity:{number.normalize():f}:{unit}")
                index += match.end()
                continue
            word = next(((word, tags) for word, tags in _words() if tail.startswith(word)), None)
            if word:
                if "ambiguous" in word[1]:
                    return None
                tokens.extend(word[1])
                index += len(word[0])
                continue
            match = re.match(r"\d+(?:\.\d+)?", tail)
            if match:
                tokens.append("number:" + format(Decimal(match[0]).normalize(), "f"))
                index += match.end()
                continue
            if text[index].isspace() or text[index] in ",.?!·ㆍ/()[]:~-→":
                index += 1
                continue
            return None
    except ValueError, InvalidOperation, OverflowError, OSError:
        return None
    return json_hash({"version": GUARD_VERSION, "operands": tokens}) if tokens else None


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items() if key not in _TRANSPORT_KEYS}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return normalize_text(value)
    return value


def context_hash(history: list[dict[str, Any]]) -> str | None:
    """Hash public content and call/result pairing; never persist the messages."""
    if not isinstance(history, list):
        return None
    messages: list[dict[str, Any]] = []
    calls: dict[str, int] = {}
    answered: set[str] = set()
    try:
        for message in history:
            if not isinstance(message, dict) or message.get("role") not in {
                "user",
                "assistant",
                "tool",
            }:
                return None
            role = message["role"]
            content = message.get("content")
            item: dict[str, Any] = {"role": role}
            if role == "tool":
                call_id = message.get("tool_call_id")
                if call_id not in calls or call_id in answered or not isinstance(content, str):
                    return None
                parsed = json.loads(content)
                if not isinstance(parsed, dict) or not public_payload(parsed):
                    return None
                item.update(call=calls[call_id], content=_clean(parsed))
                answered.add(call_id)
            else:
                if content is not None:
                    if not isinstance(content, str):
                        return None
                    private = (
                        requires_private_dialogue(content)
                        if role == "user"
                        else contains_sensitive_dialogue(content)
                    )
                    if private:
                        return None
                    item["content"] = normalize_text(content)
                if message.get("tool_calls"):
                    normalized: list[dict[str, Any]] = []
                    if role != "assistant" or not isinstance(message["tool_calls"], list):
                        return None
                    for call in message["tool_calls"]:
                        function = call["function"]
                        name = function["name"]
                        identifier = call["id"]
                        if (
                            name in _PRIVATE_TOOLS
                            or name not in ALLOWED_OPERATIONS
                            or identifier in calls
                        ):
                            return None
                        arguments = json.loads(function["arguments"])
                        if not isinstance(arguments, dict) or not public_payload(arguments):
                            return None
                        calls[identifier] = len(calls)
                        normalized.append(
                            {
                                "call": calls[identifier],
                                "name": name,
                                "arguments": _clean(arguments),
                            }
                        )
                    item["tool_calls"] = normalized
            messages.append(item)
        if set(calls) != answered:
            return None
        json.dumps(messages, allow_nan=False)
        return json_hash({"version": GUARD_VERSION, "messages": messages})
    except TypeError, ValueError, KeyError:
        return None
