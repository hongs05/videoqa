import os
from pathlib import Path

import pytest

from tests.fixtures.make_fixtures import build_all


def pytest_runtest_setup(item):
    if "slow" in item.keywords and not os.environ.get("VIDEOQA_SLOW"):
        pytest.skip("test lento: exporta VIDEOQA_SLOW=1 para correrlo")


@pytest.fixture(autouse=True)
def _videoqa_home(tmp_path_factory, monkeypatch):
    """Ningún test debe tocar el ~/.videoqa real del usuario que corre la suite.

    videoqa.config.videoqa_home() (usado por defaults de Settings.jobs_dir,
    default_config_path() y cli.setup_logging()) lee VIDEOQA_HOME en cada
    llamada, así que basta con fijarla aquí para aislar toda la suite.
    """
    home = tmp_path_factory.mktemp("videoqa_home")
    monkeypatch.setenv("VIDEOQA_HOME", str(home))
    return home


FIXTURE_OUT = Path(__file__).resolve().parent / "fixtures" / "out"


@pytest.fixture(scope="session")
def fixture_videos():
    return build_all(FIXTURE_OUT)
