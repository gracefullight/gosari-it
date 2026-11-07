"""Keep model payloads limited to fixed public terms, numbers and dates — never user prose."""

import re
from typing import Any


def public_model_data(value: Any) -> Any:
    """Allow numbers, fixed public terms and dates; never arbitrary user prose."""
    from gosari.agent import ALLOWED_OPERATIONS
    from gosari.sources.weather import JEJU_LOCATIONS

    terms = set(ALLOWED_OPERATIONS) | {
        "jeju_579",
        "jeju_578",
        "kma_aws",
        "kma_asos",
        "open_meteo",
        "at_settlement",
        "forestinfo",
        "retail_sample",
        "daily_rainfall",
        "average_temperature",
        "wind_speed",
        "low_rain",
        "mild_temperature",
        "low_wind",
        "common_valid_month_days",
        "count_positive_days",
        "day",
        "Asia/Seoul",
        "retail",
        "survey",
        "wholesale",
        "complete",
        "partial",
        "no_data",
        "fetched",
        "replay",
        "link",
        "forecast",
        "historical",
        "선흘",
        "제주",
        "제주(184)",
        "clear",
        "cloudy",
        "rain",
        "snow",
        "unknown",
        "kg",
        "g",
        "mm",
        "℃",
    }
    terms.update(str(part) for row in JEJU_LOCATIONS for part in row[:2])
    if isinstance(value, dict):
        return {
            str(key): public_model_data(item)
            for key, item in value.items()
            if re.fullmatch(r"[a-z_][a-z_0-9]*|\d{4}", str(key))
        }
    if isinstance(value, list):
        return [public_model_data(item) for item in value]
    if isinstance(value, str):
        return value if value in terms or re.fullmatch(r"[\d.,:T+Z /-]+", value) else None
    return value if value is None or isinstance(value, (bool, int, float)) else None
