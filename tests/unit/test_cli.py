import logging

import pytest
import yaml
from videoqa.cli import main, make_sheet
from videoqa.config import Settings

def test_init_writes_config_and_folders(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "Revision_Videos"
    assert main(["init", "--drive-root", str(drive), "--sheet-id", "abc"]) == 0
    data = yaml.safe_load(cfg.read_text())
    assert data["drive_root"] == str(drive) and data["sheet_id"] == "abc"
    for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
        assert (drive / d).is_dir()

def test_run_uses_injected_process(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "v.mp4"; video.write_bytes(b"x")
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("approved", [], drive / "03_Aprobado" / "v"))
    assert main(["run", str(video)]) == 0

def test_run_returns_1_on_error(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "drive")])
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("error", [], None, "boom"))
    assert main(["run", str(tmp_path / "x.mp4")]) == 1


@pytest.mark.parametrize("kwargs,falta", [
    ({"sheet_id": "abc"}, "service_account_json"),
    ({"service_account_json": "/tmp/sa.json"}, "sheet_id"),
])
def test_make_sheet_warns_on_half_configuration(tmp_path, caplog, kwargs, falta):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs", **kwargs)
    with caplog.at_level(logging.WARNING, logger="videoqa"):
        writer = make_sheet(s)
    assert writer.factory is None
    assert any(falta in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_make_sheet_silent_when_fully_configured_or_absent(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="videoqa"):
        assert make_sheet(Settings(drive_root=tmp_path / "d", jobs_dir=tmp_path / "j")).factory is None
        assert make_sheet(Settings(drive_root=tmp_path / "d", jobs_dir=tmp_path / "j",
                                   sheet_id="abc", service_account_json="/tmp/sa.json")).factory is not None
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_init_guarda_las_carpetas_extra(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "Drive"
    local = tmp_path / "MisPruebas"
    assert main(["init", "--drive-root", str(drive), "--carpeta-extra", str(local)]) == 0
    data = yaml.safe_load(cfg.read_text())
    assert data["carpetas_extra"] == [str(local)]
    # las subcarpetas se crean en las dos
    for raiz in (drive, local):
        for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
            assert (raiz / d).is_dir(), f"falta {d} en {raiz}"


def test_init_acepta_varias_carpetas_extra(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    a, b = tmp_path / "a", tmp_path / "b"
    main(["init", "--drive-root", str(tmp_path / "d"),
          "--carpeta-extra", str(a), "--carpeta-extra", str(b)])
    assert yaml.safe_load(cfg.read_text())["carpetas_extra"] == [str(a), str(b)]


def test_init_sin_extras_no_escribe_la_clave(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "d")])
    assert "carpetas_extra" not in yaml.safe_load(cfg.read_text())


def test_watch_vigila_todas_las_carpetas(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "d"), "--carpeta-extra", str(tmp_path / "local")])

    import videoqa.cli as cli

    recibidas = {}

    def fake_watch(settings, rules, runner, sheet=None, once=False):
        recibidas["carpetas"] = [s.drive_root for s in settings]

    monkeypatch.setattr(cli, "watch", fake_watch)
    assert main(["watch", "--once"]) == 0
    assert recibidas["carpetas"] == [tmp_path / "d", tmp_path / "local"]
