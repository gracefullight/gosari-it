"""Alembic 환경 — 공개 DB만 대상. 개인 수첩을 디스크에 덤프하지 않는다."""

import psycopg
from sqlalchemy import create_engine

from alembic import context
from gosari.config import get_settings

config = context.config


def get_dsn() -> str:
    dsn = config.attributes.get("dsn")
    if dsn:
        return dsn
    return get_settings().db_dsn


def run_migrations_online() -> None:
    dsn = get_dsn()
    engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(dsn))
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
