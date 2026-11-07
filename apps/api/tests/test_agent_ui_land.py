from gosari.agent.ui import build_ui, restore_ui, selection_schema
from gosari.domain.envelope import ResultEnvelope, UiElement

SCOPE = {
    "operation": "land_ownership",
    "source_ids": ["vworld_cadastral", "vworld_ownership"],
    "location_id": "aws:965",
}


def test_land_component_is_model_selectable_and_preserves_only_result_references():
    envelope = ResultEnvelope(
        request_id="land-request",
        data_status="complete",
        requested_scope=SCOPE,
        result={"land_ownership": {"ownership_class": "public", "is_private": False}},
    )
    spec, values, source = build_ui(
        {"land_ownership": envelope},
        {"land_ownership": SCOPE},
        {
            "components": [{"component": "LandOwnershipResults", "operation": "land_ownership"}],
            "actions": [],
        },
    )
    assert source == "model"
    assert spec.elements["view_1"] == UiElement(
        type="LandOwnershipResults", props={"resultRef": "result_1"}
    )
    assert values["result_1"].result["land_ownership"]["is_private"] is False
    schema = selection_schema()
    assert (
        "LandOwnershipResults"
        in schema["properties"]["components"]["items"]["properties"]["component"]["enum"]
    )
    restored, _ = restore_ui(
        spec.model_dump(mode="json"),
        {key: value.model_dump(mode="json") for key, value in values.items()},
    )
    assert restored == spec


def test_land_fallback_does_not_offer_an_unimplemented_weather_or_price_condition_form():
    envelope = ResultEnvelope(
        request_id="land-request",
        data_status="no_data",
        result={"land_ownership": {"is_private": None}},
    )
    spec, _, _ = build_ui({"land_ownership": envelope}, {"land_ownership": SCOPE})
    assert spec.elements["view_1"].type == "LandOwnershipResults"
    assert "actions" not in spec.elements
