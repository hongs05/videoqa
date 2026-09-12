import os
from pathlib import Path

import pytest

from tests.fixtures.make_fixtures import build_all


def pytest_runtest_setup(item):
    if "slow" in item.keywords and not os.environ.get("VIDEOQA_SLOW"):
        pytest.skip("test lento: exporta VIDEOQA_SLOW=1 para correrlo")


FIXTURE_OUT = Path(__file__).resolve().parent / "fixtures" / "out"


@pytest.fixture(scope="session")
def fixture_videos():
    return build_all(FIXTURE_OUT)
