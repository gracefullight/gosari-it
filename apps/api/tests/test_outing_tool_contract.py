"""The agent receives the same comparison criteria and rows as the result UI."""

from gosari.agent.dialogue import _compact_tool
from gosari.domain.envelope import ResultEnvelope


def test_outing_tool_preserves_priority_and_ranked_weather_associations():
    candidates = [
        {
            "candidate_id": "second",
            "station_name": "서귀포",
            "target_date": "2026-11-09",
            "target_time_window": "09:00",
            "rank": 2,
            "weather": {
                "temperature_c": 15.4,
                "precipitation_probability": 24,
                "wind_speed_kmh": 15.8,
            },
        },
        {
            "candidate_id": "first",
            "station_name": "애월",
            "target_date": "2026-11-09",
            "target_time_window": "09:00",
            "rank": 1,
            "weather": {
                "temperature_c": 14.9,
                "precipitation_probability": 18,
                "wind_speed_kmh": 34.1,
            },
        },
    ]
    priorities = ["low_rain", "mild_temperature", "low_wind"]
    envelope = ResultEnvelope(
        request_id="comparison-contract",
        result={"candidates": candidates, "ranked_candidate_ids": ["first", "second"]},
    )
    facts = {}
    output = _compact_tool(envelope, "outing_compare", {"preferred_elements": priorities}, facts)
    assert output["preferred_elements"] == priorities
    assert [row["candidate_id"] for row in output["actual_ranking"]] == ["first", "second"]
    assert output["actual_ranking"][0]["weather"] == candidates[1]["weather"]
    assert output["actual_ranking"][1]["weather"] == candidates[0]["weather"]
    assert any(fact["value"] == 1 and "애월" in fact["label"] for fact in facts.values())
