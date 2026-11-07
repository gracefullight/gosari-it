from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from gosari.agent.street_view import build_street_view_links


def test_uses_the_official_google_viewpoint_url_without_a_key_or_network():
    location = {"id": "aws:965", "name": "한라산남벽", "latitude": 33.3524, "longitude": 126.5330}
    (link,) = build_street_view_links(location)
    parsed = urlsplit(link["url"])
    assert (parsed.scheme, parsed.netloc, parsed.path) == ("https", "www.google.com", "/maps/@")
    assert parse_qs(parsed.query) == {
        "api": ["1"],
        "map_action": ["pano"],
        "viewpoint": ["33.3524,126.533"],
    }
    assert link["location_name"] == "한라산남벽"
    assert link["provider"] == "google"
    assert link["label"] == "Google 스트리트뷰"
    assert build_street_view_links(location) == [link]


def test_accepts_a_resolved_place_object_and_preserves_coordinate_order():
    (link,) = build_street_view_links(
        SimpleNamespace(name="공개 지점", latitude=-33.1, longitude=151.2)
    )
    assert parse_qs(urlsplit(link["url"]).query)["viewpoint"] == ["-33.1,151.2"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("latitude", None),
        ("latitude", True),
        ("latitude", "nan"),
        ("latitude", float("inf")),
        ("latitude", 91),
        ("longitude", -181),
        ("longitude", "javascript:alert(1)"),
        ("name", ""),
    ],
)
def test_rejects_missing_or_invalid_resolved_values(field, value):
    location = {"name": "한라산남벽", "latitude": 33.3524, "longitude": 126.533}
    location[field] = value
    with pytest.raises(ValueError):
        build_street_view_links(location)
