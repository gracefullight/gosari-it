"""Official public station coordinates, separate from the map's representative areas."""

import hashlib
import json
import math
from functools import lru_cache
from importlib.resources import files
from typing import Any

from gosari.domain.errors import GosariError
from gosari.sources.weather import JEJU_LOCATIONS


@lru_cache(maxsize=1)
def station_catalog() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        files("gosari.sources")
        .joinpath("data", "jeju_stations_578.json")
        .read_text(encoding="utf-8")
    )
    rows = payload["stations"]
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != payload["normalized_sha256"] or len(rows) != 42:
        raise GosariError("UPSTREAM_SCHEMA_CHANGED")
    result = {}
    for row in rows:
        if row["id"] != f"aws:{row['code']}" or row["id"] in result:
            raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        for field, minimum, maximum in (("latitude", -90, 90), ("longitude", -180, 180)):
            value = row[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not minimum <= value <= maximum
            ):
                raise GosariError("UPSTREAM_SCHEMA_CHANGED")
        result[row["id"]] = {
            **row,
            "coordinate_source": "jeju_578",
            "coordinate_source_url": payload["source_url"],
            "coordinate_verified_at": payload["manifest"]["fetched_at"],
            "coordinate_content_hash": payload["manifest"]["content_hash"],
        }
    return result


def public_places() -> dict[str, tuple[str, str, float, float]]:
    result = {row[0]: row for row in JEJU_LOCATIONS}
    result["seonheul"] = ("seonheul", "선흘", 33.456, 126.705)
    result.update(
        {
            key: (key, row["name"], row["latitude"], row["longitude"])
            for key, row in station_catalog().items()
        }
    )
    return result


def resolve_public_place(identifier: str) -> tuple[str, str, float, float]:
    places = public_places()
    if identifier in places:
        return places[identifier]
    # Existing public area names retain their established coordinates.
    aliases = {row[1]: row for row in JEJU_LOCATIONS}
    aliases.update(
        {"제주": places["jeju"], "제주(184)": places["jeju"], "선흘": places["seonheul"]}
    )
    if identifier in aliases:
        return aliases[identifier]
    matched = [
        row for row in station_catalog().values() if identifier in (row["name"], row["code"])
    ]
    if len(matched) != 1:
        raise GosariError("STATION_AMBIGUOUS")
    return places[matched[0]["id"]]
