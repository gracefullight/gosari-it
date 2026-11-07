"""Plan-index persistence without a DB, embedding engine, or model call."""

import copy
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from gosari.cache import dialogue_plan, semantic
from gosari.config import Settings
from gosari.domain import CacheResolution

NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)
QUESTION = "제주 고사리 100g 판매가"
SPEC = {"operation": "retail_lookup", "source_ids": ["retail_sample", "tamnao"]}


class MemoryConnection:
    def __init__(self):
        self.rows = {}
        self.statements = []

    def execute(self, sql, params):
        self.statements.append((sql, params))
        row = None
        if "INSERT INTO public_response_cache" in sql:
            self.rows[(params[3], params[2])] = {
                "id": params[0],
                "payload": copy.deepcopy(params[8].obj),
                "evidence": params[9].obj,
                "expires": params[15],
                "digest": params[17],
            }
        elif "SELECT" in sql:
            stored = self.rows.get(tuple(params[:2]))
            if stored and stored["expires"] > params[2]:
                if "cache_entry_id, public_answer" in sql:
                    row = tuple(
                        stored[k] for k in ("id", "payload", "evidence", "expires", "digest")
                    )
                else:
                    row = tuple(stored[k] for k in ("payload", "expires", "digest"))
        return SimpleNamespace(fetchone=lambda: row)

    def commit(self):
        pass


@pytest.fixture
def memory(monkeypatch):
    conn = MemoryConnection()
    settings = Settings(response_cache_enabled=True, domain_threshold_config=None)

    @contextmanager
    def connect():
        yield conn

    for module in (dialogue_plan, semantic):
        monkeypatch.setattr(module, "connection", connect)
        monkeypatch.setattr(module, "db_available", lambda: True)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(semantic, "get_engine", lambda: pytest.fail("unexpected embedding"))
    return conn, settings


def test_round_trip_without_raw_question_and_ordinary_answer_reuse(memory, monkeypatch):
    conn, _ = memory
    assert dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    assert dialogue_plan.read_plan(QUESTION, now=NOW) == [semantic.canonical_public_spec(SPEC)]
    assert QUESTION not in repr(conn.statements)
    (fingerprint, exact), stored = next(iter(conn.rows.items()))
    assert not semantic.result_cacheable(stored["payload"])
    assert stored["evidence"] == []
    assert conn.statements[0][1][4] is None
    # Even a forced namespace collision must never serve a plan as a response.
    monkeypatch.setattr(semantic, "condition_fingerprint", lambda _: fingerprint)
    monkeypatch.setattr(semantic, "exact_query_hash", lambda *_: exact)
    assert semantic.lookup(SPEC, "canonical public spec", now=NOW) == (CacheResolution.MISS, None)


@pytest.mark.parametrize("context", ["prior-public-history", "", "private-context"])
def test_context_always_bypasses(memory, context):
    conn, _ = memory
    assert not dialogue_plan.store_plan(QUESTION, [SPEC], context, now=NOW)
    assert dialogue_plan.read_plan(QUESTION, context, now=NOW) is None
    assert conn.statements == []


@pytest.mark.parametrize(
    "question", ["엄마 밭 가격", "010-1234-5678 가격", "a@example.com 가격", "내 수첩 가격"]
)
def test_private_questions_never_touch_db(memory, question):
    conn, _ = memory
    assert not dialogue_plan.store_plan(question, [SPEC], now=NOW)
    assert dialogue_plan.read_plan(question, now=NOW) is None
    assert conn.statements == []


def test_exact_question_and_version_scope(memory, monkeypatch):
    assert dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    assert dialogue_plan.read_plan(QUESTION + "?", now=NOW) is None
    assert dialogue_plan.read_plan("제주 고사리 200g 판매가", now=NOW) is None
    monkeypatch.setattr(semantic, "PROMPT_VERSION", "new-prompt")
    assert dialogue_plan.read_plan(QUESTION, now=NOW) is None


def test_expiry_and_kst_day_boundary(memory):
    conn, _ = memory
    near_midnight = NOW.replace(hour=14, minute=59, second=30)
    assert dialogue_plan.store_plan(QUESTION, [SPEC], now=near_midnight)
    assert next(iter(conn.rows.values()))["expires"] == NOW.replace(hour=15)
    assert dialogue_plan.read_plan(QUESTION, now=near_midnight + timedelta(seconds=31)) is None
    assert dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    assert dialogue_plan.read_plan(QUESTION, now=NOW + timedelta(minutes=31)) is None


def test_time_sensitive_plan_has_shorter_ttl(memory):
    conn, _ = memory
    spec = {"operation": "current_observation", "source_ids": ["kma_aws"]}
    assert dialogue_plan.store_plan("제주 지금 날씨", [spec], now=NOW)
    assert next(iter(conn.rows.values()))["expires"] == NOW + timedelta(seconds=60)
    assert dialogue_plan.read_plan("제주 지금 날씨", now=NOW + timedelta(seconds=61)) is None


@pytest.mark.parametrize(
    "specs",
    [
        [],
        [SPEC, SPEC],
        [{"operation": "personal_note"}],
        [{**SPEC, "origin_filter": "010-1234-5678"}],
    ],
)
def test_invalid_specs_are_not_persisted(memory, specs):
    conn, _ = memory
    assert not dialogue_plan.store_plan(QUESTION, specs, now=NOW)
    assert conn.statements == []


def test_tampered_payload_is_rejected(memory):
    conn, _ = memory
    assert dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    next(iter(conn.rows.values()))["payload"]["specs"][0]["product_option"] = "변조"
    assert dialogue_plan.read_plan(QUESTION, now=NOW) is None


def test_db_failure_is_a_silent_miss(memory, monkeypatch):
    def unavailable():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(dialogue_plan, "connection", unavailable)
    assert not dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    assert dialogue_plan.read_plan(QUESTION, now=NOW) is None


def test_disabled_cache_and_naive_clock_bypass(memory):
    conn, settings = memory
    assert not dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW.replace(tzinfo=None))
    settings.response_cache_enabled = False
    assert dialogue_plan.read_plan(QUESTION, now=NOW) is None
    assert not dialogue_plan.store_plan(QUESTION, [SPEC], now=NOW)
    assert conn.statements == []
