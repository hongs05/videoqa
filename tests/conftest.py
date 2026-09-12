import os
import pytest

def pytest_runtest_setup(item):
    if "slow" in item.keywords and not os.environ.get("VIDEOQA_SLOW"):
        pytest.skip("test lento: exporta VIDEOQA_SLOW=1 para correrlo")
