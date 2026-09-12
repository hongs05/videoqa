from pathlib import Path
import pytest
from videoqa.config import Settings, load_settings, load_rules, videoqa_home

def test_load_settings_from_yaml(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\nsheet_id: abc\n")
    s = load_settings(cfg)
    assert s.drive_root == Path("/tmp/drive")
    assert s.entrada == Path("/tmp/drive/01_Entrada")
    assert s.con_errores == Path("/tmp/drive/02_Con_errores")
    assert s.aprobado == Path("/tmp/drive/03_Aprobado")
    assert s.config_dir == Path("/tmp/drive/_config")
    assert s.sheet_id == "abc"
    assert s.service_account_json is None
    assert s.claude_bin == "claude"
    assert s.jobs_dir == videoqa_home() / "jobs"


def test_jobs_dir_default_honors_videoqa_home(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_HOME", str(tmp_path / "custom_home"))
    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\n")
    s = load_settings(cfg)
    assert s.jobs_dir == tmp_path / "custom_home" / "jobs"

def test_load_settings_requires_drive_root(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sheet_id: abc\n")
    with pytest.raises(ValueError):
        load_settings(cfg)

def test_load_rules_default():
    rules = load_rules()
    assert rules["severities"]["brand_color"] == "blocker"
