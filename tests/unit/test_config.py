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


def test_load_all_settings_sin_extras_devuelve_una(tmp_path):
    from videoqa.config import load_all_settings

    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\n")
    todas = load_all_settings(cfg)
    assert len(todas) == 1 and todas[0].drive_root == Path("/tmp/drive")


def test_load_all_settings_con_carpetas_extra(tmp_path):
    from videoqa.config import load_all_settings

    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\ncarpetas_extra:\n  - ~/Documentos/MisPruebas\n  - /tmp/otra\n")
    todas = load_all_settings(cfg)
    assert [s.drive_root for s in todas] == [Path("/tmp/drive"),
                                             Path.home() / "Documentos" / "MisPruebas",
                                             Path("/tmp/otra")]


def test_las_carpetas_extra_comparten_jobs_y_motor_pero_no_el_sheet(tmp_path):
    """El Sheet es el tablero del equipo: solo lo alimenta la carpeta principal."""
    from videoqa.config import load_all_settings

    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\nsheet_id: abc\nwhisper_model: modelo-x\n"
                   "carpetas_extra:\n  - /tmp/local\n")
    principal, extra = load_all_settings(cfg)
    assert principal.sheet_id == "abc"
    assert extra.sheet_id is None, "una carpeta local no debe escribir en el tablero del equipo"
    assert extra.jobs_dir == principal.jobs_dir
    assert extra.whisper_model == "modelo-x" == principal.whisper_model


def test_carpetas_extra_vacia_o_ausente(tmp_path):
    from videoqa.config import load_all_settings

    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\ncarpetas_extra: []\n")
    assert len(load_all_settings(cfg)) == 1


def test_carpeta_extra_repetida_se_ignora(tmp_path):
    from videoqa.config import load_all_settings

    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\ncarpetas_extra:\n  - /tmp/drive\n  - /tmp/local\n")
    todas = load_all_settings(cfg)
    assert [s.drive_root for s in todas] == [Path("/tmp/drive"), Path("/tmp/local")]
