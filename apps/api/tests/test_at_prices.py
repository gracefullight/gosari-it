from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from gosari.agent.analysis import AnalysisEngine, get_evidence_store
from gosari.config import Settings
from gosari.domain.errors import GosariError
from gosari.sources import SourceManifest
from gosari.sources.at import AtAdapter, _body, query_settlements, settlement_card
from gosari.sources.live import SourceBudget, TransmissionGate

CATALOG = {
    "goods": [
        {
            "gds_lclsf_cd": "14",
            "gds_mclsf_cd": "02",
            "gds_mclsf_nm": "고사리",
            "gds_sclsf_cd": "01",
            "gds_sclsf_nm": "생고사리",
        },
        {"gds_sclsf_cd": "02", "gds_sclsf_nm": "건고사리"},
    ],
    "wholesaleMarkets": [
        {"whsl_mrkt_cd": "110001", "whsl_mrkt_nm": "서울가락"},
        {"whsl_mrkt_cd": "210001", "whsl_mrkt_nm": "부산엄궁"},
    ],
    "grades": [{"grd_cd": "11", "grd_nm": "특"}, {"grd_cd": "12", "grd_nm": "상"}],
    "packagings": [{"pkg_cd": "101", "pkg_nm": "상자"}, {"pkg_cd": "109", "pkg_nm": "봉지"}],
}


def row(**extra: Any) -> dict[str, Any]:
    return {
        "trd_clcln_ymd": "2026-04-15",
        "whsl_mrkt_cd": "110001",
        "whsl_mrkt_nm": "서울가락",
        "gds_lclsf_cd": "14",
        "gds_mclsf_cd": "02",
        "gds_sclsf_cd": "01",
        "gds_sclsf_nm": "생고사리",
        "grd_cd": "11",
        "grd_nm": "특",
        "pkg_cd": "101",
        "pkg_nm": "상자",
        "unit_qty": "4",
        "unit_nm": "kg",
        "avgprc": "20000",
        "plor_nm": "제주",
        **extra,
    }


def settings() -> Settings:
    return Settings(
        external_requests_enabled=True, at_service_key="test-only", response_cache_enabled=False
    )


def manifest(count: int, total: int, has_more: bool = False) -> SourceManifest:
    return SourceManifest(
        source_id="at_settlement",
        dataset_id="15141809",
        operation="katSale/trades",
        sanitized_parameters={},
        returned_count=count,
        total_count=total,
        has_more=has_more,
    )


@pytest.fixture(autouse=True)
def catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AtAdapter, "catalog", lambda self: CATALOG)


def test_actual_operation_parameters_and_secret_redaction() -> None:
    class Gate:
        def get_json(self, url: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
            assert url == "https://apis.data.go.kr/B552845/katSale/trades"
            assert params["cond[trd_clcln_ymd::EQ]"] == "2026-04-15"
            assert params["cond[whsl_mrkt_cd::EQ]"] == "110001"
            assert params["cond[gds_sclsf_cd::EQ]"] == "01"
            assert params["returnType"] == "json"
            return {
                "response": {
                    "header": {"resultCode": "0"},
                    "body": {"items": {"item": [row()]}, "totalCount": 1},
                }
            }, "digest"

    adapter = AtAdapter(Gate(), settings())  # type: ignore[arg-type]
    rows, receipt = adapter.settlement(date(2026, 4, 15), "110001", small_code="01")
    assert len(rows) == 1
    assert "test-only" not in str(receipt.to_dict())
    assert "serviceKey" not in receipt.sanitized_parameters


def test_pagination_reads_all_pages_before_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def page(self: AtAdapter, day: date, market: str, **kwargs: Any):
        calls.append(kwargs["page"])
        return [row(avgprc=str(20000 + kwargs["page"]))], manifest(1, 2, kwargs["page"] == 1)

    monkeypatch.setattr(AtAdapter, "settlement", page)
    result, receipts, failed, complete = query_settlements(
        {"settlement_date": "2026-04-15"}, settings()
    )
    assert calls == [1, 2]
    assert len(result["price_cards"]) == 2
    assert len(receipts) == 2 and not failed
    assert complete[0]["returned_count"] == complete[0]["total_count"] == 2


def test_failed_market_does_not_erase_successful_market(monkeypatch: pytest.MonkeyPatch) -> None:
    def page(self: AtAdapter, day: date, market: str, **kwargs: Any):
        if market == "210001":
            raise GosariError("UPSTREAM_FAILED")
        return [row()], manifest(1, 1)

    monkeypatch.setattr(AtAdapter, "settlement", page)
    spec = {
        "operation": "market_query",
        "settlement_date": "2026-04-15",
        "market_ids": ["110001", "210001"],
    }
    envelope = AnalysisEngine(settings()).run(spec, "test")
    assert envelope.data_status == "partial"
    assert envelope.source_mode == "fetched"
    assert len(envelope.result["price_cards"]) == 1
    assert envelope.result["failed_scope"][0]["market_code"] == "210001"


def test_page_mismatch_is_not_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AtAdapter, "settlement", lambda *args, **kwargs: ([row()], manifest(1, 2)))
    result, _, failed, complete = query_settlements({"settlement_date": "2026-04-15"}, settings())
    assert failed[0]["reason"] == "PAGE_COUNT_MISMATCH"
    assert not complete
    assert not result["price_cards"]


def test_row_outside_requested_scope_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        AtAdapter, "settlement", lambda *args, **kwargs: ([row(gds_mclsf_cd="99")], manifest(1, 1))
    )
    result, _, failed, _ = query_settlements({"settlement_date": "2026-04-15"}, settings())
    assert failed[0]["reason"] == "ROW_SCOPE_MISMATCH"
    assert not result["price_cards"]


def test_filters_do_not_mix_form_grade_package_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [row(), row(grd_cd="12"), row(pkg_cd="109"), row(plor_nm="충남")]

    def page(self: AtAdapter, day: date, market: str, **kwargs: Any):
        assert kwargs["small_code"] == "01"
        return rows, manifest(4, 4)

    monkeypatch.setattr(AtAdapter, "settlement", page)
    result, _, failed, _ = query_settlements(
        {
            "settlement_date": "2026-04-15",
            "fresh_or_dried": "생고사리",
            "grade": "11",
            "package_code": "101",
            "origin_filter": "제주",
        },
        settings(),
    )
    assert not failed
    assert len(result["price_cards"]) == 1


def test_history_keeps_each_date_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        AtAdapter,
        "settlement",
        lambda self, day, *args, **kwargs: ([row(trd_clcln_ymd=day.isoformat())], manifest(1, 1)),
    )
    result, _, failed, complete = query_settlements(
        {"settlement_date": "2026-04-14", "settlement_date_end": "2026-04-15"}, settings()
    )
    assert not failed and len(complete) == 2
    assert [c["price_as_of"] for c in result["price_cards"]] == ["2026-04-15", "2026-04-14"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "", None])
def test_invalid_average_never_becomes_zero(value: Any) -> None:
    card = settlement_card(row(avgprc=value))
    assert card["price_value"] is None
    assert card["price_per_kg_value"] is None
    assert card["price_state"] == "missing"


def test_mass_conversion_preserves_original_price_and_unknown_unit() -> None:
    card = settlement_card(row())
    assert card["price_value"] == 20000
    assert card["net_weight_value"] == 4000
    assert card["price_per_kg_value"] == 5000
    assert "20000" in str(Decimal(str(card["price_value"])))
    unknown = settlement_card(row(unit_nm="봉지"))
    assert unknown["price_value"] == 20000
    assert unknown["price_per_kg_value"] is None
    assert unknown["net_weight_value"] is None


def test_missing_key_never_falls_back_to_fixture_as_live() -> None:
    envelope = AnalysisEngine(Settings(external_requests_enabled=True)).run(
        {"operation": "market_query"}, "test"
    )
    assert envelope.data_status == "unavailable"
    assert envelope.source_mode is None
    assert envelope.result["reason"] == "AT_KEY_MISSING"


def test_upstream_error_is_not_no_data() -> None:
    with pytest.raises(GosariError, match="원천 조회"):
        _body({"response": {"header": {"resultCode": "99"}, "body": {"totalCount": 0}}})


def test_33_markets_two_dates_keep_one_rate_limited_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    markets = [str(110001 + index) for index in range(33)]
    codes = {
        **CATALOG,
        "wholesaleMarkets": [
            {"whsl_mrkt_cd": code, "whsl_mrkt_nm": f"합성시장{index + 1}"}
            for index, code in enumerate(markets)
        ],
    }
    monkeypatch.setattr(AtAdapter, "catalog", lambda self: codes)

    def page(self: AtAdapter, day: date, market: str, **kwargs: Any):
        if day.isoformat() == "2026-04-15" and market == markets[-1]:
            raise GosariError("SOURCE_RATE_LIMIT")
        return [row(trd_clcln_ymd=day.isoformat(), whsl_mrkt_cd=market)], manifest(1, 1)

    monkeypatch.setattr(AtAdapter, "settlement", page)
    envelope = AnalysisEngine(settings()).run(
        {
            "operation": "market_query",
            "market_ids": markets,
            "settlement_date": "2026-04-14",
            "settlement_date_end": "2026-04-15",
        },
        "acceptance-33-markets",
    )
    assert envelope.data_status == "partial"
    assert len(envelope.result["completed_scope"]) == 65
    assert len(envelope.result["price_cards"]) == 65
    assert len(envelope.result["failed_scope"]) == 1
    failed = envelope.result["failed_scope"][0]
    assert failed["market_code"] == markets[-1]
    assert failed["settlement_date"] == "2026-04-15"
    assert failed["page"] == 1 and failed["reason"] == "SOURCE_RATE_LIMIT"


def test_last_page_failure_preserves_other_market_and_retry_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def page(self: AtAdapter, day: date, market: str, **kwargs: Any):
        if market == "210001" and kwargs["page"] == 2:
            raise GosariError("UPSTREAM_FAILED")
        return [row(whsl_mrkt_cd=market)], manifest(
            1, 2 if market == "210001" else 1, market == "210001"
        )

    monkeypatch.setattr(AtAdapter, "settlement", page)
    envelope = AnalysisEngine(settings()).run(
        {
            "operation": "market_query",
            "market_ids": ["110001", "210001"],
            "settlement_date": "2026-04-15",
        },
        "acceptance-final-page",
    )
    assert envelope.data_status == "partial"
    assert len(envelope.result["price_cards"]) == 1
    assert envelope.result["failed_scope"][0]["page"] == 2
    assert envelope.result["failed_scope"][0]["returned_count"] == 1
    assert envelope.result["failed_scope"][0]["total_count"] == 2


def test_price_evidence_preserves_displayed_options_and_numeric_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gosari.agent.evidence_store.db_available", lambda: False)
    monkeypatch.setattr(AtAdapter, "settlement", lambda *args, **kwargs: ([row()], manifest(1, 1)))
    engine = AnalysisEngine(settings())
    wholesale = engine.run(
        {"operation": "market_query", "settlement_date": "2026-04-15"}, "evidence-wholesale"
    )
    retail = engine.run({"operation": "retail_lookup"}, "evidence-retail")
    for envelope, card_key in [(wholesale, "price_cards"), (retail, "sample_cards")]:
        evidence = get_evidence_store().get(envelope.evidence_ids[0])
        assert evidence is not None
        assert evidence["result_values"]["price_cards"] == envelope.result[card_key]
        assert evidence["result_values"]["units"]["net_weight_value"] == "g"
        assert evidence["result_values"]["units"]["price_per_kg_value"] == "KRW/kg"


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_stops_without_retry_or_secret_in_error(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    calls = []
    source_canary = "AUDIT_FAKE_SOURCE_KEY_20261107"

    def get(url: str, **kwargs: Any):
        calls.append(url)
        return httpx.Response(status, request=httpx.Request("GET", url, params=kwargs["params"]))

    monkeypatch.setattr("gosari.sources.live.httpx.get", get)
    gate = TransmissionGate(settings(), budget=SourceBudget())
    with pytest.raises(GosariError) as denied:
        gate.get_json("https://apis.data.go.kr/example", {"serviceKey": source_canary})
    assert denied.value.code == "POLICY_BLOCKED"
    assert len(calls) == 1
    assert source_canary not in str(denied.value) and source_canary not in str(denied.value.extra)


@pytest.mark.parametrize("payload", [{}, {"response": {"header": {"resultCode": "0"}, "body": {}}}])
def test_missing_required_upstream_fields_are_schema_errors(payload: Any) -> None:
    with pytest.raises(GosariError) as changed:
        _body(payload)
    assert changed.value.code == "UPSTREAM_SCHEMA_CHANGED"
