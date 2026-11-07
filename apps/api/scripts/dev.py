"""Start the native API with apps/api/.env and explicit environment overrides."""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

api_root = Path(__file__).resolve().parents[1]
root = api_root.parents[1]
for key, value in dotenv_values(api_root / ".env").items():
    if value is not None:
        os.environ.setdefault(key, value)
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
