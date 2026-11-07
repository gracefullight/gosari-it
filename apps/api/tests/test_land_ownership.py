import json
from secrets import token_hex
from types import SimpleNamespace

import pytest

from gosari.agent import build_public_spec
from gosari.agent.dialogue import public_spec_for_tool
from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.sources.land_ownership import (
    OWNERSHIP_URL,
    PARCEL_URL,
    classify_ownership,
    contains_point,
    query_land_ownership,
)

PNU = "5011010100100010000"
POLYGON = {
    "type": "Polygon",
    "coordinates": [[[126.5, 33.3], [126.6, 33.3], [126.6, 33.4], [126.5, 33.4], [126.5, 33.3]]],
}


def parcel(*features):
    return {
        "response": {"status": "OK", "result": {"featureCollection": {"features": list(features)}}}
    }


def feature(pnu=PNU, geometry=None):
    return {
        "properties": {"pnu": pnu, "ownerName": "PRIVATE_OWNER_CANARY"},
        "geometry": geometry or POLYGON,
    }


def ownership(name="국유지", code="02", **extra):
    return {
        "pnu": PNU,
        "posesnSeCode": code,
        "posesnSeCodeNm": name,
        "stdrYm": "2026-10",
        "lastUpdtDt": "2026-10-31",
        "ownerName": "PRIVATE_OWNER_CANARY",
        "ownerPhone": "010-9724-6381",
        **extra,
    }


@pytest.fixture
def run_source(monkeypatch):
    _saved = []
    _calls = []
    monkeypatch.setattr(
        "gosari.agent.analysis.get_evidence_store",
        lambda: SimpleNamespace(put=lambda payload: _saved.append(payload) or "ev-land"),
    )

    def run(responses, settings=None):
        responses = iter(responses)

        def get(gate, url, params, **kwargs):
            _calls.append((url, params))
            response = next(responses)
            if isinstance(response, Exception):
                raise response
            return response, "provider-raw-hash-not-stored"

        monkeypatch.setattr("gosari.sources.land_ownership.TransmissionGate.get_json", get)
        settings = settings or Settings(
            vworld_api_key=token_hex(24), external_requests_enabled=True
        )
        spec = public_spec_for_tool("land_ownership", {"location_id": "한라산남벽"})
        return query_land_ownership(spec, "land-test", settings)

    return run, _saved, _calls


@pytest.mark.parametrize(
    ("name", "classification", "private"),
    [
        ("개인", "private", True),
        ("국유지", "public", False),
        ("시, 도유지", "public", False),
        ("시, 군, 구유지", "public", False),
        ("법인", "unknown", None),
        ("종중", "unknown", None),
        ("외국인, 외국공공기관", "unknown", None),
        ("종교단체", "unknown", None),
    ],
)
def test_owner_classification_does_not_infer_private_for_corporate_or_public_possible_groups(
    name, classification, private
):
    assert classify_ownership(name) == (classification, private)


def test_exact_point_parcel_then_ownership_keeps_only_public_class_and_provenance(run_source):
    run, _saved, _calls = run_source
    result = run([parcel(feature()), {"possessions": {"field": [ownership()], "totalCount": "1"}}])
    assert result.data_status == "complete"
    assert _calls[0][0] == PARCEL_URL and _calls[1][0] == OWNERSHIP_URL
    assert _calls[0][1]["geomFilter"] == "POINT(126.533 33.3524)"
    assert _calls[0][1]["geometry"] == "true" and _calls[1][1]["pnu"] == PNU
    public = result.result["land_ownership"]
    assert public["location_name"] == "한라산남벽" and public["pnu"] == PNU
    assert public["ownership_class"] == "public" and public["is_private"] is False
    assert public["owner_type_name"] == "국유지" and public["reference_month"] == "2026-10"
    assert public["last_updated"] == "2026-10-31" and len(_saved[0]["source_manifests"]) == 2
    serialized = json.dumps([result.model_dump(mode="json"), _saved], ensure_ascii=False)
    assert "PRIVATE_OWNER_CANARY" not in serialized and "010-9724-6381" not in serialized
    assert "provider-raw-hash-not-stored" not in serialized
    assert all(
        "key" not in manifest["sanitized_parameters"] for manifest in _saved[0]["source_manifests"]
    )


def test_coordinates_are_always_server_resolved_and_unknown_personal_location_rejected():
    spec = build_public_spec(
        {"operation": "land_ownership", "source_ids": [], "location_id": "한라산남벽"}
    )
    assert spec["location_id"] == "aws:965" and spec["source_ids"] == [
        "vworld_cadastral",
        "vworld_ownership",
    ]
    assert spec["land_point"] == {"latitude": 33.3524, "longitude": 126.533}
    rebuilt = build_public_spec({**spec, "land_point": {"latitude": 1, "longitude": 2}})
    assert rebuilt["land_point"] == spec["land_point"]
    with pytest.raises(GosariError):
        public_spec_for_tool("land_ownership", {"location_id": "PRIVATE_HOME", "latitude": 33.1})
    with pytest.raises(GosariError):
        public_spec_for_tool("land_ownership", {"location_id": "PRIVATE_HOME"})


def test_point_containment_does_not_replace_coordinate_with_nearest_parcel(run_source):
    run, _saved, _calls = run_source
    distant = {
        "type": "Polygon",
        "coordinates": [
            [[126.1, 33.1], [126.2, 33.1], [126.2, 33.2], [126.1, 33.2], [126.1, 33.1]]
        ],
    }
    result = run([parcel(feature(geometry=distant))])
    assert result.data_status == "no_data" and result.result["reason"] == "PARCEL_NOT_FOUND"
    assert len(_calls) == 1 and result.result["land_ownership"]["pnu"] is None
    assert contains_point(POLYGON, 126.533, 33.3524)


def test_holes_and_multiple_parcels_do_not_produce_ownership_guesses(run_source):
    geometry = {
        "type": "Polygon",
        "coordinates": POLYGON["coordinates"]
        + [[[126.52, 33.34], [126.54, 33.34], [126.54, 33.36], [126.52, 33.36], [126.52, 33.34]]],
    }
    assert not contains_point(geometry, 126.533, 33.3524)
    run, _saved, _calls = run_source
    result = run([parcel(feature(), feature("5011010100100020000"))])
    assert result.data_status == "conflict" and result.result["reason"] == "AMBIGUOUS_PARCEL"
    assert len(_calls) == 1 and result.result["land_ownership"]["is_private"] is None


@pytest.mark.parametrize(
    "failure",
    [
        GosariError("UPSTREAM_FAILED"),
        {
            "response": {
                "status": "ERROR",
                "error": {"code": "INVALID_KEY", "text": "DO_NOT_EXPOSE_PROVIDER_HTML<script>"},
            }
        },
    ],
)
def test_api_auth_or_transport_failure_is_not_reported_as_no_data(run_source, failure):
    run, _saved, _calls = run_source
    result = run([failure])
    assert result.data_status == "unavailable" and result.errors
    assert "DO_NOT_EXPOSE" not in json.dumps(result.model_dump(mode="json"))


def test_missing_key_never_calls_source_and_is_unavailable(run_source, monkeypatch):
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    run, _saved, _calls = run_source
    result = run([], Settings(vworld_api_key=None, vworld_api_key_file=None))
    assert result.data_status == "unavailable" and result.result["reason"] == "VWORLD_KEY_MISSING"
    assert _calls == []


def test_empty_ownership_is_distinct_from_missing_parcel(run_source):
    run, _saved, _calls = run_source
    result = run([parcel(feature()), {"possessions": {"field": [], "totalCount": 0}}])
    assert result.data_status == "no_data" and result.result["reason"] == "OWNERSHIP_NOT_FOUND"
    assert result.result["land_ownership"]["pnu"] == PNU


def test_conflicting_classes_in_latest_period_remain_unknown(run_source):
    run, _saved, _calls = run_source
    result = run(
        [
            parcel(feature()),
            {"possessions": {"field": [ownership(), ownership("개인", "01")], "totalCount": 2}},
        ]
    )
    assert (
        result.data_status == "conflict" and result.result["land_ownership"]["is_private"] is None
    )


def test_newest_official_period_wins_without_overwriting_reference_date(run_source):
    run, _saved, _calls = run_source
    result = run(
        [
            parcel(feature()),
            {
                "possessions": {
                    "field": [ownership("개인", "01", stdrYm="2025-01"), ownership()],
                    "totalCount": 2,
                }
            },
        ]
    )
    assert (
        result.data_status == "complete"
        and result.result["land_ownership"]["reference_month"] == "2026-10"
    )
    assert result.result["land_ownership"]["is_private"] is False


def test_ownership_pages_are_bounded_and_incomplete_data_does_not_become_complete(run_source):
    run, _saved, _calls = run_source
    result = run(
        [
            parcel(feature()),
            {"possessions": {"field": [ownership()], "totalCount": 3000}},
            {"possessions": {"field": [ownership()], "totalCount": 3000}},
        ]
    )
    assert result.data_status == "partial" and len(_calls) == 3
    assert result.result["land_ownership"]["is_private"] is None


def test_parcel_result_truncation_and_wrong_geometry_crs_never_choose_an_approximate_owner(
    run_source,
):
    run, _saved, _calls = run_source
    payload = parcel(feature())
    payload["response"]["record"] = {"total": "101"}
    result = run([payload])
    assert result.data_status == "partial" and result.result["reason"] == "PARCEL_PAGES_INCOMPLETE"
    assert len(_calls) == 1
    with pytest.raises(GosariError):
        contains_point(
            {"type": "Polygon", "coordinates": [[[1000000, 1000000]] * 4]}, 126.533, 33.3524
        )
