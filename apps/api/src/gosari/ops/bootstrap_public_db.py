"""공개 DB 초기화: vector 확장·앱 역할·마이그레이션. 관리자 권한은 초기화 전용."""

import sys
from pathlib import Path

import psycopg

from gosari.config import get_settings


def main() -> int:
    settings = get_settings()
    admin_password = settings.resolved_db_admin_password or ""
    app_password = settings.resolved_db_password or ""
    dsn = (
        f"host={settings.db_host} port={settings.db_port} dbname={settings.db_name} "
        f"user=postgres password={admin_password}"
    )
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            role_exists = conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (settings.db_user,)
            ).fetchone()
            if not role_exists:
                # CREATE ROLE은 서버 바인드 파라미터를 지원하지 않으므로 Literal로 이스케이프한다.
                conn.execute(
                    psycopg.sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        psycopg.sql.Identifier(settings.db_user),
                        psycopg.sql.Literal(app_password),
                    )
                )
            conn.execute(
                psycopg.sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    psycopg.sql.Identifier(settings.db_name),
                    psycopg.sql.Identifier(settings.db_user),
                )
            )
            conn.execute(
                psycopg.sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    psycopg.sql.Identifier(settings.db_user)
                )
            )
            conn.execute(
                psycopg.sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(psycopg.sql.Identifier(settings.db_user))
            )
        # 마이그레이션은 관리자 연결로 실행 (앱 역할에 DDL 권한을 주지 않는다)
        import alembic.command
        import alembic.config

        api_root = Path(__file__).resolve()
        while not (api_root / "alembic.ini").is_file() and api_root != api_root.parent:
            api_root = api_root.parent
        config = alembic.config.Config(str(api_root / "alembic.ini"))
        config.set_main_option("script_location", str(api_root / "alembic"))
        config.attributes["dsn"] = dsn
        alembic.command.upgrade(config, "head")
        # 기본 권한은 미래 테이블에만 적용되므로 기존 테이블에도 명시적으로 부여한다.
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                psycopg.sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(psycopg.sql.Identifier(settings.db_user))
            )
            conn.execute(
                psycopg.sql.SQL(
                    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}"
                ).format(psycopg.sql.Identifier(settings.db_user))
            )
        print("bootstrap_public_db: ok")
        return 0
    except Exception as exc:
        import traceback

        from gosari.logging import redact

        print(f"bootstrap_public_db: failed ({type(exc).__name__})", file=sys.stderr)
        print(redact(traceback.format_exc()), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
