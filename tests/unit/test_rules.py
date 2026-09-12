from pathlib import Path
import yaml

RULES = Path(__file__).resolve().parents[2] / "reglas.yaml"

def test_rules_have_required_sections():
    data = yaml.safe_load(RULES.read_text())
    assert set(data) >= {"severities", "thresholds", "frames", "claude"}
    assert all(v in {"blocker", "warning", "info"} for v in data["severities"].values())
    assert data["frames"]["fps"] == 2
