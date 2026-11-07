import pytest

from gosari.agent import build_public_spec
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.coordinator import Coordinator
from gosari.config import Settings
from gosari.domain import CacheResolution
from gosari.sessions import Session


def engine(monkeypatch):
    class Evidence:
        def put(self, payload):
            return "synthetic-price-evidence"

    monkeypatch.setattr("gosari.agent.analysis.get_evidence_store", lambda: Evidence())
    return AnalysisEngine(Settings(app_profile="replay", external_requests_enabled=False))


def test_fresh_retail_does_not_show_dried_samples_or_claim_market_absence(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample"],
                "fresh_or_dried": "생고사리",
            }
        ),
        "fresh",
    )
    assert result.result["sample_cards"] == []
    assert result.result["links"] == []
    assert result.result["matched_sample_count"] == 0
    assert result.result["available_sample_count"] == 3
    assert result.result["reason"] == "NO_MATCHING_SAMPLE"
    assert result.data_status == "no_data"
    assert result.source_mode == "replay"
    assert result.verified_on == "2026-11-05"


def test_retail_option_preserves_price_weight_shipping_and_kg_conversion(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample"],
                "fresh_or_dried": "건고사리",
                "product_option": "200g",
            }
        ),
        "option",
    )
    assert len(result.result["sample_cards"]) == 1
    card = result.result["sample_cards"][0]
    assert card["product_option"] == "200g"
    assert card["price_value"] == 32500
    assert card["net_weight_value"] == 200
    assert card["net_weight_unit"] == "g"
    assert card["price_per_kg_value"] == 162500
    assert card["shipping_value"] == 4000
    assert result.data_status == "complete"


def test_retail_equivalent_kg_weight_and_explicit_source_are_respected(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample", "tamnao"],
                "package_weight_unit": "0.2 kg",
            }
        ),
        "weight",
    )
    cards = result.result["sample_cards"]
    assert len(cards) == 1 and cards[0]["source_id"] == "탐나오"
    assert cards[0]["net_weight_value"] == 200
    assert result.result["links"][0]["source_id"] == "tamnao"


def test_oasis_sample_retains_its_official_link_despite_query_string_difference(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "retail_lookup",
                "source_ids": ["retail_sample", "oasis"],
                "product_option": "80g",
            }
        ),
        "oasis",
    )
    assert len(result.result["sample_cards"]) == 1
    assert result.result["sample_cards"][0]["source_id"] == "오아시스마켓"
    assert result.result["links"][0]["source_id"] == "oasis"


def test_survey_fresh_stage_matches_without_changing_old_sample_date(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "survey_link",
                "source_ids": ["forestinfo"],
                "fresh_or_dried": "생고사리",
                "survey_stage": "소비지",
            }
        ),
        "survey",
    )
    assert len(result.result["sample_cards"]) == 1
    card = result.result["sample_cards"][0]
    assert card["price_value"] == 18500
    assert card["net_weight_value"] == 1000
    assert card["net_weight_unit"] == "g"
    assert card["price_as_of"] == "2026-11-04"
    assert result.source_mode == "link"
    assert result.data_status == "unavailable"


def test_dried_survey_has_zero_matching_samples_not_a_zero_price(monkeypatch):
    result = engine(monkeypatch).run(
        build_public_spec(
            {
                "operation": "survey_link",
                "source_ids": ["forestinfo"],
                "fresh_or_dried": "건고사리",
            }
        ),
        "survey-dried",
    )
    assert result.result["sample_cards"] == []
    assert result.result["matched_sample_count"] == 0
    assert result.result["sample_filter_status"] == "no_match"
    assert result.result["reason"] == "LINK_ONLY"


@pytest.mark.parametrize(
    ("question", "channel"),
    [("탐나오 건고사리200g판매가", "retail"), ("산림조합 생고사리 조사가", "survey")],
)
def test_ready_chat_intent_runs_its_public_tool_in_job_without_navigation(
    monkeypatch, question, channel
):
    class Evidence:
        def put(self, payload):
            return "synthetic-price-evidence"

    monkeypatch.setattr("gosari.agent.analysis.get_evidence_store", lambda: Evidence())
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr("httpx.get", lambda *a, **k: pytest.fail("fixture job called source"))
    monkeypatch.setattr("httpx.post", lambda *a, **k: pytest.fail("fixture job called model"))
    settings = Settings(external_requests_enabled=False, app_profile="replay")
    coordinator = Coordinator(settings)
    session = Session(settings)
    prepared = coordinator.prepare(session, {"text": question})
    assert prepared["needs_confirmation"] is False
    job = coordinator.run_job(session, prepared["spec"])
    assert job.stage.value == "completed"
    assert job.result.result["channel"] == channel
    assert job.result.result["sample_cards"]
    assert session.notebook == {} and session.regions == {} and session.share_drafts == {}
