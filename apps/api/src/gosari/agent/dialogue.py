"""Model-directed public conversation. Tool validation is independent of intent routing."""

import copy
import json
import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gosari.agent import PUBLIC_JEJU_STATIONS, build_public_spec
from gosari.agent.llm import LlmClient, runtime_system_prompt
from gosari.agent.prompts import DIALOGUE_SYSTEM_PROMPT as SYSTEM
from gosari.agent.runtime import LABELS, compact_result, fallback
from gosari.agent.ui import COMPONENTS, build_ui, selection_schema
from gosari.domain.envelope import ResultEnvelope, UiElement
from gosari.domain.errors import GosariError
from gosari.sources.locations import public_places, resolve_public_place, station_catalog
from gosari.sources.observations import kma_grid
from gosari.sources.weather import korea_today

STATION_NAMES = list(dict.fromkeys(name for name, _ in PUBLIC_JEJU_STATIONS))
STATION_EXTRA: dict[str, Any] = {"enum": STATION_NAMES}
STATION_ITEMS_EXTRA: dict[str, Any] = {"items": {"type": "string", "enum": STATION_NAMES}}
PLACES = public_places()
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
MONTH_DAY_PATTERN = r"^\d{2}-\d{2}$"
TIME_PATTERN = r"^(?:[01]\d|2[0-3]):00$"


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoryArgs(Args):
    station_name: str = Field(json_schema_extra=STATION_EXTRA)
    station_code: str | None = None
    years: list[int] = Field(min_length=2, max_length=8)
    month_day_start: str = Field(pattern=MONTH_DAY_PATTERN)
    month_day_end: str = Field(pattern=MONTH_DAY_PATTERN)
    elements: list[Literal["daily_rainfall", "average_temperature"]] = Field(
        default_factory=lambda: ["daily_rainfall", "average_temperature"]
    )


class RegionArgs(Args):
    station_names: list[str] = Field(
        min_length=2,
        max_length=12,
        json_schema_extra=STATION_ITEMS_EXTRA,
    )
    years: list[int] = Field(min_length=1, max_length=8)
    month_day_start: str = Field(pattern=MONTH_DAY_PATTERN)
    month_day_end: str = Field(pattern=MONTH_DAY_PATTERN)
    elements: list[Literal["daily_rainfall", "average_temperature"]] = Field(
        default_factory=lambda: ["daily_rainfall", "average_temperature"]
    )


class Candidate(Args):
    location_id: str = Field(description="공개 카탈로그의 지역 ID 또는 관측 지점 ID·이름")
    date: str = Field(pattern=DATE_PATTERN)
    time_slot: str = Field(pattern=TIME_PATTERN)


class OutingArgs(Args):
    candidates: list[Candidate] = Field(min_length=1, max_length=12)
    preferred_elements: list[Literal["low_rain", "mild_temperature", "low_wind"]] = Field(
        default_factory=lambda: ["low_rain", "mild_temperature", "low_wind"]
    )


class ForecastArgs(Args):
    location_id: str = Field(description="공개 카탈로그의 지역 ID 또는 관측 지점 ID·이름")
    forecast_published_at: str = Field(description="확정된 공식 발표시각 ISO8601 한국시간")
    forecast_target_times: list[str] = Field(min_length=1, max_length=24)


class PriceFilters(Args):
    fresh_or_dried: Literal["생고사리", "건고사리", "fresh", "dried", "전체"] | None = None
    package_weight_unit: str | None = Field(
        default=None,
        description="사용자가 명시한 중량. 예: 100g, 200g, 0.1 kg. 단위까지 보존하세요.",
    )
    product_option: str | None = Field(
        default=None,
        description="공식 옵션명을 아는 경우만 지정. 중량은 package_weight_unit을 사용하세요.",
    )


class RetailArgs(PriceFilters):
    providers: list[Literal["tamnao", "oasis"]] = Field(default_factory=list)
    product_id: str | None = None


class SurveyArgs(Args):
    fresh_or_dried: Literal["생고사리", "건고사리", "fresh", "dried", "전체"] | None = None
    survey_stage: Literal["생산지", "도매지", "소비지"] | None = None


class MarketArgs(Args):
    settlement_date: str = Field(pattern=DATE_PATTERN)
    settlement_date_end: str | None = Field(default=None, pattern=DATE_PATTERN)
    market_ids: list[str] = Field(
        description="서울가락=110001, 부산엄궁=210001. 코드를 묻지 말고 시장명을 물으세요.",
        min_length=1,
        max_length=12,
        json_schema_extra={"items": {"type": "string", "pattern": "^\\d{6}$"}},
    )
    fresh_or_dried: Literal["생고사리", "건고사리", "fresh", "dried", "전체"] | None = None
    grade: str | None = None
    package_code: str | None = None
    package_weight_unit: str | None = None
    origin_filter: (
        Literal[
            "제주", "제주산", "제주도", "제주특별자치도", "제주시", "서귀포시", "국내산", "수입산"
        ]
        | None
    ) = None


class PersonalSearchArgs(Args):
    kind: Literal["region", "notebook", "share", "contact", "all"]
    query: str = Field(
        default="",
        max_length=400,
        description=(
            "기록 내용에서 찾을 구체적인 키워드. 등록한 지역·스팟이 어디인지 묻거나 "
            "전체 기록을 찾을 때는 kind로 종류를 고르고 query는 빈 문자열로 보내세요."
        ),
    )


class PersonalFormArgs(Args):
    feature: Literal["notebook", "region_compare", "share"]


class StreetViewArgs(Args):
    location_id: str = Field(description="공개 카탈로그의 지역 ID 또는 관측 지점 ID·이름")


class LandOwnershipArgs(Args):
    location_id: str = Field(description="소유 구분을 확인할 공개 카탈로그 지점 ID·이름")


LINK_TOOLS = {"open_street_view": StreetViewArgs}
LINK_LABELS = {"open_street_view": "거리뷰 링크 만들기"}
PRIVATE_TOOLS = {
    "search_personal_records": PersonalSearchArgs,
    "open_personal_form": PersonalFormArgs,
}
PRIVATE_LABELS = {"search_personal_records": "내 기록 검색", "open_personal_form": "기록 작성 준비"}


ARG_MODELS: dict[str, type[Args]] = {
    "current_observation": Args,
    "station_search": Args,
    "history_compare": HistoryArgs,
    "region_compare": RegionArgs,
    "outing_compare": OutingArgs,
    "forecast_compare": ForecastArgs,
    "market_query": MarketArgs,
    "survey_link": SurveyArgs,
    "retail_lookup": RetailArgs,
    "land_ownership": LandOwnershipArgs,
}
SOURCES = {
    "current_observation": ["kma_aws"],
    "station_search": ["jeju_578"],
    "history_compare": ["jeju_579"],
    "region_compare": ["jeju_579"],
    "outing_compare": ["kma_vilage", "open_meteo"],
    "forecast_compare": ["kma_vilage"],
    "market_query": ["at_settlement"],
    "survey_link": ["forestinfo"],
    "retail_lookup": ["retail_sample"],
    "land_ownership": ["vworld_cadastral", "vworld_ownership"],
}


def dialogue_tools() -> list[dict[str, Any]]:
    definitions = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": LABELS[name],
                "parameters": model.model_json_schema(),
                "strict": False,
            },
        }
        for name, model in sorted(ARG_MODELS.items())
    ]
    for name, model in {**PRIVATE_TOOLS, **LINK_TOOLS}.items():
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "거리뷰 링크를 만들어 사용자가 클릭해 열 수 있도록 안내합니다."
                    if name == "open_street_view"
                    else PRIVATE_LABELS[name],
                    "parameters": model.model_json_schema(),
                    "strict": False,
                },
            }
        )
    definitions.append(
        {
            "type": "function",
            "function": {
                "name": "respond",
                "description": "대화에 답하거나 필요한 조건을 묻고 결과 UI를 선택합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "claims": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "fact_id": {"type": "string"},
                                    "quote": {"type": "string"},
                                },
                                "required": ["fact_id", "quote"],
                                "additionalProperties": False,
                            },
                        },
                        "ui": selection_schema(),
                    },
                    "required": ["text", "claims", "ui"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
    )
    return definitions


def public_spec_for_tool(name: str, arguments: Any) -> dict[str, Any]:
    if name not in ARG_MODELS or not isinstance(arguments, dict):
        raise GosariError("INVALID_INPUT", {"fields": ["tool"]})
    try:
        args = ARG_MODELS[name].model_validate(arguments).model_dump(exclude_none=True)
    except ValidationError as error:
        fields = sorted({str(row["loc"][0]) for row in error.errors() if row["loc"]})
        raise GosariError("INVALID_INPUT", {"fields": fields}) from None
    spec: dict[str, Any] = {"operation": name, "source_ids": list(SOURCES[name])}
    if name in ("history_compare", "region_compare"):
        names = args.pop("station_names", None) or [args.pop("station_name")]
        station_code = args.pop("station_code", None)
        if len(set(names)) != len(names):
            raise GosariError("STATION_AMBIGUOUS")
        for station in names:
            choices = [(n, code) for n, code in PUBLIC_JEJU_STATIONS if n == station]
            if not choices or (len(choices) > 1 and station_code is None):
                raise GosariError("STATION_AMBIGUOUS")
        if len(set(args["years"])) != len(args["years"]):
            raise GosariError("INVALID_INPUT", {"fields": ["years"]})
        for year in args["years"]:
            for field in ("month_day_start", "month_day_end"):
                try:
                    date.fromisoformat(f"{year}-{args[field]}")
                except ValueError:
                    raise GosariError("INVALID_INPUT", {"fields": [field]}) from None
        if args["month_day_start"] > args["month_day_end"]:
            raise GosariError("INVALID_INPUT", {"fields": ["month_day_start", "month_day_end"]})
        spec["station_selections"] = [
            {
                "source_id": "jeju_579",
                "station_name": station,
                **({"station_code": station_code} if station_code else {}),
            }
            for station in names
        ]
        spec.update(
            comparison_scope="common_actual_dates"
            if name == "region_compare"
            else "common_valid_month_days",
            timezone="Asia/Seoul",
            **args,
        )
    elif name == "outing_compare":
        for item in args["candidates"]:
            item["location_id"] = resolve_public_place(item["location_id"])[0]
            try:
                date.fromisoformat(item["date"])
            except ValueError:
                raise GosariError("INVALID_INPUT", {"fields": ["candidates.date"]}) from None
        spec.update(args)
    elif name == "forecast_compare":
        from datetime import datetime
        from zoneinfo import ZoneInfo

        place = resolve_public_place(args["location_id"])
        try:
            published = datetime.fromisoformat(args["forecast_published_at"])
            if len(args["forecast_published_at"]) < 16:
                raise ValueError
            published = (
                published.replace(tzinfo=ZoneInfo("Asia/Seoul"))
                if published.tzinfo is None
                else published.astimezone(ZoneInfo("Asia/Seoul"))
            )
            targets = []
            for target in args["forecast_target_times"]:
                if len(target) < 16:
                    raise ValueError
                instant = datetime.fromisoformat(target)
                instant = (
                    instant.replace(tzinfo=ZoneInfo("Asia/Seoul"))
                    if instant.tzinfo is None
                    else instant.astimezone(ZoneInfo("Asia/Seoul"))
                )
                targets.append(instant.strftime("%Y%m%d %H%M"))
        except ValueError:
            raise GosariError(
                "INVALID_INPUT", {"fields": ["forecast_published_at", "forecast_target_times"]}
            ) from None
        nx, ny = kma_grid(place[2], place[3])
        spec.update(
            forecast_grid_id=f"{nx},{ny}",
            forecast_published_at=published.isoformat(timespec="minutes"),
            forecast_target_times=targets,
        )
        if place[0] in station_catalog():
            station = station_catalog()[place[0]]
            spec["station_selections"] = [
                {
                    "source_id": "jeju_578",
                    "station_name": station["name"],
                    "station_code": station["code"],
                }
            ]
    elif name == "market_query":
        try:
            start = date.fromisoformat(args["settlement_date"])
            end = date.fromisoformat(args.get("settlement_date_end") or args["settlement_date"])
        except ValueError:
            raise GosariError("INVALID_INPUT", {"fields": ["settlement_date"]}) from None
        if start > end or end > korea_today():
            raise GosariError(
                "INVALID_INPUT", {"fields": ["settlement_date", "settlement_date_end"]}
            )
        spec.update(args, price_channel="wholesale", settlement_date_end=end.isoformat())
    elif name == "land_ownership":
        spec["location_id"] = resolve_public_place(args["location_id"])[0]
    elif name == "retail_lookup":
        providers = args.pop("providers", [])
        spec["source_ids"] += list(dict.fromkeys(providers))
        spec.update(args, price_channel="retail")
    elif name == "survey_link":
        spec.update(args, price_channel="survey", survey_region="제주")
    return build_public_spec(spec)


_HTML = re.compile(r"<[^>]+>|javascript:", re.IGNORECASE)
_PHONE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _public_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    if isinstance(value, str) and (
        _HTML.search(value) or _PHONE.search(value) or _EMAIL.search(value)
    ):
        return None
    return value


def _valid_fact(entry: dict[str, Any]) -> bool:
    return (
        entry.get("value") is not None
        and all(isinstance(entry.get(key), str) for key in ("label", "unit", "as_of"))
        and isinstance(entry.get("anchors", []), list)
        and all(isinstance(anchor, str) for anchor in entry.get("anchors", []))
        and isinstance(entry.get("anchor_groups", []), list)
        and all(
            isinstance(group, list) and all(isinstance(alias, str) for alias in group)
            for group in entry.get("anchor_groups", [])
        )
    )


def _seed_facts(messages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    facts: dict[str, dict[str, Any]] = {}
    for message in messages:
        if message.get("role") != "tool" or not isinstance(message.get("content"), str):
            continue
        try:
            payload = json.loads(message["content"])
        except ValueError:
            continue
        found = payload.get("facts", {}) if isinstance(payload, dict) else {}
        if not isinstance(found, dict):
            continue
        for key, value in found.items():
            if not re.fullmatch(r"(?:f\d+|private_count_\d+)", str(key)) or not isinstance(
                value, dict
            ):
                continue
            if not {"value", "label", "unit", "as_of"} <= set(value):
                continue
            sanitized = _public_value(value)
            if _valid_fact(sanitized):
                facts[str(key)] = sanitized
    return facts


def normalize_dialogue_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep real tool pairs and one final answer, omitting respond's protocol copies."""
    accepted = copy.deepcopy(
        [message for message in messages if message.get("role") in ("user", "assistant", "tool")]
    )
    respond_ids = {
        str(call.get("id") or "")
        for message in accepted
        for call in message.get("tool_calls", [])
        if call.get("function", {}).get("name") == "respond"
    }
    normalized = []
    for message in accepted:
        if message.get("role") == "tool" and str(message.get("tool_call_id")) in respond_ids:
            continue
        if message.get("role") == "assistant" and message.get("tool_calls"):
            calls = [
                call
                for call in message["tool_calls"]
                if call.get("function", {}).get("name") != "respond"
            ]
            if calls:
                message["tool_calls"] = calls
            else:
                message.pop("tool_calls", None)
                if not message.get("content"):
                    continue
        if (
            normalized
            and message.get("role") == "assistant"
            and not message.get("tool_calls")
            and normalized[-1].get("role") == "assistant"
            and not normalized[-1].get("tool_calls")
            and normalized[-1].get("content") == message.get("content")
        ):
            continue
        normalized.append(message)
    return normalized


def _outing_ranking(output: ResultEnvelope) -> list[dict[str, Any]]:
    rows = output.result.get("candidates", [])
    ranked = [
        row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("rank"), int)
        and not isinstance(row.get("rank"), bool)
    ]
    ranked.sort(key=lambda row: row["rank"])
    if [row["rank"] for row in ranked] != list(range(1, len(ranked) + 1)):
        return []
    declared = output.result.get("ranked_candidate_ids")
    if declared is not None and declared != [row.get("candidate_id") for row in ranked]:
        return []
    return ranked


_RECOMMEND_WORDS = (
    "추천",
    "권해",
    "권합니다",
    "가장 좋",
    "제일 좋",
    "가장 적합",
    "가장 무난",
    "균형이 좋",
    "1순위",
    "고르세요",
    "선택하세요",
    "가세요",
)
_ALTERNATIVE_WORDS = ("대안", "않", "피하", "어렵", "바꾸", "바꾸면", "라면", "다면", "비추")


def outing_recommendation_conflict(
    text: str, records: list[tuple[str, dict[str, Any], ResultEnvelope]]
) -> str | None:
    """Return the rank=1 station when a recommending sentence names only a lower-ranked one."""
    for name, _, output in reversed(records):
        if name != "outing_compare":
            continue
        ranked = _outing_ranking(output)
        if not ranked:
            return None
        winner = str(ranked[0].get("station_name") or "")
        others = {str(row.get("station_name") or "") for row in ranked[1:]} - {winner, ""}
        if not winner or not others:
            return None
        for sentence in re.split(r"(?<=[.!?。])\s+|\n+", text):
            if not any(word in sentence for word in _RECOMMEND_WORDS):
                continue
            if any(word in sentence for word in _ALTERNATIVE_WORDS) or winner in sentence:
                continue
            if any(other in sentence for other in others):
                return winner
        return None
    return None


def _compact_tool(
    output: ResultEnvelope, name: str, spec: dict[str, Any], facts: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    compact = compact_result(output, facts)
    if name == "land_ownership":
        compact["land_ownership"] = output.result.get("land_ownership", {})

    def add(
        value: Any, label: str, unit: str, as_of: str = "", anchors: list[str] | None = None
    ) -> None:
        if value is None or isinstance(value, bool):
            return
        try:
            if not Decimal(str(value)).is_finite():
                return
        except InvalidOperation:
            return
        facts[f"f{len(facts) + 1}"] = {
            "value": value,
            "label": label,
            "unit": unit,
            "as_of": as_of,
            "anchors": anchors or [],
        }

    public_names = set(STATION_NAMES) | {row[1] for row in PLACES.values()}
    for row in [*output.result.get("stations", []), *output.result.get("candidates", [])]:
        if not isinstance(row, dict):
            continue
        place = next(
            (place for place in PLACES.values() if row.get("station_name") == place[1]), None
        )
        if not place or (row.get("latitude"), row.get("longitude")) != (place[2], place[3]):
            continue
        for field, axis in (("latitude", "위도"), ("longitude", "경도")):
            add(row[field], f"{place[1]} {axis}", "°", anchors=[place[1]])
    if name in ("market_query", "retail_lookup", "survey_link"):
        cards = output.result.get("price_cards") or output.result.get("sample_cards") or []
        add(len(cards), "조회한 가격 자료 수", "건")
    if name == "station_search":
        stations = output.result.get("stations", [])
        catalog = station_catalog()
        compact["stations"] = [
            {
                "name": row.get("station_name"),
                **(
                    {"location_id": f"aws:{row['station_code']}"}
                    if f"aws:{row.get('station_code')}" in catalog
                    and catalog[f"aws:{row['station_code']}"]["name"] == row["station_name"]
                    else {}
                ),
                **({"code": str(row["station_code"])} if row.get("station_code") else {}),
                **(
                    {"altitude_m": row["altitude_m"]}
                    if isinstance(row.get("altitude_m"), (int, float))
                    and not isinstance(row["altitude_m"], bool)
                    and 0 <= row["altitude_m"] <= 2000
                    else {"altitude_m": catalog[f"aws:{row['station_code']}"]["altitude_m"]}
                    if f"aws:{row.get('station_code')}" in catalog
                    and catalog[f"aws:{row['station_code']}"]["name"] == row["station_name"]
                    else {}
                ),
            }
            for row in stations
            if isinstance(row, dict) and row.get("station_name") in public_names
        ]
        add(len(compact["stations"]), "공개 관측 지점 수", "곳")
    if name == "region_compare":
        for element, field, label, unit in (
            ("daily_rainfall", "positive_days", "비가 온 날", "일"),
            ("average_temperature", "average", "평균기온", "℃"),
        ):
            for station, values in output.result.get(element, {}).get("per_station", {}).items():
                if station in public_names:
                    add(values.get(field), f"{station} {label}", unit, anchors=[station])
    if name == "forecast_compare":
        place = next(
            (
                row
                for row in PLACES.values()
                if ",".join(str(value) for value in kma_grid(row[2], row[3]))
                == spec.get("forecast_grid_id")
            ),
            None,
        )
        selections = spec.get("station_selections", [])
        region = selections[0]["station_name"] if selections else place[1] if place else "제주"
        for row in output.result.get("forecast", [])[:24]:
            metadata = {
                "TMP": ("기온", "℃"),
                "TMN": ("최저기온", "℃"),
                "TMX": ("최고기온", "℃"),
                "POP": ("강수확률", "%"),
                "WSD": ("풍속", "m/s"),
            }.get(row.get("category"))
            if metadata:
                add(
                    row.get("value"),
                    f"{region} {row.get('target_at', '')} {metadata[0]}",
                    metadata[1],
                    str(row.get("target_at") or ""),
                    [region],
                )
    for row in output.result.get("stations", [])[:12]:
        station = str(row.get("station_name") or "")
        if station in public_names:
            add(
                row.get("wind_speed_ms"),
                f"{station} 풍속",
                "m/s",
                str(row.get("observation_time") or ""),
                [station],
            )
    for row in output.result.get("candidates", [])[:4]:
        station = str(row.get("station_name") or "")
        if station in public_names:
            add(
                row.get("weather", {}).get("wind_speed_kmh"),
                f"{station} {row.get('target_date', '')} {row.get('target_time_window', '')} 풍속",
                "km/h",
                anchors=[station],
            )
    if name == "outing_compare":
        ranked = _outing_ranking(output)
        compact["actual_ranking"] = [
            {
                **{
                    key: row.get(key)
                    for key in (
                        "candidate_id",
                        "location_id",
                        "station_name",
                        "target_date",
                        "target_time_window",
                        "rank",
                    )
                },
                "weather": {
                    key: row.get("weather", {}).get(key)
                    for key in (
                        "temperature_c",
                        "precipitation_probability",
                        "wind_speed_kmh",
                    )
                },
            }
            for row in ranked
        ]
        compact["preferred_elements"] = list(spec.get("preferred_elements", []))
        compact["ranked_candidate_ids"] = [row.get("candidate_id") for row in ranked]
        compact["recommended_candidate_id"] = ranked[0].get("candidate_id") if ranked else None
        for row in ranked:
            station = str(row.get("station_name") or "")
            add(
                row["rank"],
                f"{station} 날씨 비교 순위",
                "위",
                str(row.get("target_date") or ""),
                [station],
            )
    compact["facts"] = facts
    return compact


def dialogue_answer_supported(text: str, claims: Any, facts: dict[str, dict[str, Any]]) -> bool:
    """Validate measurements against their subject; dates and proposed counts are context."""
    if (
        not text.strip()
        or not isinstance(claims, list)
        or _HTML.search(text)
        or _PHONE.search(text)
        or _EMAIL.search(text)
    ):
        return False
    claimed = [
        facts[claim["fact_id"]]
        for claim in claims
        if isinstance(claim, dict) and claim.get("fact_id") in facts
    ]
    masked = [False] * len(text)

    def cover(start: int, end: int) -> None:
        masked[start:end] = [True] * (end - start)

    for match in re.finditer(r"(위도|경도)\s*:?\s*(\d{1,3}(?:\.\d+)?)\s*°?", text):
        possible = [
            fact
            for fact in claimed
            if fact.get("unit") == "°"
            and match[1] in str(fact.get("label"))
            and str(fact.get("value")) == match[2]
        ]
        places = [place[1] for place in PLACES.values() if place[1] in text[: match.start()]]
        if not possible or (places and not any(places[-1] in str(f["label"]) for f in possible)):
            return False
        cover(*match.span())

    known_dates = set()
    known_times = set()
    context = " ".join(
        str(fact.get(key, "")) for fact in facts.values() for key in ("value", "label", "as_of")
    )
    known_dates.update(re.findall(r"\d{4}-\d{2}-\d{2}", context))
    known_times.update(re.findall(r"(?:[01]\d|2[0-3]):[0-5]\d", context))
    for match in re.finditer(r"\d{4}-\d{2}-\d{2}", text):
        if match.group() not in known_dates:
            return False
        prefix = text[max(0, match.start() - 12) : match.start()]
        for relative, key in (
            ("내일", "clock_tomorrow"),
            ("모레", "clock_after_tomorrow"),
            ("오늘", "clock_today"),
        ):
            if relative in prefix and match.group() != str(facts.get(key, {}).get("value")):
                return False
        cover(*match.span())
    for match in re.finditer(r"(\d{1,2})월\s*(\d{1,2})일", text):
        dates = {
            value
            for value in known_dates
            if value[5:] == f"{int(match[1]):02d}-{int(match[2]):02d}"
        }
        prefix = text[max(0, match.start() - 12) : match.start()]
        for relative, key in (
            ("내일", "clock_tomorrow"),
            ("모레", "clock_after_tomorrow"),
            ("오늘", "clock_today"),
        ):
            if relative in prefix:
                dates &= {str(facts.get(key, {}).get("value"))}
        if not dates:
            return False
        cover(*match.span())
    for match in re.finditer(r"(?:(오전|오후)\s*)?(\d{1,2})시|(?:[01]\d|2[0-3]):[0-5]\d", text):
        if match[2]:
            hour = int(match[2])
            if match[1]:
                hour = hour % 12 + (12 if match[1] == "오후" else 0)
            value = f"{hour:02d}:00"
        else:
            value = match.group()
        if value not in known_times:
            return False
        cover(*match.span())
    for match in re.finditer(r"(\d+)\s*[~-]\s*(\d+)\s*(?:곳|개|후보)", text):
        if 1 <= int(match[1]) <= int(match[2]) <= 12 and any(
            word in text[max(0, match.start() - 35) : match.end() + 35]
            for word in ("추천", "대표", "골라", "선택", "후보")
        ):
            cover(*match.span())
    for match in re.finditer(r"\d+(?:\.\d+)?\s*(?:kg|g)(?![a-z/])", text):
        if re.sub(r"\s", "", match.group()) in re.sub(r"\s", "", context):
            cover(*match.span())
    for match in re.finditer(
        r"(\d[\d,]*(?:\.\d+)?)\s*[~-]\s*(\d[\d,]*(?:\.\d+)?)\s*(원/kg|원|%|℃|km/h|m/s)", text
    ):
        for endpoint in (match[1], match[2]):
            if not any(
                str(fact.get("unit")) == match[3]
                and Decimal(str(fact.get("value"))) == Decimal(endpoint.replace(",", ""))
                for fact in facts.values()
                if re.fullmatch(r"\d+(?:\.\d+)?", str(fact.get("value")))
            ):
                return False
        cover(match.start(1), match.end(1))
    actors = (
        set(STATION_NAMES)
        | {place[1] for place in PLACES.values()}
        | {"탐나오", "오아시스", "오아시스마켓", "산림조합"}
    )
    for match in re.finditer(
        r"(\d[\d,]*(?:\.\d+)?)\s*(℃|°C|km/h|m/s|원/kg|원|%|mm|일|위|건|곳|개|명)", text
    ):
        if all(masked[match.start() : match.end()]):
            continue
        value, unit = Decimal(match[1].replace(",", "")), match[2].replace("°C", "℃")
        possible = []
        for fact in facts.values():
            try:
                same = Decimal(str(fact.get("value"))) == value
            except InvalidOperation:
                same = False
            if same and (
                fact.get("unit") == unit
                or (
                    unit in ("건", "곳", "개", "명")
                    and fact.get("unit") in ("건", "곳", "개", "명")
                )
            ):
                possible.append(fact)
        if not possible or (
            unit not in ("건", "곳") and not any(fact in claimed for fact in possible)
        ):
            return False
        prefix = text[: match.start()]
        relevant_actors = (
            {"탐나오", "오아시스", "오아시스마켓", "산림조합"} if unit.startswith("원") else actors
        )
        present = [
            (prefix.rfind(actor), actor)
            for actor in relevant_actors
            if prefix.rfind(actor) >= max(0, len(prefix) - 220)
        ]
        recent = max(present, default=(-1, ""))[1]
        sentence_breaks = list(re.finditer(r"(?<!\d)[.!?。\n]|[.!?。\n](?!\d)", prefix))
        clause = prefix[sentence_breaks[-1].end() :] if sentence_breaks else prefix
        shared = any(word in clause[-35:] for word in ("모두", "둘 다", "두 곳"))
        subjects = [actor for _, actor in present] if shared else ([recent] if recent else [])
        for subject in subjects:
            if not any(subject in str(fact.get("label")) for fact in possible):
                return False
        if unit.startswith("원"):
            weights = list(re.finditer(r"\d+(?:\.\d+)?\s*(?:kg|g)(?![a-z/])", prefix))
            price_subject = prefix[weights[-1].start() :] if weights else prefix[-120:]
            kind = (
                "배송"
                if "배송" in prefix[-14:]
                else "쿠폰"
                if "쿠폰" in prefix[-14:]
                else "kg 환산"
                if unit == "원/kg"
                else ""
            )
            possible = [
                fact
                for fact in possible
                if (
                    kind in str(fact.get("label"))
                    if kind
                    else not any(
                        label in str(fact.get("label")) for label in ("배송", "쿠폰", "kg 환산")
                    )
                )
            ]
            possible = [
                fact
                for fact in possible
                if all(
                    any(
                        re.sub(r"\s", "", alias).lower() in re.sub(r"\s", "", price_subject).lower()
                        for alias in group
                    )
                    for group in fact.get("anchor_groups", [])
                    if any(re.search(r"\d\s*(?:kg|g)", alias) for alias in group)
                )
            ]
            if not possible:
                return False
        cover(*match.span())
    return all(
        all(masked[match.start() : match.end()])
        for match in re.finditer(r"\d+(?:,\d{3})*(?:\.\d+)?", text)
    )


def _context_fallback(
    records: list[tuple[str, dict[str, Any], ResultEnvelope]], facts: dict[str, dict[str, Any]]
) -> str:
    if not records:
        return "필요한 조건을 조금 더 알려주세요."
    name, spec, output = records[-1]
    label = LABELS[name].removesuffix(" 조회").removesuffix(" 확인")
    day = spec.get("settlement_date")
    prefix = f"{day} " if day else ""
    if output.data_status == "no_data" or output.result.get("matched_sample_count") == 0:
        return f"{prefix}선택한 조건에 맞는 {label} 자료를 찾지 못했습니다."
    if output.data_status in ("unavailable", "conflict"):
        return f"{prefix}선택한 조건의 {label} 자료를 확정하지 못했습니다."
    if name == "outing_compare":
        ranked = _outing_ranking(output)
        if ranked:
            winner = ranked[0]
            return f"날씨 조건으로 비교한 후보의 1위는 {winner.get('station_name')}입니다."
        return "후보 순위를 확인하지 못해 추천을 확정하지 못했습니다."
    if facts:
        text = fallback(facts).replace("기온는", "기온은").replace("풍속는", "풍속은")
        return text + (
            " 일부 자료는 확인하지 못했습니다." if output.data_status == "partial" else ""
        )
    if output.data_status == "partial":
        return f"{prefix}{label} 자료의 일부만 확인했습니다."
    return f"{prefix}{label} 결과를 확인했습니다."


def _render_ui(
    records: list[tuple[str, dict[str, Any], ResultEnvelope]],
    selection: Any,
    emit: Callable[[str, dict[str, Any]], None],
) -> None:
    if not records:
        return
    latest: dict[str, ResultEnvelope] = {}
    scopes: dict[str, dict[str, Any]] = {}
    for name, spec, output in records:
        latest[name], scopes[name] = output, spec
    ui, bound, source = build_ui(latest, scopes, selection)
    if ui is None:
        return
    # The fixed UI enum names an operation. Preserve additional argument sets as
    # separate authoritative result references rather than overwriting their cards.
    for name, spec, output in records:
        if spec == scopes[name]:
            continue
        ref = f"result_{len(bound) + 1}"
        bound[ref] = output.model_copy(update={"requested_scope": spec}, deep=True)
        view = UiElement(type=COMPONENTS[name][0], props={"resultRef": ref})
        for element in ui.elements.values():
            original = bound.get(str(element.props.get("resultRef")))
            if original and original.requested_scope.get("operation") == name:
                view = element.model_copy(update={"props": {"resultRef": ref}}, deep=True)
                break
        node = f"view_extra_{len(bound)}"
        ui.elements[node] = view
        root = ui.elements[ui.root]
        index = root.children.index("actions") if "actions" in root.children else len(root.children)
        root.children.insert(index, node)
        if source == "model":
            source = "model_with_fallback"
    emit(
        "ui_spec",
        {
            "spec": ui.model_dump(mode="json"),
            "results": {key: value.model_dump(mode="json") for key, value in bound.items()},
            "selection_source": source,
        },
    )


def run_dialogue(
    client: LlmClient,
    messages: list[dict[str, Any]],
    execute: Callable[[dict[str, Any]], ResultEnvelope],
    emit: Callable[[str, dict[str, Any]], None],
    checkpoint: Callable[[], None],
    *,
    max_steps: int = 8,
) -> tuple[ResultEnvelope | None, str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Only server-authoritative public history is accepted by the coordinator."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    history = normalize_dialogue_history(messages)
    facts = _seed_facts(history)
    cursor = max((int(key[1:]) for key in facts if key.startswith("f")), default=0)
    records: list[tuple[str, dict[str, Any], ResultEnvelope]] = []
    turn_facts: dict[str, dict[str, Any]] = {}
    memo: dict[str, tuple[ResultEnvelope | None, dict[str, Any]]] = {}
    specifications: list[dict[str, Any]] = []
    private_results: list[dict[str, Any]] = []
    rank_corrections = 0
    definitions = dialogue_tools()

    def complete(
        text: str, selection: Any = None, replacement: bool = False
    ) -> tuple[ResultEnvelope | None, str, list[dict[str, Any]], list[dict[str, Any]]]:
        if (
            not history
            or history[-1].get("role") != "assistant"
            or history[-1].get("content") != text
        ):
            history.append({"role": "assistant", "content": text})
        _render_ui(records, selection, emit)
        emit("assistant_completed", {"text": text, "replacement": replacement})
        return (
            (records[-1][2] if records else None),
            text,
            normalize_dialogue_history(history),
            specifications,
        )

    for _ in range(max_steps):
        checkpoint()
        current = datetime.now(ZoneInfo("Asia/Seoul"))
        clock = {
            "clock_today": {
                "value": current.date().isoformat(),
                "label": "오늘 날짜",
                "unit": "",
                "as_of": "",
                "anchors": list[str](),
            },
            "clock_time": {
                "value": current.strftime("%H:%M"),
                "label": "한국 현재 시각(24시간)",
                "unit": "",
                "as_of": current.date().isoformat(),
                "anchors": list[str](),
            },
        }
        for offset, key in ((1, "clock_tomorrow"), (2, "clock_after_tomorrow")):
            clock[key] = {
                "value": (current.date() + timedelta(days=offset)).isoformat(),
                "label": "날짜 확인",
                "unit": "",
                "as_of": "",
                "anchors": list[str](),
            }
        # Static tools + system prompt first, the per-second clock last: the provider
        # prompt cache matches prefixes at message boundaries, so a changing clock
        # before the history would defeat caching on every call.
        request = [
            {
                "role": "system",
                "content": SYSTEM
                + "\n공개 대표 지역: "
                + json.dumps(
                    {identifier: place[1] for identifier, place in PLACES.items()},
                    ensure_ascii=False,
                ),
            },
            *history,
            {
                "role": "system",
                "content": runtime_system_prompt(
                    "현재 시계 facts: " + json.dumps(clock, ensure_ascii=False), current
                ),
            },
        ]
        try:
            message = client.stream_turn(
                request,
                definitions,
                lambda text: emit("assistant_delta", {"text": text, "provisional": True}),
                checkpoint,
                tool_choice="auto",
            )
        except GosariError as error:
            checkpoint()
            _render_ui(records, None, emit)
            raise error
        history.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            text = str(message.get("content") or "")
            return complete(text)
        has_queries = any(call.get("function", {}).get("name") != "respond" for call in calls)
        response: tuple[str, Any, bool] | None = None
        for call in calls:
            checkpoint()
            call_id = str(call.get("id") or "")
            function = call.get("function", {})
            name = str(function.get("name") or "")
            payload: dict[str, Any]
            try:
                args = json.loads(function.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise GosariError("INVALID_INPUT")
                if name == "respond":
                    if has_queries:
                        payload = {
                            "error": "RESULTS_REQUIRED",
                            "message": "조회 결과를 읽은 뒤 다시 답해주세요.",
                        }
                    else:
                        text = str(args.get("text") or "")
                        winner = outing_recommendation_conflict(text, records)
                        if winner and rank_corrections < 2:
                            rank_corrections += 1
                            payload = {
                                "error": "RANK_MISMATCH",
                                "message": (
                                    f"actual_ranking의 rank=1 후보는 {winner}입니다. "
                                    f"{winner}를 먼저 추천하고 다른 후보의 장점은 우선순위를 "
                                    "바꿨을 때의 대안으로만 설명한 뒤 다시 답해주세요."
                                ),
                            }
                        elif winner:
                            text = _context_fallback(records, facts)
                            response = text, args.get("ui"), True
                            payload = {"status": "responded", "accepted_text": text}
                        else:
                            response = text, args.get("ui"), False
                            payload = {"status": "responded", "accepted_text": text}
                else:
                    personal = name in PRIVATE_TOOLS
                    linked = name in LINK_TOOLS
                    if personal:
                        validated = PRIVATE_TOOLS[name].model_validate(args).model_dump()
                        if (
                            name == "search_personal_records"
                            and _public_value(validated["query"]) is None
                        ):
                            raise GosariError("POLICY_BLOCKED")
                        spec = {"operation": name, **validated}
                    elif linked:
                        validated = LINK_TOOLS[name].model_validate(args).model_dump()
                        spec = {
                            "operation": name,
                            "location_id": resolve_public_place(validated["location_id"])[0],
                        }
                    else:
                        spec = public_spec_for_tool(name, args)
                    key = json.dumps(spec, ensure_ascii=False, sort_keys=True)
                    if key in memo:
                        _, payload = memo[key]
                    elif len(memo) >= max_steps:
                        payload = {
                            "error": "BUDGET_EXCEEDED",
                            "message": "확인한 자료로 답해주세요.",
                        }
                    else:
                        emit(
                            "tool_started",
                            {
                                "tool_call_id": call_id,
                                "name": name,
                                "label": {**LABELS, **PRIVATE_LABELS, **LINK_LABELS}[name],
                                "conditions": {
                                    key: value for key, value in spec.items() if key != "query"
                                }
                                if personal
                                else spec,
                            },
                        )
                        try:
                            output = execute(spec)
                            checkpoint()
                        except GosariError as error:
                            if (
                                error.code in ("JOB_DEADLINE_EXCEEDED", "ACTION_NOT_ALLOWED")
                                or error.extra.get("reason") == "CANCELLED"
                            ):
                                raise
                            checkpoint()
                            payload = {
                                "error": error.code,
                                "message": error.safe_message,
                                "conditions": spec,
                            }
                            memo[key] = None, payload
                            emit(
                                "tool_failed",
                                {
                                    "tool_call_id": call_id,
                                    "name": name,
                                    "code": error.code,
                                    "message": error.safe_message,
                                },
                            )
                        else:
                            if linked:
                                payload = {
                                    "status": "link_ready",
                                    "user_click_required": True,
                                    "street_view_links": output.result.get("street_view_links", []),
                                }
                                memo[key] = output, payload
                                emit(
                                    "tool_completed",
                                    {
                                        "tool_call_id": call_id,
                                        "name": name,
                                        "summary": LINK_LABELS[name],
                                        "result": output.model_dump(mode="json"),
                                    },
                                )
                                history.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call_id,
                                        "content": json.dumps(payload, ensure_ascii=False),
                                    }
                                )
                                continue
                            if personal:
                                if name == "search_personal_records":
                                    count = output.result.get("count")
                                    kinds = output.result.get("kinds", [])
                                    if (
                                        not isinstance(count, int)
                                        or isinstance(count, bool)
                                        or count < 0
                                        or not isinstance(kinds, list)
                                        or any(
                                            kind not in ("region", "notebook", "share", "contact")
                                            for kind in kinds
                                        )
                                    ):
                                        raise GosariError("UPSTREAM_SCHEMA_CHANGED")
                                    metadata = {"count": count, "kinds": kinds}
                                    counter = (
                                        max(
                                            (
                                                int(key.rsplit("_", 1)[1])
                                                for key in facts
                                                if key.startswith("private_count_")
                                            ),
                                            default=0,
                                        )
                                        + 1
                                    )
                                    private_facts = {
                                        f"private_count_{counter}": {
                                            "value": count,
                                            "label": "개인 조회 결과 수",
                                            "unit": "건",
                                            "as_of": "",
                                            "anchors": list[str](),
                                        }
                                    }
                                    facts.update(private_facts)
                                    payload = {**metadata, "facts": private_facts}
                                    emit(
                                        "personal_search",
                                        {
                                            "query": output.result.get("ui_query", spec["query"]),
                                            "kind": spec["kind"],
                                            "count": count,
                                        },
                                    )
                                else:
                                    metadata = {"feature": spec["feature"]}
                                    payload = {**metadata, "opened": True}
                                    emit("personal_form", metadata)
                                private_results.append(metadata)
                                memo[key] = None, payload
                                emit(
                                    "tool_completed",
                                    {
                                        "tool_call_id": call_id,
                                        "name": name,
                                        "summary": PRIVATE_LABELS[name],
                                        **metadata,
                                    },
                                )
                                history.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call_id,
                                        "content": json.dumps(
                                            payload, ensure_ascii=False, sort_keys=True
                                        ),
                                    }
                                )
                                continue
                            records.append((name, spec, output))
                            specifications.append(spec)
                            new_facts: dict[str, dict[str, Any]] = {}
                            compact = _compact_tool(output, name, spec, new_facts)
                            renamed: dict[str, dict[str, Any]] = {}
                            for entry in new_facts.values():
                                cursor += 1
                                renamed[f"f{cursor}"] = entry
                            renamed = {
                                key: entry
                                for key, entry in _public_value(renamed).items()
                                if _valid_fact(entry)
                            }
                            facts.update(renamed)
                            turn_facts.update(renamed)
                            compact["facts"] = renamed
                            compact["operation"] = name
                            compact["conditions"] = spec
                            payload = _public_value(compact)
                            memo[key] = output, payload
                            emit(
                                "tool_completed",
                                {
                                    "tool_call_id": call_id,
                                    "name": name,
                                    "summary": LABELS[name],
                                    "result": output.model_dump(mode="json"),
                                },
                            )
            except (GosariError, ValueError, TypeError) as error:
                if isinstance(error, GosariError) and (
                    error.code in ("JOB_DEADLINE_EXCEEDED", "ACTION_NOT_ALLOWED")
                    or error.extra.get("reason") == "CANCELLED"
                ):
                    raise
                payload = {
                    "error": error.code if isinstance(error, GosariError) else "INVALID_INPUT",
                    "message": "조회 조건을 확인하고 수정하거나 사용자에게 질문해주세요.",
                }
                if isinstance(error, GosariError) and error.extra.get("fields"):
                    payload["fields"] = error.extra["fields"]
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                }
            )
        if response is not None:
            return complete(response[0], response[1], replacement=response[2])
    _render_ui(records, None, emit)
    raise GosariError("BUDGET_EXCEEDED")
