import copy
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from psycopg.types.json import Jsonb

from gosari.cache import public_source, semantic
from gosari.config import Settings
from gosari.domain import CacheResolution

NOW = datetime(2026, 11, 7, 7, 0, tzinfo=UTC)
SPEC = {"operation": "station_search", "source_ids": ["jeju_578"]}
ANSWER = {
    "data_status": "complete",
    "source_mode": "fetched",
    "result": {"station_count": 43},
    "warnings": [],
    "evidence_ids": ["ev-public"],
}
MANIFESTS = [
    {
        "source_id": "jeju_578",
        "dataset_id": "stations",
        "operation": "stations",
        "rights_status": "public_api",
        "transport_status": "ok",
        "source_mode": "fetched",
        "parser_version": "1",
    }
]


@pytest.fixture
def cache(monkeypatch):
    settings = Settings(
        embedding_revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
        domain_threshold_config="0.95",
    )
    state = {"source": {}, "response": {}, "score": 0.95, "embeds": 0}

    class Engine:
        def token_count(self, text):
            return 10

        def embed(self, text):
            state["embeds"] += 1
            return [0.1] * 384

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Connection:
        def execute(self, sql, params=()):
            assert sql.count("%s") == len(params)
            if "INSERT INTO public_source_cache" in sql:
                state["source"][params[0]] = copy.deepcopy(
                    [
                        params[2].obj,
                        params[3].obj,
                        params[5],
                        params[6],
                        params[7],
                        params[8],
                        params[10],
                    ]
                )
            if "FROM public_source_cache" in sql:
                row = state["source"].get(params[0])
                return Cursor([copy.deepcopy(row[:6])] if row and row[6] > params[1] else [])
            if "INSERT INTO public_response_cache" in sql:
                state["response_evidence_parameter"] = params[9]
                state["response"][params[2]] = [
                    params[0],
                    json.loads(params[8]),
                    params[9].obj if isinstance(params[9], Jsonb) else params[9],
                    params[15],
                    params[17],
                    params[3],
                ]
            if "FROM public_response_cache" in sql:
                values = [
                    row
                    for row in state["response"].values()
                    if row[3] > params[-1 if "exact_query_hash" in sql else 2]
                ]
                if "exact_query_hash" in sql:
                    row = state["response"].get(params[1])
                    return Cursor([copy.deepcopy(row[:5])] if row and row[3] > params[2] else [])
                return Cursor(
                    [[r[0], r[1], r[2], state["score"], r[4]] for r in values if r[5] == params[1]]
                )
            return Cursor([])

        def commit(self):
            pass

        def rollback(self):
            pass

    @contextmanager
    def connection():
        yield Connection()

    for module in (semantic, public_source):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
        monkeypatch.setattr(module, "db_available", lambda: True)
        monkeypatch.setattr(module, "connection", connection)
    monkeypatch.setattr(semantic, "get_engine", Engine)
    return state


def test_normalized_result_survives_a_new_connection(cache):
    assert public_source.put_source_result(SPEC, ANSWER, source_manifests=MANIFESTS, now=NOW)
    assert public_source.get_source_result(SPEC, now=NOW + timedelta(seconds=1)) == ANSWER
    assert public_source.get_source_result({**SPEC, "source_ids": ["kma_aws"]}, now=NOW) is None


def test_source_integrity_expiry_and_parser_version_are_checked(cache):
    assert public_source.put_source_result(SPEC, ANSWER, source_manifests=MANIFESTS, now=NOW)
    row = next(iter(cache["source"].values()))
    row[0]["result"]["station_count"] = 99
    assert public_source.get_source_result(SPEC, now=NOW) is None
    assert public_source.put_source_result(SPEC, ANSWER, source_manifests=MANIFESTS, now=NOW)
    row = next(iter(cache["source"].values()))
    row[3] = "stale-parser"
    assert public_source.get_source_result(SPEC, now=NOW) is None
    assert public_source.get_source_result(SPEC, now=NOW + timedelta(hours=1)) is None


@pytest.mark.parametrize(
    "patch",
    [
        {"data_status": "partial"},
        {"warnings": ["missing"]},
        {"record_id": "private"},
        {"result": {"child": {"data_status": "partial"}}},
        {"result": {"price_value": None}},
        {"result": {"temperature_c": float("nan")}},
    ],
)
def test_incomplete_and_personal_results_are_never_shared(cache, patch):
    assert not public_source.put_source_result(
        SPEC, {**ANSWER, **patch}, source_manifests=MANIFESTS, now=NOW
    )
    assert not cache["source"]


def test_manifest_quality_must_be_explicit(cache):
    assert not public_source.put_source_result(
        SPEC,
        ANSWER,
        source_manifests=[{"source_id": "jeju_578", "source_mode": "fetched"}],
        now=NOW,
    )


def test_exact_hit_never_embeds_and_checks_integrity(cache):
    assert semantic.store(
        SPEC, "제주 관측소", ANSWER, ["ev-public"], now=NOW, valid_until=NOW + timedelta(minutes=5)
    )
    cache["embeds"] = 0
    resolution, value = semantic.lookup(SPEC, "제주 관측소", now=NOW)
    assert resolution == CacheResolution.EXACT_HIT
    assert value["answer"] == ANSWER
    assert cache["embeds"] == 0
    next(iter(cache["response"].values()))[1]["result"]["station_count"] = 99
    assert semantic.lookup(SPEC, "제주 관측소", now=NOW)[1] is None


def test_response_evidence_ids_use_jsonb_not_a_postgresql_array(cache):
    assert semantic.store(
        SPEC, "제주 관측소", ANSWER, ["ev-public"], now=NOW, valid_until=NOW + timedelta(minutes=5)
    )
    parameter = cache["response_evidence_parameter"]
    assert isinstance(parameter, Jsonb), (
        "JSONB evidence IDs must not use PostgreSQL array adaptation"
    )
    assert parameter.obj == ["ev-public"]


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.949, CacheResolution.MISS),
        (0.95, CacheResolution.MISS),
        (0.95001, CacheResolution.SEMANTIC_HIT),
    ],
)
def test_cosine_is_strictly_greater_than_95_percent(cache, score, expected):
    assert semantic.store(
        SPEC, "제주 관측소", ANSWER, ["ev-public"], now=NOW, valid_until=NOW + timedelta(minutes=5)
    )
    cache["score"] = score
    assert semantic.lookup(SPEC, "제주 공개 관측 지점", now=NOW)[0] == expected


def test_exact_store_and_lookup_work_without_embedding_model(cache, monkeypatch):
    class MissingEngine:
        def token_count(self, text):
            return None

        def embed(self, text):
            raise AssertionError("Exact cache must not embed")

    monkeypatch.setattr(semantic, "get_engine", MissingEngine)
    assert semantic.store(
        SPEC, "제주 관측소", ANSWER, ["ev-public"], now=NOW, valid_until=NOW + timedelta(minutes=5)
    )
    assert semantic.lookup(SPEC, "제주 관측소", now=NOW)[0] == CacheResolution.EXACT_HIT


def test_four_parallel_nested_scopes_reuse_lock_connections_without_pool_exhaustion(
    cache, monkeypatch
):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    semaphore = threading.BoundedSemaphore(8)
    mutex = threading.Lock()
    usage = {"active": 0, "peak": 0, "opens": 0}

    class Cursor:
        def fetchone(self):
            return [True]

    class LockConnection:
        def execute(self, sql, params=()):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    @contextmanager
    def bounded_connection():
        assert semaphore.acquire(timeout=1), "Singleflight exhausted the 8-connection pool"
        with mutex:
            usage["active"] += 1
            usage["opens"] += 1
            usage["peak"] = max(usage["peak"], usage["active"])
        try:
            yield LockConnection()
        finally:
            with mutex:
                usage["active"] -= 1
            semaphore.release()

    monkeypatch.setattr(public_source, "connection", bounded_connection)

    def run(index):
        with (
            public_source.public_cache_singleflight(f"response-{index}", namespace="response"),
            public_source.public_cache_singleflight(f"source-{index}"),
        ):
            with public_source.connection():
                time.sleep(0.03)
            with public_source.connection():
                time.sleep(0.03)
        return index

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(run, range(4))) == [0, 1, 2, 3]
    assert usage["active"] == 0
    assert usage["peak"] <= 8
    assert usage["opens"] == 12  # Four outer connections and eight brief queries.
