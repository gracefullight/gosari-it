"""psycopg3 동기 연결 풀 (SRS 기술 환경). 비밀 포함 DSN은 로그에 남기지 않는다."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from gosari.config import Settings, get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def open_pool(settings: Settings | None = None) -> ConnectionPool:
    """앱 시작 시 1회. 백그라운드에서 연결을 수립하며 DB 부재는 제한 모드로 처리된다."""
    global _pool
    if _pool is not None:
        return _pool
    s = settings or get_settings()
    _pool = ConnectionPool(
        conninfo=s.db_dsn,
        min_size=s.db_pool_min,
        max_size=max(s.db_pool_max, s.db_pool_min),
        kwargs={"autocommit": False, "connect_timeout": 3},
        open=False,
        name="gosari-public",
    )
    _pool.open(wait=False)
    return _pool


def get_pool() -> ConnectionPool | None:
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    pool = get_pool()
    if pool is None:
        from gosari.domain.errors import GosariError

        raise GosariError("DATABASE_UNAVAILABLE")
    with pool.connection(timeout=5.0) as conn:
        register_vector(conn)
        yield conn


_availability_cache: tuple[bool, float] | None = None


def db_available() -> bool:
    global _availability_cache
    now = time.monotonic()
    if _availability_cache is not None and now - _availability_cache[1] < 5.0:
        return _availability_cache[0]
    pool = get_pool()
    if pool is None:
        return False
    try:
        with pool.connection(timeout=2.0) as conn:
            conn.execute("SELECT 1")
        result = True
    except Exception:
        logger.warning("public DB health check failed")
        result = False
    _availability_cache = (result, now)
    return result
