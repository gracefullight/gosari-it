"""공개 전송 게이트웨이 (SRS §4.1, §12.9).

개인 원문에서 필드를 제거한 복사본이 아니라 allowlist로 새 객체를 작성한다.
사용자 별칭·기록 ID·원문 대화·정확 개인 좌표는 여기에 들어올 수 없다.
"""

from typing import Any

from gosari.domain.errors import GosariError

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
    }
)

ALLOWED_OPERATIONS = frozenset(
    {
        "history_compare",
        "region_compare",
        "current_observation",
        "forecast_compare",
        "market_query",
        "survey_link",
        "retail_lookup",
        "station_search",
    }
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
    for selection in spec.get("station_selections", []):
        if set(selection) - {"source_id", "station_name", "station_code"}:
            raise GosariError("UNKNOWN_FIELD", {"fields": ["station_selections"]})
    return spec


def detect_personal_hint(text: str) -> bool:
    """개인혼입 의심은 임베딩 이전 우회 사유. 완전한 비개인성 보증이 아니다."""
    lowered = text.lower()
    if any(marker in lowered for marker in PERSONAL_HINT_MARKERS):
        return True
    import re

    return bool(re.search(r"01[016789]-?\d{3,4}-?\d{4}", text))
