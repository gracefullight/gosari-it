"""Direct credentials work without read-only Docker secret mounts."""

from contextlib import nullcontext
from secrets import token_hex

from gosari.config import Settings
from gosari.ops import bootstrap_public_db


def test_admin_direct_value_and_explicit_file_fallback(tmp_path):
    secret = tmp_path / "admin-password"
    file_value = token_hex(16)
    direct_value = token_hex(16)
    secret.write_text(file_value + "\n")
    settings = Settings(
        _env_file=None,
        db_admin_password=direct_value,
        db_admin_password_file=str(secret),
    )
    assert settings.resolved_db_admin_password == direct_value
    assert settings.model_copy(update={"db_admin_password": None}).resolved_db_admin_password == (
        file_value
    )


def test_bootstrap_uses_direct_credentials_without_secret_files(monkeypatch, capsys):
    import alembic.command

    admin_value = token_hex(16)
    app_value = token_hex(16)
    settings = Settings(
        _env_file=None,
        db_admin_password=admin_value,
        db_admin_password_file=None,
        db_password=app_value,
        db_password_file=None,
    )
    connections = []
    migrations = []

    class Connection:
        def execute(self, *args):
            return self

        def fetchone(self):
            return (1,)

    def connect(dsn, **kwargs):
        connections.append(dsn)
        return nullcontext(Connection())

    monkeypatch.setattr(bootstrap_public_db, "get_settings", lambda: settings)
    monkeypatch.setattr(bootstrap_public_db.psycopg, "connect", connect)
    monkeypatch.setattr(
        alembic.command, "upgrade", lambda config, revision: migrations.append(revision)
    )
    assert bootstrap_public_db.main() == 0
    assert len(connections) == 2
    assert all(f"password={admin_value}" in dsn for dsn in connections)
    assert migrations == ["head"]
    output = capsys.readouterr()
    assert admin_value not in output.out + output.err
    assert app_value not in output.out + output.err
