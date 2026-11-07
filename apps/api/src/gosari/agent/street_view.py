"""Google's documented, keyless Street View link for a resolved public place."""

import math
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlencode


def _field(location: object, name: str) -> object:
    if isinstance(location, Mapping):
        return cast(object, location.get(name))
    return cast(object, getattr(location, name, None))


def _coordinate(value: object, limit: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("A resolved public coordinate is required")
    try:
        coordinate = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid public coordinate") from exc
    if not math.isfinite(coordinate) or not -limit <= coordinate <= limit:
        raise ValueError("Invalid public coordinate")
    return coordinate


def build_street_view_links(location: object) -> list[dict[str, str]]:
    """Accept only a location already resolved by the public-place catalog.

    This constructs an outbound link; it does not fetch images or claim panorama
    availability. Google chooses the available panorama closest to the viewpoint.
    """
    name = _field(location, "name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A resolved public place name is required")
    latitude = _coordinate(_field(location, "latitude"), 90)
    longitude = _coordinate(_field(location, "longitude"), 180)
    viewpoint = f"{latitude:.8f}".rstrip("0").rstrip(".")
    viewpoint += "," + f"{longitude:.8f}".rstrip("0").rstrip(".")
    url = "https://www.google.com/maps/@?" + urlencode(
        {"api": "1", "map_action": "pano", "viewpoint": viewpoint}
    )
    return [
        {
            "provider": "google",
            "label": "Google 스트리트뷰",
            "url": url,
            "location_name": name.strip(),
        }
    ]
