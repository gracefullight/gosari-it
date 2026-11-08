"""Hermetic response-cache persistence, equivalence and integrity contract."""

import copy
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from gosari.cache import dialogue_response as cache
from gosari.cache import semantic
from gosari.cache.embeddings import DIMENSIONS
from gosari.config import Settings
from gosari.domain import CacheResolution

NOW = datetime(2026, 11, 8, 3, tzinfo=UTC)
QUESTION = "제주 고사리 100g 판매가 알려줘"
PARAPHRASE = "제주도 고사리 100그램 소매가 보여줘"
SPEC = {"operation": "retail_lookup", "source_ids": ["retail_sample", "tamnao"]}


def envelope(spec=SPEC, *, value=17000, evidence="ev-1"):
    return {
        "request_id": "public-request",
        "data_status": "complete",
        "source_mode": "replay",
        "requested_scope": semantic.canonical_public_spec(spec),
        "result": {"price_cards": [{"price_value": value, "unit": "원", "source_id": "tamnao"}]},
        "evidence_ids": [evidence],
        "warnings": [],
        "errors": [],
    }


def answer(spec=SPEC):
    return {**envelope(spec), "assistant_text": "탐나오 고사리 가격을 확인했어요."}


class MemoryConnection:
    def __init__(self):
        self.rows = {}
        self.statements = []

    def execute(self, sql, params):
        self.statements.append((sql, params))
        row = None
        rows = []
        if "INSERT INTO public_response_cache" in sql:
            self.rows[(params[3], params[2])] = {
                "id": params[0],
                "payload": copy.deepcopy(params[7].obj),
                "evidence": copy.deepcopy(params[8].obj),
                "expires": params[14],
                "digest": params[16],
                "vector": None,
                "eligible": True,
                "similarity": 0.98,
            }
        elif sql.startswith("SELECT 1"):
            row = next(
                (
                    (1,)
                    for (fingerprint, _), stored in self.rows.items()
                    if fingerprint == params[0]
                    and stored["vector"] is not None
                    and stored["eligible"]
                    and stored["expires"] > params[1]
                ),
                None,
            )
        elif "AS similarity" in sql:
            for (fingerprint, _), stored in self.rows.items():
                if (
                    fingerprint == params[1]
                    and stored["vector"] is not None
                    and stored["eligible"]
                    and stored["expires"] > params[2]
                ):
                    rows.append((*self.result(stored), stored["similarity"]))
            rows.sort(key=lambda item: item[5], reverse=True)
            rows = rows[:5]
        elif sql.startswith("SELECT"):
            stored = self.rows.get(tuple(params[:2]))
            if stored and stored["eligible"] and stored["expires"] > params[2]:
                row = self.result(stored)
        elif sql.startswith("UPDATE public_response_cache SET embedding"):
            for stored in self.rows.values():
                if (
                    stored["id"] == params[1]
                    and stored["digest"] == params[2]
                    and stored["eligible"]
                    and stored["expires"] > params[3]
                ):
                    stored["vector"] = params[0]
                    row = (stored["id"],)
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: rows)

    @staticmethod
    def result(stored):
        return tuple(stored[key] for key in ("id", "payload", "evidence", "expires", "digest"))

    def commit(self):
        pass


@pytest.fixture
def memory(monkeypatch):
    conn = MemoryConnection()
    settings = Settings(_env_file=None, response_cache_enabled=True, domain_threshold_config="0.95")

    @contextmanager
    def connect():
        yield conn

    monkeypatch.setattr(cache, "connection", connect)
    monkeypatch.setattr(cache, "db_available", lambda: True)
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    monkeypatch.setattr(semantic, "get_settings", lambda: settings)
    monkeypatch.setattr(cache, "get_engine", lambda: pytest.fail("unexpected embedding load"))
    return conn, settings


def store(question=QUESTION, history=None, specs=None, payload=None, evidence=None, now=NOW):
    return cache.store_response(
        question,
        history or [],
        specs or [SPEC],
        payload or answer(),
        evidence or ["ev-1"],
        now=now,
        valid_until=now + timedelta(hours=1),
    )


def embedder(monkeypatch):
    calls = []
    engine = SimpleNamespace(
        token_count=lambda text: 20,
        embed=lambda text: calls.append(text) or [1.0] + [0.0] * (DIMENSIONS - 1),
    )
    monkeypatch.setattr(cache, "get_engine", lambda: engine)
    return calls


def test_exact_is_immediate_without_embedding_or_raw_question_persistence(memory):
    conn, _ = memory
    assert store()
    assert next(iter(conn.rows.values()))["vector"] is None
    assert QUESTION not in repr(conn.statements)
    resolution, payload = cache.lookup_response(QUESTION, [], now=NOW)
    assert resolution == CacheResolution.EXACT_HIT
    assert payload == {
        "specs": [semantic.canonical_public_spec(SPEC)],
        "answer": answer(),
        "evidence_ids": ["ev-1"],
    }
    payload["answer"]["assistant_text"] = "local mutation"
    assert (
        cache.lookup_response(QUESTION, [], now=NOW)[1]["answer"]["assistant_text"]
        != "local mutation"
    )


def test_empty_candidates_and_unindexed_rows_never_load_model(memory):
    assert cache.lookup_response(QUESTION, [], now=NOW) == (CacheResolution.MISS, None)
    assert store()
    assert cache.lookup_response(PARAPHRASE, [], now=NOW) == (CacheResolution.MISS, None)


def test_background_enrichment_enables_guarded_paraphrase(memory, monkeypatch):
    assert store()
    calls = embedder(monkeypatch)
    assert cache.enrich_response_embedding(QUESTION, [], now=NOW)
    resolution, payload = cache.lookup_response(PARAPHRASE, [], now=NOW)
    assert resolution == CacheResolution.SEMANTIC_HIT
    assert payload["answer"] == answer()
    assert calls == [QUESTION, PARAPHRASE]


def test_same_row_outlives_the_previous_sixty_second_plan_index(memory):
    assert store()
    assert (
        cache.lookup_response(QUESTION, [], now=NOW + timedelta(minutes=3))[0]
        == CacheResolution.EXACT_HIT
    )


def test_semantic_checks_all_top_five_candidates_for_valid_integrity(memory, monkeypatch):
    conn, _ = memory
    assert store()
    assert store(question=PARAPHRASE)
    embedder(monkeypatch)
    assert cache.enrich_response_embedding(QUESTION, [], now=NOW)
    assert cache.enrich_response_embedding(PARAPHRASE, [], now=NOW)
    first, second = conn.rows.values()
    first["similarity"] = 0.999
    first["payload"]["answer"]["assistant_text"] = "tampered"
    second["similarity"] = 0.98
    resolution, hit = cache.lookup_response("제주도 고사리 100그램 소매가 확인해줘", [], now=NOW)
    assert resolution == CacheResolution.SEMANTIC_HIT
    assert hit["answer"] == answer()


@pytest.mark.parametrize("threshold", [None, "NaN", "Infinity", "1", "invalid"])
def test_invalid_semantic_configuration_keeps_exact_available(memory, threshold):
    _, settings = memory
    settings.domain_threshold_config = threshold
    assert store()
    assert cache.lookup_response(QUESTION, [], now=NOW)[0] == CacheResolution.EXACT_HIT
    assert cache.lookup_response(PARAPHRASE, [], now=NOW)[1] is None


@pytest.mark.parametrize("vector", [[0.0] * DIMENSIONS, [float("nan")] * DIMENSIONS, [1.0]])
def test_invalid_embedding_never_indexes_a_valid_exact_answer(memory, monkeypatch, vector):
    assert store()
    monkeypatch.setattr(
        cache,
        "get_engine",
        lambda: SimpleNamespace(token_count=lambda _: 20, embed=lambda _: vector),
    )
    assert not cache.enrich_response_embedding(QUESTION, [], now=NOW)
    assert cache.lookup_response(QUESTION, [], now=NOW)[0] == CacheResolution.EXACT_HIT


def test_cold_index_finishing_after_expiry_does_not_extend_lifetime(memory, monkeypatch):
    assert store()
    embedder(monkeypatch)
    times = iter([0.0, 1801.0])
    monkeypatch.setattr(cache.time, "monotonic", lambda: next(times))
    assert not cache.enrich_response_embedding(QUESTION, [], now=NOW)


@pytest.mark.parametrize(
    "different",
    [
        "제주 고사리 200g 판매가 알려줘",
        "내 수첩 고사리 100g 판매가",
        "제주 생고사리 100g 판매가",
        "성산 날씨",
        "고사리 사유지",
    ],
)
def test_changed_or_private_question_never_cross_hits(memory, monkeypatch, different):
    assert store()
    embedder(monkeypatch)
    assert cache.enrich_response_embedding(QUESTION, [], now=NOW)
    assert cache.lookup_response(different, [], now=NOW)[1] is None


def test_strict_threshold_and_configured_minimum(memory, monkeypatch):
    conn, settings = memory
    assert store()
    embedder(monkeypatch)
    assert cache.enrich_response_embedding(QUESTION, [], now=NOW)
    row = next(iter(conn.rows.values()))
    row["similarity"] = 0.95
    assert cache.lookup_response(PARAPHRASE, [], now=NOW)[1] is None
    settings.domain_threshold_config = "0.99"
    row["similarity"] = 0.98
    assert cache.lookup_response(PARAPHRASE, [], now=NOW)[1] is None


def test_unknown_conditions_still_have_exact_cache(memory):
    question = "내일 특이한 생육조건 설명도 곁들여 가격 알려줘"
    assert store(question=question)
    assert cache.lookup_response(question, [], now=NOW)[0] == CacheResolution.EXACT_HIT


def test_context_is_digest_only_and_separates_followups(memory):
    conn, _ = memory
    history = [
        {"role": "user", "content": "탐나오 건고사리 100g 판매가"},
        {"role": "assistant", "content": "가격을 확인했어요."},
    ]
    assert store(question="그럼 200g은?", history=history)
    assert cache.lookup_response("그럼 200g은?", history, now=NOW)[0] == CacheResolution.EXACT_HIT
    assert cache.lookup_response("그럼 200g은?", [], now=NOW)[1] is None
    changed = copy.deepcopy(history)
    changed[0]["content"] = "오아시스 건고사리 1000g 판매가"
    assert cache.lookup_response("그럼 200g은?", changed, now=NOW)[1] is None
    assert history[0]["content"] not in repr(conn.statements)


@pytest.mark.parametrize(
    "question",
    ["내 수첩 가격", "내가 등록한 스팟 알려줘", "010-1234-5678 가격", "a@example.com 가격"],
)
def test_private_question_never_queries_or_stores(memory, question):
    conn, _ = memory
    assert not store(question=question)
    assert cache.lookup_response(question, [], now=NOW) == (CacheResolution.BYPASS, None)
    assert conn.statements == []


@pytest.mark.parametrize(
    ("operation", "seconds"),
    [
        ("outing_compare", 300),
        ("current_observation", 900),
        ("forecast_compare", 900),
        ("retail_lookup", 1800),
    ],
)
def test_lifespan(operation, seconds):
    assert cache.lifespan([{"operation": operation}], NOW) == NOW + timedelta(seconds=seconds)


def test_bundle_shortest_lifetime_and_kst_midnight():
    assert cache.lifespan(
        [{"operation": "retail_lookup"}, {"operation": "outing_compare"}], NOW
    ) == NOW + timedelta(minutes=5)
    near_midnight = NOW.replace(hour=14, minute=59, second=30)
    assert cache.lifespan([SPEC], near_midnight) == NOW.replace(hour=15)


def test_expiry_version_and_invalidated_rows_cannot_hit(memory, monkeypatch):
    conn, _ = memory
    assert store()
    assert cache.lookup_response(QUESTION, [], now=NOW + timedelta(minutes=30))[1] is None
    next(iter(conn.rows.values()))["eligible"] = False
    assert cache.lookup_response(QUESTION, [], now=NOW)[1] is None
    assert store()
    monkeypatch.setattr(semantic, "PROMPT_VERSION", "another-prompt")
    assert cache.lookup_response(QUESTION, [], now=NOW)[1] is None


@pytest.mark.parametrize("target", ["answer", "evidence", "scope"])
def test_tampered_bundle_is_rejected(memory, target):
    conn, _ = memory
    assert store()
    row = next(iter(conn.rows.values()))
    if target == "answer":
        row["payload"]["answer"]["result"]["price_cards"][0]["price_value"] = 999
    elif target == "evidence":
        row["evidence"] = ["another-ev"]
    else:
        row["payload"]["scope"]["kst_date"] = "2026-11-09"
    assert cache.lookup_response(QUESTION, [], now=NOW)[1] is None


def test_duplicate_operation_results_and_ui_bindings_survive_roundtrip(memory):
    specs = [SPEC, {**SPEC, "fresh_or_dried": "fresh"}]
    first = envelope(specs[0])
    second = envelope(specs[1], value=23000, evidence="ev-2")
    payload = {
        **second,
        "assistant_text": "두 상품 가격을 비교했어요.",
        "dialogue_tool_results": [
            {"spec": spec, "envelope": result}
            for spec, result in zip(specs, [first, second], strict=True)
        ],
        "ui_spec": {
            "root": "root",
            "elements": {
                "root": {"type": "ResultLayout", "props": {}, "children": ["view_1", "view_2"]},
                "view_1": {"type": "PriceResults", "props": {"resultRef": "result_1"}},
                "view_2": {"type": "PriceResults", "props": {"resultRef": "result_2"}},
            },
        },
        "ui_results": {"result_1": first, "result_2": second},
    }
    assert store(specs=specs, payload=payload, evidence=["ev-1", "ev-2"])
    cached = cache.lookup_response(QUESTION, [], now=NOW)[1]
    assert cached["answer"] == payload
    assert len(cached["specs"]) == 2


@pytest.mark.parametrize(
    "defect",
    ["partial", "error", "warning", "missing_tool", "private", "nan", "no_evidence", "broken_ui"],
)
def test_incomplete_or_private_bundle_is_never_stored(memory, defect):
    conn, _ = memory
    payload = answer()
    if defect == "partial":
        payload["data_status"] = "partial"
    elif defect == "error":
        payload["result"]["errors"] = [{"code": "FAILED"}]
    elif defect == "warning":
        payload["warnings"] = ["incomplete"]
    elif defect == "missing_tool":
        payload["dialogue_tool_results"] = []
    elif defect == "private":
        payload["result"]["contact_id"] = "private-canary"
    elif defect == "nan":
        payload["result"]["price_cards"][0]["price_value"] = float("nan")
    elif defect == "no_evidence":
        payload["evidence_ids"] = ["missing-evidence"]
    else:
        payload["ui_spec"] = {"root": "missing", "elements": {}}
    assert not store(payload=payload)
    assert conn.statements == []


@pytest.mark.parametrize(
    "field", ["question", "user_question", "history", "dialogue_messages", "conversation_id"]
)
def test_raw_dialogue_fields_are_never_persisted(memory, field):
    conn, _ = memory
    payload = answer()
    payload[field] = "private-canary"
    assert not store(payload=payload)
    assert conn.statements == []


def test_multitool_partial_or_missing_grounding_rejects_entire_bundle(memory):
    conn, _ = memory
    first = envelope()
    second = envelope(evidence="ev-2")
    payload = {
        **second,
        "assistant_text": "두 번 조회했어요.",
        "dialogue_tool_results": [
            {"spec": SPEC, "envelope": first},
            {"spec": SPEC, "envelope": second},
        ],
    }
    first["data_status"] = "partial"
    assert not store(specs=[SPEC, SPEC], payload=payload, evidence=["ev-1", "ev-2"])
    first["data_status"] = "complete"
    first["evidence_ids"] = []
    assert not store(specs=[SPEC, SPEC], payload=payload, evidence=["ev-1", "ev-2"])
    assert conn.statements == []


def test_public_tool_references_are_preserved_without_raw_question(memory):
    payload = answer()
    payload["dialogue_references"] = [
        {
            "name": "retail_lookup",
            "payload": {"conditions": SPEC, "facts": [{"id": "f_1", "value": 17000, "unit": "원"}]},
        }
    ]
    assert store(payload=payload)
    assert cache.lookup_response(QUESTION, [], now=NOW)[1]["answer"] == payload


def continuation():
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "public-call-1",
                    "type": "function",
                    "function": {"name": "retail_lookup", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "public-call-1",
            "content": json.dumps(
                {"conditions": SPEC, "facts": {"f1": {"value": 17000, "unit": "원"}}}
            ),
        },
        {"role": "assistant", "content": "탐나오 고사리 가격을 확인했어요."},
    ]


def test_public_continuation_roundtrips_without_user_or_system_messages(memory):
    payload = answer()
    payload["dialogue_continuation"] = continuation()
    assert store(payload=payload)
    assert cache.lookup_response(QUESTION, [], now=NOW)[1]["answer"] == payload


@pytest.mark.parametrize(
    "defect", ["user", "system", "unpaired", "private_tool", "pii", "not_list"]
)
def test_invalid_or_private_continuation_is_never_persisted(memory, defect):
    conn, _ = memory
    payload = answer()
    messages = continuation()
    if defect in {"user", "system"}:
        messages.append({"role": defect, "content": "raw question must not be saved"})
    elif defect == "unpaired":
        messages.pop(1)
    elif defect == "private_tool":
        messages[0]["tool_calls"][0]["function"]["name"] = "search_personal_records"
    elif defect == "pii":
        messages[-1]["content"] = "a@example.com"
    payload["dialogue_continuation"] = messages if defect != "not_list" else {}
    assert not store(payload=payload)
    assert conn.statements == []


def test_disabled_database_failure_and_naive_time_are_nonfatal(memory, monkeypatch):
    conn, settings = memory
    settings.response_cache_enabled = False
    assert cache.lookup_response(QUESTION, [], now=NOW)[0] == CacheResolution.BYPASS
    settings.response_cache_enabled = True
    assert not store(now=NOW.replace(tzinfo=None))
    monkeypatch.setattr(
        cache, "connection", lambda: (_ for _ in ()).throw(RuntimeError("unavailable"))
    )
    assert not store()
    assert cache.lookup_response(QUESTION, [], now=NOW)[0] == CacheResolution.BYPASS
    assert conn.statements == []
