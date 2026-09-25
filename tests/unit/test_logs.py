"""Registros: el general, el de cada video, los tiempos por etapa y el paquete de soporte."""
import json
import logging
import zipfile

import pytest

from tests.unit.test_espera import _Speller, _video_con_etapas_cacheadas
from videoqa import backends
from videoqa.claude_runner import run_claude
from videoqa.cli import main
from videoqa.config import load_rules, videoqa_home
from videoqa.job import Job
from videoqa.logs import log_level, setup_logging, support_bundle, tail, video_log
from videoqa.pipeline import process_video

log = logging.getLogger("videoqa")


@pytest.fixture(autouse=True)
def _restaura_logger():
    logger = logging.getLogger("videoqa")
    handlers, level = logger.handlers[:], logger.level
    yield
    for h in logger.handlers[:]:
        if h not in handlers:
            h.close()
            logger.removeHandler(h)
    logger.setLevel(level)


@pytest.mark.parametrize("valor, nivel", [
    (None, logging.INFO), ("debug", logging.DEBUG), (" WARNING ", logging.WARNING), ("nada", logging.INFO),
])
def test_log_level_desde_el_entorno(monkeypatch, valor, nivel):
    if valor is None:
        monkeypatch.delenv("VIDEOQA_LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("VIDEOQA_LOG_LEVEL", valor)
    assert log_level() == nivel


def test_setup_logging_sin_consola_solo_escribe_el_archivo(monkeypatch):
    monkeypatch.setenv("VIDEOQA_LOG_LEVEL", "DEBUG")
    setup_logging(console=False)
    logger = logging.getLogger("videoqa")
    assert logger.level == logging.DEBUG
    assert [type(h).__name__ for h in logger.handlers] == ["RotatingFileHandler"]
    log.debug("detalle fino")
    assert "detalle fino" in (videoqa_home() / "videoqa.log").read_text()


def test_video_log_solo_captura_mientras_dura(tmp_path):
    path = tmp_path / "registro.log"
    log.info("antes")
    with video_log(path):
        log.info("durante")
    log.info("después")
    texto = path.read_text()
    assert "durante" in texto and "antes" not in texto and "después" not in texto


def test_tail_problemas_conserva_el_traceback(tmp_path):
    path = tmp_path / "x.log"
    path.write_text("2026-09-25 10:00:00,000 INFO todo bien\n"
                    "2026-09-25 10:00:01,000 ERROR [reel] fallo\n"
                    "Traceback (most recent call last):\n"
                    "ValueError: roto\n"
                    "2026-09-25 10:00:02,000 INFO sigue\n")
    assert tail(path, problems_only=True) == ["2026-09-25 10:00:01,000 ERROR [reel] fallo",
                                              "Traceback (most recent call last):", "ValueError: roto"]
    assert tail(path, lines=1) == ["2026-09-25 10:00:02,000 INFO sigue"]
    assert tail(tmp_path / "no_existe.log") == []


def test_run_stage_guarda_y_registra_lo_que_tarda(tmp_path, caplog):
    job = Job(tmp_path / "v.mp4", tmp_path / "jobs")
    with caplog.at_level(logging.INFO, logger="videoqa"):
        job.run_stage("probe", "probe.json", lambda j: {"ok": True})
    assert isinstance(job.state()["stages"]["probe"]["seconds"], float)
    assert any("etapa probe: lista en" in r.getMessage() for r in caplog.records)


def test_el_registro_del_video_viaja_con_el_reporte(tmp_path):
    veredicto = json.dumps({"findings": [], "guion_real_md": "## Escena 1 [0:00]\nHola"})
    backends.register_speller(_Speller)
    try:
        video, s = _video_con_etapas_cacheadas(tmp_path)
        res = process_video(video, s, load_rules(), lambda p, c: veredicto)
    finally:
        backends.reset()
    assert res.status == "approved"
    texto = (res.dest / "registro.log").read_text()
    assert "[reel] inicio" in texto
    assert "juez: veredicto en" in texto
    assert "[reel] fin: approved en" in texto


def test_run_claude_registra_duracion_y_coste(monkeypatch, tmp_path, caplog):
    import subprocess

    salida = json.dumps({"result": "ok", "duration_ms": 42000, "total_cost_usd": 0.125,
                         "usage": {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 50}})
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=salida, stderr=""))
    with caplog.at_level(logging.INFO, logger="videoqa"):
        assert run_claude("p", tmp_path) == "ok"
    msg = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("claude -p:"))
    assert msg == "claude -p: 42 s, ~0.125 USD, 1000 tokens de entrada, 50 de salida"


def test_paquete_de_soporte_sin_config_ni_tokens(tmp_path):
    home = videoqa_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "videoqa.log").write_text("general\n")
    (home / "videoqa.log.1").write_text("viejo\n")
    (home / "launchd.err.log").write_text("launchd\n")
    (home / "config.yaml").write_text("secreto: 1\n")
    job_dir = tmp_path / "jobs" / "reel"
    job_dir.mkdir(parents=True)
    (job_dir / "registro.log").write_text("del video\n")
    (job_dir / "state.json").write_text("{}")
    out = support_bundle(tmp_path / "salida", job_dir)
    nombres = set(zipfile.ZipFile(out).namelist())
    assert nombres == {"info.txt", "videoqa.log", "videoqa.log.1", "launchd.err.log",
                       "video_reel/registro.log", "video_reel/state.json"}


def _drive(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_CONFIG", str(tmp_path / "config.yaml"))
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    return drive


def test_cli_registro_general_y_de_un_video(tmp_path, monkeypatch, capsys):
    _drive(tmp_path, monkeypatch)
    job_dir = videoqa_home() / "jobs" / "promo_octubre"
    job_dir.mkdir(parents=True)
    (job_dir / "registro.log").write_text("2026-09-25 10:00:00,000 WARNING [promo_octubre] ojo\n")
    capsys.readouterr()

    assert main(["registro", "--lineas", "0"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("REGISTRO ") and "videoqa.log" in out.splitlines()[0]

    assert main(["registro", "promo", "--problemas"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith("1 línea(s) (solo avisos y errores)")
    assert out[1].endswith("ojo")

    assert main(["registro", "no_existe"]) == 1
    assert "NO_ENCONTRADO" in capsys.readouterr().out


def test_cli_registro_video_sin_registro(tmp_path, monkeypatch, capsys):
    _drive(tmp_path, monkeypatch)
    (videoqa_home() / "jobs" / "viejo").mkdir(parents=True)
    capsys.readouterr()
    assert main(["registro", "viejo"]) == 0
    assert "SIN_REGISTRO" in capsys.readouterr().out


def test_cli_registro_paquete(tmp_path, monkeypatch, capsys):
    _drive(tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["registro", "--paquete", "--destino", str(tmp_path / "zip")]) == 0
    linea = capsys.readouterr().out.strip()
    assert linea.startswith("PAQUETE ") and linea.endswith(".zip")
    assert "videoqa.log" in zipfile.ZipFile(linea.split(" ", 1)[1]).namelist()
