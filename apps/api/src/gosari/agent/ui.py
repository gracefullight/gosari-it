"""Validated selections become a flat json-render spec with public result references."""

from contextlib import suppress
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gosari.agent import build_public_spec
from gosari.domain.envelope import ResultEnvelope, UiElement, UiSpec
from gosari.domain.errors import GosariError

Operation = Literal[
    "current_observation",
    "forecast_compare",
    "history_compare",
    "region_compare",
    "station_search",
    "outing_compare",
    "market_query",
    "survey_link",
    "retail_lookup",
]
Component = Literal[
    "PriceResults", "WeatherMap", "WeatherComparison", "OutingResults", "StationResults"
]
Action = Literal[
    "adjust_conditions",
    "save_to_notebook",
    "show_weather_map",
    "show_price_table",
    "compare_dates",
    "compare_packages",
]
COMPONENTS: dict[str, tuple[Component, ...]] = {
    "current_observation": ("WeatherComparison", "WeatherMap"),
    "forecast_compare": ("WeatherComparison", "WeatherMap"),
    "history_compare": ("WeatherComparison",),
    "region_compare": ("WeatherComparison", "WeatherMap"),
    "station_search": ("StationResults",),
    "outing_compare": ("OutingResults", "WeatherMap"),
    "market_query": ("PriceResults",),
    "survey_link": ("PriceResults",),
    "retail_lookup": ("PriceResults",),
}
ACTION_LABELS = {
    "adjust_conditions": "조건 바꾸기",
    "save_to_notebook": "수첩에 기록",
    "show_weather_map": "지도 보기",
    "show_price_table": "가격표 보기",
    "compare_dates": "날짜 비교",
    "compare_packages": "다른 규격 보기",
}
MAX_UI_ACTIONS = 8


class ViewSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: Component
    operation: Operation


class ActionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action
    operation: Operation


class UiSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    components: list[ViewSelection] = Field(max_length=12)
    actions: list[ActionSelection] = Field(max_length=24)


def selection_schema() -> dict[str, Any]:
    """Inline JSON schema keeps the provider tool definition stable and compact."""

    def item(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    operation = {"type": "string", "enum": list(COMPONENTS)}
    component = {
        "type": "string",
        "enum": list(dict.fromkeys(name for names in COMPONENTS.values() for name in names)),
    }
    action = {"type": "string", "enum": list(ACTION_LABELS)}
    return item(
        {
            "components": {
                "type": "array",
                "items": item({"component": component, "operation": operation}),
            },
            "actions": {"type": "array", "items": item({"action": action, "operation": operation})},
        }
    )


def _allowed_action(action: str, operation: str) -> bool:
    if action in ("adjust_conditions", "save_to_notebook"):
        return True
    if action in ("show_price_table", "compare_packages"):
        return operation in ("market_query", "survey_link", "retail_lookup")
    return operation in (
        "current_observation",
        "forecast_compare",
        "history_compare",
        "region_compare",
        "outing_compare",
    )


def build_ui(
    outputs: dict[str, ResultEnvelope],
    scopes: dict[str, dict[str, Any]],
    selection: Any = None,
) -> tuple[UiSpec | None, dict[str, ResultEnvelope], str]:
    """The model selects enum IDs; values, references and labels come from the server."""
    if not outputs:
        return None, {}, "fallback"
    chosen: UiSelection | None = None
    if selection is not None:
        with suppress(ValidationError):
            chosen = UiSelection.model_validate(selection)
    source = "model" if chosen is not None else "fallback"
    repaired = False
    references = {operation: f"result_{index + 1}" for index, operation in enumerate(outputs)}
    results: dict[str, ResultEnvelope] = {}
    for operation, envelope in outputs.items():
        if operation not in COMPONENTS:
            continue
        raw_context = scopes.get(operation) or envelope.requested_scope or {"operation": operation}
        context = build_public_spec(
            {key: value for key, value in raw_context.items() if key != "contains_personal_hint"}
        )
        # A reference always carries the exact validated conditions used by its tool.
        results[references[operation]] = envelope.model_copy(
            update={"requested_scope": context}, deep=True
        )
    elements: dict[str, UiElement] = {"root": UiElement(type="ResultLayout")}
    rendered: set[str] = set()
    for view in chosen.components if chosen else []:
        if view.operation not in outputs or view.component not in COMPONENTS[view.operation]:
            repaired = True
            continue
        ref = references[view.operation]
        if ref not in results or view.operation in rendered:
            repaired = True
            continue
        node = f"view_{len(rendered) + 1}"
        elements[node] = UiElement(type=view.component, props={"resultRef": ref})
        elements["root"].children.append(node)
        rendered.add(view.operation)
    if not rendered:
        source = "fallback"
    elif len(rendered) < len(results):
        repaired = True
    # A model selection cannot silently discard a second successful public tool result.
    for operation in outputs:
        ref = references[operation]
        if operation in rendered or ref not in results:
            continue
        node = f"view_{len(rendered) + 1}"
        elements[node] = UiElement(type=COMPONENTS[operation][0], props={"resultRef": ref})
        elements["root"].children.append(node)
        rendered.add(operation)
    actions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    selected_actions = (
        [(item.action, item.operation) for item in chosen.actions]
        if chosen
        else [("adjust_conditions", operation) for operation in outputs]
    )
    for action, operation in selected_actions:
        if (
            operation not in outputs
            or not _allowed_action(action, operation)
            or (action, operation) in seen
        ):
            repaired = True
            continue
        ref = references[operation]
        if ref not in results:
            continue
        if len(actions) >= MAX_UI_ACTIONS:
            source = "model_with_fallback" if chosen is not None else "fallback"
            break
        seen.add((action, operation))
        actions.append({"id": action, "label": ACTION_LABELS[action], "resultRef": ref})
    if actions:
        elements["actions"] = UiElement(type="FollowupActions", props={"actions": actions})
        elements["root"].children.append("actions")
    if source == "model" and repaired:
        source = "model_with_fallback"
    return UiSpec(root="root", elements=elements), results, source


def restore_ui(spec: Any, results: Any) -> tuple[UiSpec | None, dict[str, ResultEnvelope]]:
    """Reject cached code, arbitrary props, dangling references and private query context."""
    try:
        parsed = UiSpec.model_validate(spec)
        if not isinstance(results, dict) or len(results) > 12 or not results:
            return None, {}
        envelopes = {key: ResultEnvelope.model_validate(value) for key, value in results.items()}
        root = parsed.elements.get(parsed.root)
        if root is None or root.type != "ResultLayout" or root.props:
            return None, {}
        if len(parsed.elements) > 15 or set(root.children) != set(parsed.elements) - {parsed.root}:
            return None, {}
        referenced: set[str] = set()
        for key, element in parsed.elements.items():
            if key == parsed.root:
                continue
            if element.children:
                return None, {}
            if element.type == "FollowupActions":
                if set(element.props) != {"actions"} or not isinstance(
                    element.props["actions"], list
                ):
                    return None, {}
                if len(element.props["actions"]) > MAX_UI_ACTIONS:
                    return None, {}
                for action in element.props["actions"]:
                    if not isinstance(action, dict) or set(action) != {"id", "label", "resultRef"}:
                        return None, {}
                    ref = action["resultRef"]
                    envelope = envelopes.get(ref)
                    if (
                        envelope is None
                        or action["id"] not in ACTION_LABELS
                        or action["label"] != ACTION_LABELS[action["id"]]
                    ):
                        return None, {}
                    operation = str(envelope.requested_scope.get("operation") or "")
                    if not _allowed_action(action["id"], operation):
                        return None, {}
            else:
                if set(element.props) != {"resultRef"}:
                    return None, {}
                ref = element.props["resultRef"]
                envelope = envelopes.get(ref)
                if envelope is None:
                    return None, {}
                operation = str(envelope.requested_scope.get("operation") or "")
                if operation not in COMPONENTS or element.type not in COMPONENTS[operation]:
                    return None, {}
                build_public_spec(envelope.requested_scope)
                referenced.add(ref)
        if referenced != set(envelopes):
            return None, {}
        return parsed, envelopes
    except ValidationError, TypeError, ValueError, KeyError, GosariError:
        return None, {}
