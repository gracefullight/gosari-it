from pathlib import Path

import pytest

from gosari.config import Settings

# Explicit Settings(_env_file=...) remains available to configuration tests.
Settings.model_config["env_file"] = None

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
