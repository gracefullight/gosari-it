import threading
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from gosari.agent import PUBLIC_JEJU_STATIONS, build_public_spec
from gosari.agent.analysis import AnalysisEngine
from gosari.agent.coordinator import Coordinator
from gosari.agent.llm import LlmClient, explanation_matches
from gosari.cache.semantic import result_cacheable
from gosari.config import Settings
from gosari.domain import CacheResolution, SourceMode, ValueState
from gosari.domain.envelope import ResultEnvelope
from gosari.domain.errors import GosariError
from gosari.quality import interpret_numeric
from gosari.quality.calculation import Observation, deduplicate
from gosari.sessions import Session
from gosari.sources import SourceManifest
from gosari.sources.live import JejuHubAdapter, SourceBudget, TransmissionGate, sanitized_url

SPEC = {"operation": "current_observation", "source_ids": ["kma_aws"]}


def test_prepare_and_cache_hit_do_not_call_model(monkeypatch):
    coordinator = Coordinator(Settings())
    calls = []
    coordinator.llm = SimpleNamespace(
        available=True,
        structure_question=lambda *args: calls.append("model"),
        explain=lambda *args: calls.append("model"),
    )
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup",
        lambda *args, **kwargs: (
            CacheResolution.EXACT_HIT,
            {
                "answer": {"data_status": "complete", "source_mode": "replay", "result": {}},
                "evidence_ids": ["public-evidence"],
            },
        ),
    )
    session = Session(Settings())
    prepared = coordinator.prepare(
        session, {"text": "선흘 2023년과 2024년 4월 11일부터 12일까지 강수 비교"}
    )
    assert "spec" in prepared
    job = coordinator.run_job(session, prepared["spec"])
    assert job.result.cache_resolution == CacheResolution.EXACT_HIT
    assert calls == []


def test_queue_is_bounded_and_returns_retry_information(monkeypatch):
    settings = Settings(analysis_concurrency=1, analysis_queue_limit=1)
    coordinator = Coordinator(settings)
    session = Session(settings)
    entered = threading.Event()
    release = threading.Event()

    def run(engine, spec, request_id):
        entered.set()
        release.wait(timeout=3)
        return ResultEnvelope(request_id=request_id)

    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr("gosari.agent.analysis.AnalysisEngine.run", run)
    try:
        coordinator.start_job(session, SPEC)
        assert entered.wait(timeout=1)
        coordinator.start_job(session, SPEC)
        with pytest.raises(GosariError) as busy:
            coordinator.start_job(session, SPEC)
        assert busy.value.code == "LOCAL_BUSY"
        assert busy.value.http_status == 429
        assert busy.value.extra["retry_after_seconds"] > 0
        assert len(coordinator._jobs) == 2
    finally:
        release.set()
        coordinator._executor.shutdown(wait=True)


def test_terminal_job_retention_is_bounded(monkeypatch):
    settings = Settings(job_retention_limit=3)
    coordinator = Coordinator(settings)
    session = Session(settings)
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr(
        "gosari.agent.analysis.AnalysisEngine.run",
        lambda engine, spec, request_id: ResultEnvelope(request_id=request_id),
    )
    for _ in range(12):
        coordinator.run_job(session, SPEC)
    assert len(coordinator._jobs) == len(session.jobs) == 3


def test_cancel_retains_actual_completed_dates_and_stops_later_dates(monkeypatch):
    settings = Settings(external_requests_enabled=True)
    coordinator = Coordinator(settings)

    class Model:
        available = True

        def begin_job(self):
            pass

        def stream_turn(self, *args, **kwargs):
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "cancel-history",
                        "type": "function",
                        "function": {"name": "history_compare", "arguments": "{}"},
                    }
                ],
            }

    coordinator.llm = Model()
    session = Session(settings)
    called = []

    def day(adapter, selected, name):
        called.append(selected.isoformat())
        next(iter(coordinator._jobs.values())).cancelled = True
        return [], SourceManifest(
            source_id="jeju_579",
            dataset_id="579",
            operation="daily_weather",
            sanitized_parameters={},
            returned_count=0,
        )

    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr("gosari.sources.live.JejuHubAdapter.daily_weather", day)
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda spec: None)
    job = coordinator.run_job(
        session,
        {
            "operation": "history_compare",
            "source_ids": ["jeju_579"],
            "station_selections": [{"source_id": "jeju_579", "station_name": "선흘"}],
            "years": [2023, 2024],
            "month_day_start": "04-11",
            "month_day_end": "04-12",
        },
    )
    assert job.stage.value == "cancelled"
    assert called == ["2023-04-11"]
    assert job.result.data_status == "partial"
    assert job.result.result["completed_scope"][0]["date"] == "2023-04-11"
    assert any(event.completed_units == 1 for event in job.events)


def test_closed_session_is_not_repopulated_by_worker(monkeypatch):
    coordinator = Coordinator(Settings())
    session = Session(Settings())
    entered, release = threading.Event(), threading.Event()

    def run(engine, spec, request_id):
        entered.set()
        release.wait(timeout=3)
        engine.checkpoint()
        return ResultEnvelope(request_id=request_id)

    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *a, **k: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr("gosari.agent.analysis.AnalysisEngine.run", run)
    job = coordinator.start_job(session, SPEC)
    assert entered.wait(timeout=1)
    session.close()
    release.set()
    coordinator._executor.shutdown(wait=True)
    assert session.jobs == {}
    assert job.job_id not in coordinator._jobs


def test_public_station_validation_preserves_all_42_provider_records():
    assert len(PUBLIC_JEJU_STATIONS) == 42
    for name, code in PUBLIC_JEJU_STATIONS:
        build_public_spec(
            {
                "operation": "history_compare",
                "source_ids": ["jeju_579"],
                "station_selections": [
                    {"source_id": "jeju_579", "station_name": name, "station_code": code}
                ],
            }
        )
    with pytest.raises(GosariError) as private:
        build_public_spec(
            {
                "operation": "history_compare",
                "source_ids": ["jeju_579"],
                "station_selections": [{"source_id": "jeju_579", "station_name": "개인밭_CANARY"}],
            }
        )
    assert private.value.code == "STATION_AMBIGUOUS"


@pytest.mark.parametrize("state", ["missing", "error", "unresolved_blank"])
def test_nested_quality_states_prevent_cache_store(state):
    assert not result_cacheable(
        {
            "data_status": "complete",
            "result": {"daily_rainfall": {"per_year": {"2023": {"value_states": {state: 1}}}}},
        }
    )
    assert not result_cacheable({"data_status": "complete", "result": {"value_states": [state]}})


def test_valid_zero_is_cacheable_but_failed_explanation_is_not():
    assert result_cacheable(
        {"data_status": "complete", "result": {"value_states": {"valid_zero": 1}}}
    )
    assert not result_cacheable({"data_status": "complete", "warnings": ["설명 실패"]})


def test_legacy_validator_remains_independent_and_completed_explanation_is_preserved(monkeypatch):
    result = {
        "daily_rainfall": {
            "common_day_count": 51,
            "per_year": {"2023": {"positive_days": 21}, "2024": {"positive_days": 20}},
        }
    }
    assert not explanation_matches("2023년 20일, 2024년 21일", result)
    assert not explanation_matches("채취 허가가 완료된 안전한 명당입니다.", result)
    client = LlmClient(Settings())
    monkeypatch.setattr(client, "_chat", lambda *a, **k: "2023년 20일, 2024년 21일")
    assert client.explain({"result": result}) == "2023년 20일, 2024년 21일"


@pytest.mark.parametrize("operation", ["history_compare", "region_compare"])
def test_empty_successful_weather_scope_is_no_data(monkeypatch, operation):
    engine = AnalysisEngine(Settings())
    monkeypatch.setattr(engine, "_observations_for", lambda spec: ([], SourceMode.FETCHED, [], []))
    selections = [{"source_id": "jeju_579", "station_name": "선흘"}]
    if operation == "region_compare":
        selections.append({"source_id": "jeju_579", "station_name": "서귀포"})
    envelope = engine.run(
        {"operation": operation, "station_selections": selections, "years": [2023, 2024]}, "empty"
    )
    assert envelope.data_status == "no_data"


def test_unfinished_jeju_pages_cannot_be_complete(monkeypatch):
    class Gate:
        def get_json(self, url, params):
            return {
                "data": [
                    {
                        "observatoryName": "선흘",
                        "baseDate": "20230411",
                        "dailyRainfall": "1",
                        "averageTemperature": "15",
                    }
                ],
                "totCnt": 3,
                "hasMore": True,
            }, "test-hash"

    observations, manifest = JejuHubAdapter(
        Gate(), Settings(jeju_project_key="synthetic")
    ).daily_weather(date(2023, 4, 11), "선흘", max_pages=1)
    assert manifest.has_more
    assert manifest.failed_scope["reason"] == "PAGE_LIMIT_REACHED"
    assert manifest.fetched_scope["returned_count"] == 1
    engine = AnalysisEngine(Settings())
    monkeypatch.setattr(
        engine, "_observations_for", lambda spec: (observations, SourceMode.FETCHED, [manifest], [])
    )
    result = engine.run(
        {
            "operation": "history_compare",
            "station_selections": [{"source_id": "jeju_579", "station_name": "선흘"}],
            "years": [2023, 2024],
        },
        "page",
    )
    assert result.data_status == "partial"


def test_conflicting_values_are_excluded_and_comparison_withheld(monkeypatch):
    rows = [
        Observation(
            "jeju_579",
            "선흘",
            date(2023, 4, 11),
            "daily_rainfall",
            str(value),
            Decimal(value),
            ValueState.VALID,
        )
        for value in (1, 2)
    ]
    assert deduplicate(rows).unique == []
    engine = AnalysisEngine(Settings())
    monkeypatch.setattr(
        engine, "_observations_for", lambda spec: (rows, SourceMode.FETCHED, [], [])
    )
    result = engine.run(
        {
            "operation": "history_compare",
            "station_selections": [{"source_id": "jeju_579", "station_name": "선흘"}],
            "years": [2023, 2024],
        },
        "conflict",
    )
    assert result.data_status == "conflict"
    assert result.result["daily_rainfall"]["comparison_status"] == "conflict"
    assert result.result["daily_rainfall"]["per_year"]["2023"]["positive_days"] is None


def test_provider_budget_is_shared_across_gate_instances():
    budget = SourceBudget()
    settings = Settings(external_requests_enabled=True, source_daily_budget=1)
    first = TransmissionGate(settings, budget=budget)
    second = TransmissionGate(settings, budget=budget)
    first.check("https://apis.data.go.kr/test")
    with pytest.raises(GosariError) as exceeded:
        second.check("https://apis.data.go.kr/test")
    assert exceeded.value.code == "BUDGET_EXCEEDED"
    assert TransmissionGate(settings)._budget is TransmissionGate(settings)._budget


@pytest.mark.parametrize("field", ["origin_filter", "product_option", "preferred_elements"])
def test_allowed_field_cannot_carry_private_canary_into_public_evidence(field):
    payload = {
        "operation": "retail_lookup",
        "source_ids": ["retail_sample"],
        field: "010-9724-6381",
    }
    with pytest.raises(GosariError):
        build_public_spec(payload)


def test_price_question_clarifies_price_conditions():
    prepared = Coordinator(Settings()).prepare(Session(Settings()), {"text": "제주 고사리 얼마야?"})
    assert prepared["feature"] == "price"
    assert prepared["form"]["feature_hint"] == "price"
    assert "가격" in str(prepared["form"])
    assert "연도" not in str(prepared["form"])


@pytest.mark.parametrize(
    ("raw", "state"),
    [
        (0, "valid_zero"),
        ("0", "valid_zero"),
        ("", "unresolved_blank"),
        (None, "missing"),
        ("not-a-number", "error"),
    ],
)
def test_numeric_zero_blank_missing_and_error_are_distinct(raw, state):
    assert interpret_numeric(raw).state.value == state


def test_jeju_path_key_is_removed_from_sanitized_url():
    result = sanitized_url(
        "https://open.jejudatahub.net/api/proxy/dataset/AUDIT_FAKE_KEY_20261107?token=also_fake"
    )
    assert "AUDIT_FAKE_KEY" not in result
    assert "also_fake" not in result
    assert result.endswith("/[REDACTED]")


@pytest.mark.parametrize(
    ("value", "expected"), [(None, False), ("", False), ("  ", False), (0, True), ("0", True)]
)
def test_forecast_required_value_blocks_cache_but_optional_issue_time_does_not(value, expected):
    answer = {
        "data_status": "complete",
        "result": {"forecast": [{"category": "TMP", "value": value, "published_at": None}]},
    }
    assert result_cacheable(answer) is expected


def test_cancel_after_engine_return_preserves_actual_result_before_post_fetch_checkpoint(
    monkeypatch,
):
    coordinator = Coordinator(Settings(external_requests_enabled=True))
    session = Session(coordinator.settings)
    model_calls = []
    source_calls = []

    class Model:
        available = True

        def begin_job(self):
            pass

        def stream_turn(self, *args, **kwargs):
            model_calls.append(1)
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "current-observation",
                        "type": "function",
                        "function": {"name": "current_observation", "arguments": "{}"},
                    }
                ],
            }

    coordinator.llm = Model()
    monkeypatch.setattr(
        "gosari.agent.coordinator.lookup", lambda *args, **kwargs: (CacheResolution.BYPASS, None)
    )
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda spec: None)
    monkeypatch.setattr(
        "gosari.cache.public_source.put_source_result",
        lambda *args, **kwargs: pytest.fail("cancelled result entered cache"),
    )

    def engine_run(engine, spec, request_id):
        source_calls.append(spec["operation"])
        next(iter(coordinator._jobs.values())).cancelled = True
        return ResultEnvelope(
            request_id=request_id,
            data_status="complete",
            source_mode="fetched",
            result={"actual_source_value": 15.7},
        )

    monkeypatch.setattr("gosari.agent.analysis.AnalysisEngine.run", engine_run)
    job = coordinator.run_job(session, SPEC)
    assert job.stage.value == "cancelled" and job.result.data_status == "partial"
    assert job.result.result == {"actual_source_value": 15.7}
    assert source_calls == ["current_observation"] and len(model_calls) == 1
    assert job.assistant_text == ""


@pytest.mark.parametrize("cancel_at", ["first_date", "engine_return"])
def test_chat_dialogue_cancel_retains_actual_source_dates_or_returned_result(
    monkeypatch, cancel_at
):
    coordinator = Coordinator(Settings(external_requests_enabled=True))
    session = Session(coordinator.settings)
    job, _ = coordinator._new_job(session, SPEC)
    job.dialogue_messages = [{"role": "user", "content": "선흘 과거 날씨를 비교해줘"}]
    calls = []

    class Model:
        def begin_job(self):
            pass

        def stream_turn(self, *args, **kwargs):
            calls.append(1)
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "history",
                        "type": "function",
                        "function": {
                            "name": "history_compare",
                            "arguments": (
                                '{"station_name":"선흘","years":[2023,2024],'
                                '"month_day_start":"04-11","month_day_end":"04-12"}'
                            ),
                        },
                    }
                ],
            }

    coordinator.llm = Model()
    monkeypatch.setattr("gosari.cache.dialogue_plan.read_plan", lambda *args, **kwargs: None)
    monkeypatch.setattr("gosari.cache.public_source.get_source_result", lambda spec: None)
    monkeypatch.setattr(
        "gosari.cache.public_source.put_source_result",
        lambda *args, **kwargs: pytest.fail("cancelled source cached"),
    )
    days = []

    def first_day(adapter, selected, name):
        days.append(selected.isoformat())
        job.cancelled = True
        return [], SourceManifest(
            source_id="jeju_579",
            dataset_id="579",
            operation="daily_weather",
            sanitized_parameters={},
            returned_count=0,
        )

    monkeypatch.setattr("gosari.sources.live.JejuHubAdapter.daily_weather", first_day)
    if cancel_at == "engine_return":

        def engine_run(engine, spec, request_id):
            job.cancelled = True
            return ResultEnvelope(
                request_id=request_id, data_status="complete", result={"actual_source_value": 15.7}
            )

        monkeypatch.setattr("gosari.agent.analysis.AnalysisEngine.run", engine_run)
    coordinator._execute_dialogue_job(session, job)
    assert (
        job.stage.value == "cancelled" and job.result.data_status == "partial" and len(calls) == 1
    )
    if cancel_at == "first_date":
        assert days == ["2023-04-11"]
        assert job.result.result["completed_scope"][0]["date"] == "2023-04-11"
    else:
        assert job.result.result == {"actual_source_value": 15.7}
