from pathlib import Path

from gosari.agent.analysis import AnalysisEngine
from gosari.config import Settings


def test_outing_reasons_resolve_observation_and_history_values(fixtures_dir: Path) -> None:
    engine = AnalysisEngine(Settings(app_profile="replay", fixtures_dir=str(fixtures_dir)))
    envelope = engine.run(
        {
            "operation": "outing_compare",
            "candidates": [
                {
                    "station_name": "선흘",
                    "target_date": "2026-04-18",
                    "target_time_window": "오전",
                },
                {"station_name": "가파도"},
            ],
        },
        "display-regression",
    )
    candidate = envelope.result["candidates"][0]
    reasons = candidate["comparison_reasons"]
    current_candidate = envelope.result["candidates"][1]
    current = current_candidate["current_observation"]
    current_reason = current_candidate["comparison_reasons"][0]
    assert f"기온 {current['temperature_c']}℃" in current_reason
    assert f"일강수 {current['day_rain_mm']}mm" in current_reason
    for history in candidate["history_context"]:
        reason = next(r for r in reasons if r.startswith(f"{history['year']}년"))
        rain_summary = (
            f"관측 {history['rain_valid_days']}일 중 비 {history['rain_positive_days']}일"
        )
        assert rain_summary in reason
        assert f"평균 {history['temp_average_c']}℃" in reason
    assert not any("{" in reason or "}" in reason for reason in reasons)
