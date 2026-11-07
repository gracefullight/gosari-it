"""Start the native API with local settings and file-backed credentials."""

import os
import shlex
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
configured: dict[str, str] = {}
for name in (".local/settings.env", ".local/secrets/sources.env", ".local/dev.env"):
    path = root / name
    if not path.is_file():
        continue
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        words = shlex.split(value, comments=True)
        configured[key.removeprefix("export ").strip()] = words[0] if words else ""
for key, value in configured.items():
    os.environ.setdefault(key, value)
for setting, filename in (
    ("DB_PASSWORD_FILE", "db_app_password"),
    ("OPENAI_API_KEY_FILE", "openai_api_key"),
):
    path = root / ".local" / "secrets" / filename
    if path.is_file() and not Path(os.environ.get(setting) or "/nonexistent").is_file():
        os.environ[setting] = str(path)
os.chdir(root)
os.execv(  # noqa: S606 - Fixed arguments and the current virtualenv interpreter, no shell.
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "gosari.app:create_app",
        "--factory",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--reload-dir",
        str(root / "apps/api/src"),
    ],
)
