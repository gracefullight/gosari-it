import copy

import pytest

from gosari.agent.coordinator import Coordinator
from gosari.agent.runtime import run_agent, tools
from gosari.agent.ui import build_ui, restore_ui
from gosari.config import Settings
from gosari.domain import CacheResolution
from gosari.domain.envelope import ResultEnvelope
from gosari.sessions import Session

PRICE = {
    "operation": "retail_lookup",
    "source_ids": ["retail_sample", "tamnao"],
    "package_weight_unit": "100 g",
    "fresh_or_dried": "건고사리",
}
WEATHER = {"operation": "current_observation", "source_ids": ["kma_aws"]}


def result(operation="retail_lookup"):
    return ResultEnvelope(
        request_id="old",
        data_status="complete",
        source_mode="replay",
        requested_scope=PRICE if operation == "retail_lookup" else WEATHER,
        result={"trusted_value": 17000},
        evidence_ids=["ev-public"],
    )


def selected(component="PriceResults", operation="retail_lookup"):
    return {
        "components": [{"component": component, "operation": operation}],
        "actions": [
            {"action": "adjust_conditions", "operation": operation},
            {"action": "save_to_notebook", "operation": operation},
        ],
    }


def test_model_selects_components_and_actions_without_generating_values():
    spec, results, source = build_ui(
        {"retail_lookup": result()}, {"retail_lookup": PRICE}, selected()
    )
    assert source == "model"
    assert spec.elements["view_1"].type == "PriceResults"
    assert spec.elements["view_1"].props == {"resultRef": "result_1"}
    assert results["result_1"].result == {"trusted_value": 17000}
    assert results["result_1"].requested_scope["package_weight_unit"] == "100 g"
    assert [item["id"] for item in spec.elements["actions"].props["actions"]] == [
        "adjust_conditions",
        "save_to_notebook",
    ]
    assert "17000" not in spec.model_dump_json()


def test_second_tool_result_cannot_be_omitted_by_model_selection():
    spec, results, source = build_ui(
        {"retail_lookup": result(), "current_observation": result("current_observation")},
        {"retail_lookup": PRICE, "current_observation": WEATHER},
        selected(),
    )
    assert len(results) == 2
    assert source == "model_with_fallback"
    assert {spec.elements[key].type for key in ("view_1", "view_2")} == {
        "PriceResults",
        "WeatherComparison",
    }
    assert {spec.elements[key].props["resultRef"] for key in ("view_1", "view_2")} == set(results)


def test_multi_result_actions_fit_the_web_catalog_and_keep_all_results():
    scopes = {
        "market_query": {"operation": "market_query", "source_ids": ["at_settlement"]},
        "survey_link": {"operation": "survey_link", "source_ids": ["forestinfo"]},
        "retail_lookup": PRICE,
    }
    selection = {
        "components": [
            {"component": "PriceResults", "operation": operation} for operation in scopes
        ],
        "actions": [
            {"action": action, "operation": operation}
            for operation in scopes
            for action in (
                "adjust_conditions",
                "save_to_notebook",
                "show_price_table",
                "compare_packages",
            )
        ],
    }
    spec, results, source = build_ui(
        {operation: result() for operation in scopes}, scopes, selection
    )
    assert source == "model_with_fallback"
    assert len(spec.elements["actions"].props["actions"]) == 8
    assert len(results) == 3
    restored, restored_results = restore_ui(
        spec.model_dump(mode="json"),
        {key: value.model_dump(mode="json") for key, value in results.items()},
    )
    assert restored == spec
    assert len(restored_results) == 3


@pytest.mark.parametrize(
    "invalid",
    [
        {"components": [{"component": "script", "operation": "retail_lookup"}], "actions": []},
        {
            "components": [{"component": "PriceResults", "operation": "retail_lookup", "price": 1}],
            "actions": [],
        },
        {
            "components": [],
            "actions": [{"action": "delete_notebook", "operation": "retail_lookup"}],
        },
        {"components": [], "actions": [], "html": "<script />"},
    ],
)
def test_invalid_model_ui_cannot_add_code_or_private_actions(invalid):
    spec, results, source = build_ui({"retail_lookup": result()}, {"retail_lookup": PRICE}, invalid)
    assert source == "fallback"
    assert spec.elements["view_1"].type == "PriceResults"
    assert set(spec.elements["view_1"].props) == {"resultRef"}
    assert results["result_1"].result["trusted_value"] == 17000


def test_incompatible_component_or_action_falls_back_to_valid_public_view():
    spec, _, source = build_ui(
        {"retail_lookup": result()},
        {"retail_lookup": PRICE},
        {
            "components": [{"component": "WeatherMap", "operation": "retail_lookup"}],
            "actions": [{"action": "show_weather_map", "operation": "retail_lookup"}],
        },
    )
    assert source == "fallback"
    assert spec.elements["view_1"].type == "PriceResults"
    assert "actions" not in spec.elements


@pytest.mark.parametrize(
    "corruption",
    ["script", "extra_props", "dangling", "private_scope", "hidden_result", "action_route"],
)
def test_cached_flat_spec_is_revalidated(corruption):
    spec, results, _ = build_ui({"retail_lookup": result()}, {"retail_lookup": PRICE}, selected())
    raw = spec.model_dump(mode="json")
    data = {key: value.model_dump(mode="json") for key, value in results.items()}
    if corruption == "script":
        raw["elements"]["view_1"]["type"] = "script"
    elif corruption == "extra_props":
        raw["elements"]["view_1"]["props"]["html"] = "<script />"
    elif corruption == "dangling":
        raw["elements"]["view_1"]["props"]["resultRef"] = "missing"
    elif corruption == "private_scope":
        data["result_1"]["requested_scope"]["contact_id"] = "private"
    elif corruption == "hidden_result":
        data["result_2"] = copy.deepcopy(data["result_1"])
    else:
        raw["elements"]["actions"]["props"]["actions"][0]["url"] = "javascript:alert(1)"
    assert restore_ui(raw, data) == (None, {})


def test_legacy_cache_reconstructs_ui_before_any_model_call(monkeypatch):
    coordinator = Coordinator(Settings())
    cached = result().model_dump(mode="json")
    cached["assistant_text"] = "공개 결과"
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup",
        lambda *a, **k: (
            CacheResolution.EXACT_HIT,
            {"answer": cached, "evidence_ids": ["ev-public"]},
        ),
    )
    monkeypatch.setattr(
        coordinator, "_execute_agent_turn", lambda *a: pytest.fail("cache hit called model")
    )
    job = coordinator.run_job(Session(Settings()), PRICE)
    assert job.stage.value == "completed"
    assert job.ui_spec.elements["view_1"].type == "PriceResults"
    assert job.ui_results["result_1"].requested_scope["package_weight_unit"] == "100 g"
    assert any(event.event_type == "ui_spec" for event in job.events)
    assert job.model_usage["calls"] == 0
    assert (
        next(event for event in job.events if event.event_type == "ui_spec").payload[
            "selection_source"
        ]
        == "fallback"
    )


def test_cache_restores_model_selected_ui_and_rebinds_request_id_without_model(monkeypatch):
    coordinator = Coordinator(Settings())
    ui, results, _ = build_ui({"retail_lookup": result()}, {"retail_lookup": PRICE}, selected())
    cached = result().model_dump(mode="json")
    cached.update(
        ui_spec=ui.model_dump(mode="json"),
        ui_results={key: value.model_dump(mode="json") for key, value in results.items()},
    )
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup",
        lambda *a, **k: (CacheResolution.EXACT_HIT, {"answer": cached, "evidence_ids": []}),
    )
    monkeypatch.setattr(
        coordinator, "_execute_agent_turn", lambda *a: pytest.fail("cache hit called model")
    )
    job = coordinator.run_job(Session(Settings()), PRICE)
    assert job.ui_spec == ui
    assert job.ui_results["result_1"].request_id == job.request_id
    assert job.ui_results["result_1"].requested_scope["fresh_or_dried"] == "건고사리"
    assert job.model_usage["calls"] == 0


def test_runtime_uses_real_model_ui_selection_and_emits_bound_spec():
    events = []
    messages = iter(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "t", "function": {"name": "retail_lookup", "arguments": "{}"}}
                ],
            },
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "r",
                        "function": {
                            "name": "respond",
                            "arguments": __import__("json").dumps(
                                {"text": "확인했어요.", "claims": [], "ui": selected()}
                            ),
                        },
                    }
                ],
            },
        ]
    )

    class Model:
        def stream_turn(self, *args, **kwargs):
            return next(messages)

    run_agent(
        Model(),
        {"retail_lookup": PRICE},
        lambda spec: result(),
        lambda name, payload: events.append((name, payload)),
        lambda: None,
    )
    ui = next(payload for name, payload in events if name == "ui_spec")
    assert ui["selection_source"] == "model"
    assert ui["spec"]["elements"]["view_1"]["type"] == "PriceResults"
    assert ui["results"]["result_1"]["result"]["trusted_value"] == 17000
    respond = next(tool for tool in tools() if tool["function"]["name"] == "respond")
    assert "ui" in respond["function"]["parameters"]["required"]
    assert all(
        "price" not in key
        for key in respond["function"]["parameters"]["properties"]["ui"]["properties"]
    )


def test_response_cache_roundtrip_keeps_model_ui_public_conditions_and_model_zero(monkeypatch):
    import json
    from contextlib import nullcontext
    from secrets import token_hex

    settings = Settings(openai_api_key=token_hex(24), external_requests_enabled=True)
    coordinator = Coordinator(settings)
    cache, model_calls, source_calls = {}, [], []
    selection = selected()
    messages = iter(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "t", "function": {"name": "retail_lookup", "arguments": "{}"}}
                ],
            },
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "r",
                        "function": {
                            "name": "respond",
                            "arguments": json.dumps(
                                {"text": "확인했어요.", "claims": [], "ui": selection}
                            ),
                        },
                    }
                ],
            },
        ]
    )

    def lookup(spec, text, **kwargs):
        value = cache.get(text)
        return (CacheResolution.EXACT_HIT, value) if value else (CacheResolution.MISS, None)

    def store(spec, text, answer, evidence, **kwargs):
        cache[text] = {"answer": copy.deepcopy(answer), "evidence_ids": list(evidence)}

    def turn(*args, **kwargs):
        model_calls.append(1)
        return next(messages)

    def execute(engine, spec, request_id):
        source_calls.append(spec)
        return result().model_copy(update={"request_id": request_id})

    monkeypatch.setattr("gosari.agent.coordinator.lookup", lookup)
    monkeypatch.setattr("gosari.agent.coordinator.store", store)
    monkeypatch.setattr(
        "gosari.cache.semantic.response_cache_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr(
        "gosari.cache.public_source.public_source_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda *a, **k: None)
    monkeypatch.setattr("gosari.cache.public_source.put_source_result", lambda *a, **k: True)
    monkeypatch.setattr("gosari.agent.coordinator.AnalysisEngine.run", execute)
    monkeypatch.setattr(coordinator.llm, "stream_turn", turn)
    first = coordinator.run_job(Session(settings), PRICE)
    assert first.stage.value == "completed"
    assert len(model_calls) == 2 and len(source_calls) == 1
    assert (
        next(event for event in first.events if event.event_type == "ui_spec").payload[
            "selection_source"
        ]
        == "model"
    )
    second = coordinator.run_job(Session(settings), PRICE)
    assert second.stage.value == "completed"
    assert len(model_calls) == 2 and len(source_calls) == 1
    assert second.ui_spec == first.ui_spec
    assert second.ui_results["result_1"].requested_scope["package_weight_unit"] == "100 g"
    assert second.ui_results["result_1"].request_id == second.request_id
    assert (
        next(event for event in second.events if event.event_type == "ui_spec").payload[
            "selection_source"
        ]
        == "cache"
    )


def test_offline_multi_tool_ui_keeps_each_public_result_without_model(monkeypatch):
    from contextlib import nullcontext

    settings = Settings()
    coordinator = Coordinator(settings)
    session = Session(settings)
    job, spec = coordinator._new_job(session, PRICE)
    job.extra_scopes = {"current_observation": WEATHER}
    called = []
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: pytest.fail("combined cache must bypass")
    )
    monkeypatch.setattr(
        "gosari.cache.semantic.response_cache_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr(
        "gosari.cache.public_source.public_source_singleflight", lambda *a, **k: nullcontext()
    )
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda *a, **k: None)
    monkeypatch.setattr("gosari.cache.public_source.put_source_result", lambda *a, **k: True)

    def execute(engine, public, request_id):
        called.append(public["operation"])
        return result(public["operation"]).model_copy(update={"request_id": request_id})

    monkeypatch.setattr("gosari.agent.coordinator.AnalysisEngine.run", execute)
    coordinator._execute_job(session, job, spec)
    assert job.stage.value == "completed"
    assert called == ["retail_lookup", "current_observation"]
    assert len(job.ui_results) == 2
    assert {item.requested_scope["operation"] for item in job.ui_results.values()} == set(called)
    assert job.model_usage["calls"] == 0
