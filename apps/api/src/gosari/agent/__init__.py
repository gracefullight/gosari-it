"""공개 전송 게이트웨이 (SRS §4.1, §12.9).

개인 원문에서 필드를 제거한 복사본이 아니라 allowlist로 새 객체를 작성한다.
사용자 별칭·기록 ID·원문 대화·정확 개인 좌표는 여기에 들어올 수 없다.
"""

from typing import Any

from gosari.domain.errors import GosariError

# 제주허브578 실제 공개 메타데이터 2026-11-07 확인. 강정의 두 코드도 보존한다.
PUBLIC_JEJU_STATIONS = (
    ("중문", "328"),
    ("산천단", "329"),
    ("대흘", "330"),
    ("강정", "685"),
    ("추자도", "724"),
    ("우도", "725"),
    ("마라도", "726"),
    ("유수암", "727"),
    ("선흘", "751"),
    ("서광", "752"),
    ("어리목", "753"),
    ("한림", "779"),
    ("제주남원", "780"),
    ("구좌", "781"),
    ("성판악", "782"),
    ("표선", "792"),
    ("대정", "793"),
    ("가파도", "855"),
    ("월정", "861"),
    ("송당", "862"),
    ("외도", "863"),
    ("오등", "865"),
    ("한라생태숲", "866"),
    ("삼각봉", "867"),
    ("사제비", "868"),
    ("영실", "869"),
    ("진달래밭", "870"),
    ("윗세오름", "871"),
    ("금악", "880"),
    ("새별오름", "883"),
    ("기상(과)", "884"),
    ("태풍센터", "885"),
    ("제주가시리", "890"),
    ("색달", "891"),
    ("성산수산", "892"),
    ("애월", "893"),
    ("한라산남벽", "965"),
    ("강정", "980"),
    ("제주", "184"),
    ("고산", "185"),
    ("성산", "188"),
    ("서귀포", "189"),
)

ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "operation",
        "source_ids",
        "station_selections",
        "years",
        "month_day_start",
        "month_day_end",
        "elements",
        "comparison_scope",
        "aggregation",
        "unit",
        "timezone",
        "polarity",
        "accumulation_window",
        "forecast_grid_id",
        "forecast_published_at",
        "forecast_target_times",
        "candidates",
        "preferred_elements",
        "price_channel",
        "market_ids",
        "item_codes",
        "fresh_or_dried",
        "grade",
        "package_weight_unit",
        "survey_region",
        "survey_stage",
        "survey_as_of",
        "product_id",
        "product_option",
        "origin_filter",
        "shipping_basis",
        "coupon_basis",
        "settlement_date",
        "settlement_date_end",
        "package_code",
    }
)

ALLOWED_OPERATIONS = frozenset(
    {
        "history_compare",
        "region_compare",
        "current_observation",
        "forecast_compare",
        "outing_compare",
        "market_query",
        "survey_link",
        "retail_lookup",
        "station_search",
    }
)

OUT_OF_SCOPE_PATTERNS = (
    "채취해도 되",
    "꺾어도 되",
    "들어가도 되",
    "출입 가능",
    "허가",
    "먹어도 되",
    "식용",
    "독초",
    "명당",
    "어디에 많",
    "얼마나 날까",
    "수확량",
    "시세 예측",
    "오를까",
)

PERSONAL_HINT_MARKERS = (
    "우리 어머니",
    "우리 엄마",
    "우리 가족",
    "내 수첩",
    "나의 기록",
    "그곳",
    "그때",
    "어제 우리",
)


def build_public_spec(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = set(payload) - ALLOWED_FIELDS - {"safe_text"}
    if unknown:
        raise GosariError("UNKNOWN_FIELD", {"fields": sorted(unknown)})
    operation = payload.get("operation")
    if operation not in ALLOWED_OPERATIONS:
        raise GosariError("INVALID_INPUT", {"fields": ["operation"]})
    spec: dict[str, Any] = {k: v for k, v in payload.items() if k in ALLOWED_FIELDS}
    spec["schema_version"] = "query-v1"
    allowed_sources = {
        "jeju_579",
        "jeju_578",
        "kma_aws",
        "kma_asos",
        "kma_vilage",
        "open_meteo",
        "at_settlement",
        "forestinfo",
        "retail_sample",
        "tamnao",
        "oasis",
    }
    sources = spec.get("source_ids", [])
    if not isinstance(sources, list) or any(source not in allowed_sources for source in sources):
        raise GosariError("INVALID_INPUT", {"fields": ["source_ids"]})
    if "candidates" in spec:
        from datetime import date

        from gosari.sources.weather import JEJU_LOCATIONS

        public = {str(row[0]): row for row in JEJU_LOCATIONS}
        public.update({str(row[1]): row for row in JEJU_LOCATIONS})
        public["제주"] = public["jeju"]
        public["제주(184)"] = public["jeju"]
        public["선흘"] = ("seonheul", "선흘", 33.456, 126.705)
        candidates = spec["candidates"]
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= 12:
            raise GosariError("INVALID_INPUT", {"fields": ["candidates"]})
        resolved = []
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise GosariError("INVALID_INPUT", {"fields": ["candidates"]})
            region = public.get(
                str(candidate.get("location_id") or candidate.get("station_name") or "")
            )
            if region is None:
                region = ("unknown", "선택 지역", None, None)
            selected_date = candidate.get("date") or candidate.get("target_date")
            try:
                selected_date = date.fromisoformat(str(selected_date)).isoformat()
            except ValueError:
                raise GosariError("INVALID_INPUT", {"fields": ["candidates.date"]}) from None
            hour = str(candidate.get("time_slot") or candidate.get("target_time_window") or "12:00")
            hour = {"오전": "09:00", "오후": "15:00"}.get(hour, hour)
            import re

            if not re.fullmatch(r"(?:[01]\d|2[0-3]):00", hour):
                raise GosariError("INVALID_INPUT", {"fields": ["candidates.time_slot"]})
            resolved.append(
                {
                    "candidate_id": f"cand-{index + 1}",
                    "location_id": region[0],
                    "station_name": region[1],
                    "latitude": region[2],
                    "longitude": region[3],
                    "target_date": selected_date,
                    "target_time_window": hour,
                }
            )
        spec["candidates"] = resolved
    for selection in spec.get("station_selections", []):
        if set(selection) - {"source_id", "station_name", "station_code", "station_id"}:
            raise GosariError("UNKNOWN_FIELD", {"fields": ["station_selections"]})
        source = selection.get("source_id")
        name = selection.get("station_name")
        code = selection.get("station_id") or selection.get("station_code")
        valid: list[tuple[str, str]]
        if source in ("jeju_578", "jeju_579"):
            valid = [(n, c) for n, c in PUBLIC_JEJU_STATIONS if n == name]
        elif source == "kma_asos":
            valid = [
                (n, c)
                for n, c in PUBLIC_JEJU_STATIONS
                if c in ("184", "185", "188", "189") and name in (n, f"{n}({c})")
            ]
        elif source == "kma_aws":
            from gosari.config import get_settings
            from gosari.sources.replay import load_current_observations

            rows, _ = load_current_observations(get_settings().resolved_fixtures_dir)
            valid = [
                (row["station_name"], row["station_code"])
                for row in rows
                if row["station_name"] == name
            ]
        else:
            valid = []
        if not valid or (code is not None and str(code) not in {c for _, c in valid}):
            raise GosariError("STATION_AMBIGUOUS")

    def contains_private(value: Any) -> bool:
        if isinstance(value, str):
            return detect_personal_hint(value)
        if isinstance(value, dict):
            return any(contains_private(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_private(item) for item in value)
        return False

    if contains_private(spec):
        raise GosariError("INVALID_INPUT", {"reason": "PUBLIC_CONDITIONS_REQUIRED"})
    if isinstance(spec.get("preferred_elements"), list):
        aliases = {
            "daily_rainfall": "low_rain",
            "average_temperature": "mild_temperature",
            "wind_speed": "low_wind",
        }
        spec["preferred_elements"] = [
            aliases.get(value, value) if isinstance(value, str) else value
            for value in spec["preferred_elements"]
        ]
    import re

    public_enums = {
        "preferred_elements": {"low_rain", "mild_temperature", "low_wind"},
        "elements": {
            "daily_rainfall",
            "average_temperature",
            "wind_speed",
            "temperature_c",
            "precipitation_probability",
            "precipitation",
            "rain_1h_mm",
        },
        "fresh_or_dried": {"fresh", "dried", "생고사리", "건고사리", "전체"},
        "price_channel": {"wholesale", "survey", "retail"},
        "timezone": {"Asia/Seoul"},
        "polarity": {"positive", "negative"},
        "unit": {"mm", "℃", "C", "kg", "g", "원", "KRW", "day", "days", "%"},
        "comparison_scope": {
            "common_valid_month_days",
            "common_actual_dates",
            "common_valid_dates",
            "common_month_days",
            "full_period",
            "common_period",
        },
        "aggregation": {"count_positive_days", "positive_day_count", "sum", "mean", "average"},
        "survey_stage": {"생산지", "도매지", "소비지", "producer", "wholesale", "consumer"},
        "survey_region": {"제주", "제주도", "제주특별자치도"},
        "shipping_basis": {"included", "excluded", "unknown", "포함", "별도", "미확인"},
        "coupon_basis": {
            "standard",
            "conditional",
            "included",
            "excluded",
            "unknown",
            "일반가",
            "쿠폰가",
        },
    }
    patterns = {
        "month_day_start": r"\d{2}-\d{2}",
        "month_day_end": r"\d{2}-\d{2}",
        "settlement_date": r"\d{4}-\d{2}-\d{2}",
        "settlement_date_end": r"\d{4}-\d{2}-\d{2}",
        "survey_as_of": r"\d{4}-\d{2}-\d{2}",
        "forecast_grid_id": r"\d{1,3},\d{1,3}",
        "forecast_published_at": r"[\d:T+Z /-]+",
        "forecast_target_times": r"[\d:T+Z /-]+",
        "market_ids": r"\d{6}",
        "package_code": r"\d{1,8}",
        "grade": r"\d{1,8}|특|상|중|하",
        "accumulation_window": r"\d+(?:m|h|d)|day",
        "package_weight_unit": r"\d+(?:\.\d+)?\s*(?:kg|g|톤|개|봉|봉지|박스|상자|단|묶음)",
    }
    for field, choices in public_enums.items():
        value = spec.get(field)
        values = value if isinstance(value, list) else [value]
        if any(
            item is not None and item != "" and (not isinstance(item, str) or item not in choices)
            for item in values
        ):
            raise GosariError("INVALID_INPUT", {"fields": [field]})
    for field, pattern in patterns.items():
        value = spec.get(field)
        values = value if isinstance(value, list) else [value]
        if any(
            item is not None
            and item != ""
            and (not isinstance(item, str) or not re.fullmatch(pattern, item))
            for item in values
        ):
            raise GosariError("INVALID_INPUT", {"fields": [field]})
    if spec.get("origin_filter"):
        origins = {
            "제주",
            "제주산",
            "제주도",
            "제주특별자치도",
            "제주시",
            "서귀포시",
            "국내산",
            "수입산",
        }
        if not isinstance(spec["origin_filter"], str) or spec["origin_filter"] not in origins:
            raise GosariError("INVALID_INPUT", {"fields": ["origin_filter"]})
    if spec.get("product_option") or spec.get("product_id"):
        from urllib.parse import parse_qs, urlsplit

        from gosari.config import get_settings
        from gosari.sources.replay import load_retail_products

        products, _ = load_retail_products(get_settings().resolved_fixtures_dir)
        options = {p.get("optionLabel") or f"{p['weight_g']}g" for p in products}
        identifiers = {
            str(parse_qs(urlsplit(p["url"]).query).get("prdtNum", [""])[0])
            or urlsplit(p["url"]).path.rsplit("/", 1)[-1]
            for p in products
        }
        if (
            spec.get("product_option")
            and (
                not isinstance(spec["product_option"], str) or spec["product_option"] not in options
            )
        ) or (
            spec.get("product_id")
            and (not isinstance(spec["product_id"], str) or spec["product_id"] not in identifiers)
        ):
            raise GosariError("INVALID_INPUT", {"fields": ["product_option", "product_id"]})
    if "years" in spec and (
        not isinstance(spec["years"], list)
        or any(
            not isinstance(year, int) or isinstance(year, bool) or not 1800 <= year <= 2200
            for year in spec["years"]
        )
    ):
        raise GosariError("INVALID_INPUT", {"fields": ["years"]})
    if "item_codes" in spec:
        codes = spec["item_codes"]
        if (
            not isinstance(codes, dict)
            or set(codes) - {"large", "middle", "small"}
            or any(
                not isinstance(value, str) or not re.fullmatch(r"\d{1,8}", value)
                for value in codes.values()
            )
        ):
            raise GosariError("INVALID_INPUT", {"fields": ["item_codes"]})
    return spec


def detect_personal_hint(text: str) -> bool:
    """개인혼입 의심은 임베딩 이전 우회 사유. 완전한 비개인성 보증이 아니다."""
    lowered = text.lower()
    if any(marker in lowered for marker in PERSONAL_HINT_MARKERS):
        return True
    import re

    return bool(re.search(r"01[016789]-?\d{3,4}-?\d{4}", text))


def detect_out_of_scope(text: str) -> bool:
    """SRS FR-CORE-007: 식용·출입·채취 허가·명당·수확량·시세 예측 요청 감지."""
    lowered = text.lower()
    return any(pattern in lowered for pattern in OUT_OF_SCOPE_PATTERNS)
