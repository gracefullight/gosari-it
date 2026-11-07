from gosari.config import Settings


def test_standard_openai_environment_overrides_older_file(monkeypatch, tmp_path):
    key_file = tmp_path / "old-key"
    key_file.write_text("old-file-key")
    monkeypatch.setenv("OPENAI_API_KEY", "  explicit-environment-key  ")
    settings = Settings(_env_file=None, openai_api_key_file=str(key_file))
    assert settings.resolved_openai_api_key == "explicit-environment-key"


def test_file_remains_available_when_openai_environment_is_missing(monkeypatch, tmp_path):
    key_file = tmp_path / "file-key"
    key_file.write_text("file-backed-key\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None, openai_api_key_file=str(key_file))
    assert settings.resolved_openai_api_key == "file-backed-key"


def test_blank_openai_environment_uses_file_fallback(monkeypatch, tmp_path):
    key_file = tmp_path / "file-key"
    key_file.write_text("file-backed-key")
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    settings = Settings(_env_file=None, openai_api_key_file=str(key_file))
    assert settings.resolved_openai_api_key == "file-backed-key"
