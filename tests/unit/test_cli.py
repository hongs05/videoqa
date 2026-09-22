import json
import logging

import pytest
import yaml
from videoqa import cli
from videoqa.claude_runner import ClaudeError
from videoqa.cli import main, make_sheet
from videoqa.config import Settings, token_path, videoqa_home
from videoqa.pipeline import Result

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
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None, **kw: Result("approved", [], drive / "03_Aprobado" / "v"))
    assert main(["run", str(video)]) == 0

def test_run_copia_a_entrada_si_viene_de_fuera(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    fuera = tmp_path / "otra" / "clip.mp4"
    fuera.parent.mkdir()
    fuera.write_bytes(b"x")
    visto = {}

    import videoqa.cli as cli
    from videoqa.pipeline import Result

    def fake_process(video, settings, rules, runner, sheet=None, **kw):
        visto["video"] = video
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(fuera)]) == 0
    assert visto["video"] == drive / "01_Entrada" / "clip.mp4"
    assert fuera.exists(), "el original se conserva"
    assert "Copiado a 01_Entrada" in capsys.readouterr().out


def test_run_no_copia_si_ya_esta_en_entrada(tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    dentro = drive / "01_Entrada" / "clip.mp4"
    dentro.write_bytes(b"x")
    visto = {}

    import videoqa.cli as cli
    from videoqa.pipeline import Result

    def fake_process(video, settings, rules, runner, sheet=None, **kw):
        visto["video"] = video
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    main(["run", str(dentro)])
    assert visto["video"] == dentro


def test_run_returns_1_on_error(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "drive")])
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None, **kw: Result("error", [], None, "boom"))
    assert main(["run", str(tmp_path / "x.mp4")]) == 1


def test_run_hasta_juez_imprime_el_job_dir(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    capsys.readouterr()  # descarta la salida de `init`; solo interesa la de `run`
    video = drive / "01_Entrada" / "clip.mp4"
    video.write_bytes(b"x")
    visto = {}

    def fake_process(v, settings, rules, runner, sheet=None, modo="completo", veredicto_text=None):
        visto["modo"] = modo
        return Result("pending", [], None)
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(video), "--hasta-juez"]) == 0
    assert visto["modo"] == "preparar"
    assert capsys.readouterr().out.strip().startswith("JUEZ_PENDIENTE ")


def test_run_con_veredicto_lo_pasa_como_texto(tmp_path, monkeypatch):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "clip.mp4"
    video.write_bytes(b"x")
    ver = tmp_path / "veredicto.json"
    ver.write_text('{"findings": []}')
    visto = {}

    def fake_process(v, settings, rules, runner, sheet=None, modo="completo", veredicto_text=None):
        visto["texto"] = veredicto_text
        return Result("approved", [], drive / "03_Aprobado" / "clip")
    monkeypatch.setattr(cli, "process_video", fake_process)
    assert main(["run", str(video), "--veredicto", str(ver)]) == 0
    assert visto["texto"] == '{"findings": []}'


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


def test_doctor_ok_con_token(monkeypatch, capsys):
    token_path().parent.mkdir(parents=True, exist_ok=True)
    token_path().write_text("sk-ant-oat01-x")
    monkeypatch.setattr(cli, "run_claude", lambda *a, **k: "ok")
    assert cli.main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "CRITERIO OK · sesión guardada"
    assert json.loads((videoqa_home() / "doctor.json").read_text())["ok"] is True


def test_doctor_ok_sin_token(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_claude", lambda *a, **k: "ok")
    assert cli.main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "CRITERIO OK · sesión del CLI"


def test_doctor_falla_si_claude_no_responde(monkeypatch, capsys):
    def boom(*a, **k):
        raise ClaudeError("claude -p salió con 1: Failed to authenticate: OAuth session expired")
    monkeypatch.setattr(cli, "run_claude", boom)
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith("CRITERIO SIN SESIÓN · la sesión caducó o no está guardada")
    assert json.loads((videoqa_home() / "doctor.json").read_text())["ok"] is False


def test_doctor_falla_si_no_hay_binario(monkeypatch, capsys):
    def boom(*a, **k):
        raise ClaudeError("no se pudo ejecutar claude: [Errno 2] No such file")
    monkeypatch.setattr(cli, "run_claude", boom)
    assert cli.main(["doctor"]) == 1
    assert "no encuentro el programa claude" in capsys.readouterr().out


def test_doctor_falla_ante_un_error_inesperado(monkeypatch, capsys):
    # Un fallo que no es ClaudeError (p. ej. un timeout de red al margen del propio
    # subprocess) no debe tirar `videoqa doctor` con una traza: se reporta igual.
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "run_claude", boom)
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out.strip()
    assert out.startswith("CRITERIO SIN SESIÓN · no pude comprobarlo")
    assert json.loads((videoqa_home() / "doctor.json").read_text())["ok"] is False
