"""Límite de uso de Claude: el video espera en Entrada en vez de salir con errores falsos."""
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from videoqa import backends, cli
from videoqa.claude_runner import ClaudeError, UsageLimitError, parse_reset, run_claude
from videoqa.config import Settings, load_rules, videoqa_home
from videoqa.doctor_state import load_wait_until, write_wait_state
from videoqa.job import Job
from videoqa.pipeline import Result, process_video
from videoqa.watcher import watch

MANAGUA = ZoneInfo("America/Managua")
MSG = "You've hit your session limit · resets 7:20pm (America/Managua)"


# --- Detectar el límite y la hora --------------------------------------------------------

def test_parse_reset_con_zona_horaria():
    now = datetime(2026, 9, 22, 15, 0, tzinfo=MANAGUA)
    assert parse_reset(MSG, now) == datetime(2026, 9, 22, 19, 20, tzinfo=MANAGUA)


def test_parse_reset_si_la_hora_ya_paso_es_manana():
    now = datetime(2026, 9, 22, 21, 0, tzinfo=MANAGUA)
    assert parse_reset(MSG, now) == datetime(2026, 9, 23, 19, 20, tzinfo=MANAGUA)


@pytest.mark.parametrize("texto, hora", [
    ("5-hour limit reached ∙ resets 3am", (3, 0)),
    ("Claude usage limit reached. Your limit will reset at 12pm", (12, 0)),
    ("session limit · resets 12:30am", (0, 30)),
])
def test_parse_reset_formatos(texto, hora):
    when = parse_reset(texto, datetime(2026, 9, 22, 13, 0, tzinfo=MANAGUA))
    assert (when.hour, when.minute) == hora


def test_parse_reset_sin_hora():
    assert parse_reset("You've hit your session limit") is None


def _fake_claude(monkeypatch, returncode, stdout, stderr=""):
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr))


def test_run_claude_distingue_el_limite(monkeypatch, tmp_path):
    _fake_claude(monkeypatch, 1, json.dumps({"is_error": True, "result": MSG}))
    with pytest.raises(UsageLimitError) as e:
        run_claude("p", tmp_path)
    assert e.value.resets_at is not None and (e.value.resets_at.hour, e.value.resets_at.minute) == (19, 20)


def test_run_claude_otros_fallos_no_son_limite(monkeypatch, tmp_path):
    _fake_claude(monkeypatch, 1, "", "Failed to authenticate: OAuth session expired")
    with pytest.raises(ClaudeError) as e:
        run_claude("p", tmp_path)
    assert not isinstance(e.value, UsageLimitError)


# --- Pipeline: el video se queda en Entrada ----------------------------------------------

class _Speller:
    def unknown(self, words):
        return set()

    def correction(self, w):
        return None


def _video_con_etapas_cacheadas(tmp_path) -> tuple[Path, Settings]:
    """Video cuyo job ya tiene probe/transcripción/OCR hechos: el pipeline no toca ffmpeg."""
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    s.config_dir.mkdir(parents=True)
    video = s.entrada / "reel.mp4"
    video.write_bytes(b"video")
    job = Job(video, s.jobs_dir)
    job.record_video()
    (job.dir / "frames").mkdir()
    Image.new("RGB", (108, 192), (30, 30, 30)).save(job.path("frames/sec_0001.jpg"))
    etapas = {
        "probe.json": {"duration": 10.0, "width": 1080, "height": 1920, "has_audio": True},
        "transcript.json": {"language": "es", "text": "hola", "segments": [{"start": 0, "end": 2, "text": "hola"}]},
        "technical.json": {"black": [], "freeze": [], "scene_cuts": [], "silence": [], "audio": None},
        "frames.json": {"fps": 2, "period": 0.5, "frames": [{"file": "frames/sec_0001.jpg", "t": 0.0, "kind": "second"}]},
        "ocr.json": {"raw": [], "appearances": []},
        "ocr_color.json": {"raw": [], "appearances": []},
    }
    for name, data in etapas.items():
        job.path(name).write_text(json.dumps(data))
    return video, s


def _runner_sin_uso(prompt, cwd):
    raise UsageLimitError(MSG, datetime(2026, 9, 22, 19, 20, tzinfo=MANAGUA))


def test_sin_uso_el_video_espera_en_entrada_sin_reporte(tmp_path):
    backends.register_speller(_Speller)
    try:
        video, s = _video_con_etapas_cacheadas(tmp_path)
        llamadas = []
        res = process_video(video, s, load_rules(), lambda p, c: llamadas.append(1) or _runner_sin_uso(p, c))
    finally:
        backends.reset()
    assert res.status == "waiting" and res.dest is None
    assert res.retry_at == datetime(2026, 9, 22, 19, 20, tzinfo=MANAGUA)
    assert video.exists(), "el video tiene que seguir en 01_Entrada"
    assert not any(s.con_errores.glob("*")) if s.con_errores.exists() else True
    assert len(llamadas) == 1, "con el límite no se gasta un segundo intento"
    espera = json.loads((videoqa_home() / "espera.json").read_text())
    assert espera["videos"] == ["reel.mp4"] and espera["hasta"].startswith("2026-09-22T19:20")


def test_cuando_claude_vuelve_se_borra_la_espera(tmp_path):
    write_wait_state(datetime(2026, 9, 22, 19, 20, tzinfo=MANAGUA), "otro.mp4")
    veredicto = json.dumps({"findings": [], "guion_real_md": "## Escena 1 [0:00]\nHola"})
    backends.register_speller(_Speller)
    try:
        video, s = _video_con_etapas_cacheadas(tmp_path)
        res = process_video(video, s, load_rules(), lambda p, c: veredicto)
    finally:
        backends.reset()
    assert res.status == "approved"
    assert load_wait_until() is None


# --- Watcher: pausa toda la cola -----------------------------------------------------------

def _settings_con_videos(tmp_path, *nombres):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    for n in nombres:
        (s.entrada / n).write_bytes(b"1")
    return s


def test_watch_pausa_la_cola_hasta_que_vuelve_el_uso(tmp_path):
    s = _settings_con_videos(tmp_path, "a.mp4", "b.mp4")
    vistos = []

    def fake_process(video, settings, rules, runner, sheet=None):
        vistos.append(video.name)
        return Result("waiting", [], None, "límite", retry_at=datetime.now().astimezone().replace(year=2099))

    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert vistos == ["a.mp4"], "tras el límite no se intenta el siguiente"
    assert not (s.jobs_dir / "watch_failed.json").exists() or json.loads((s.jobs_dir / "watch_failed.json").read_text()) == {}


def test_watch_respeta_la_espera_guardada_tras_reiniciarse(tmp_path):
    s = _settings_con_videos(tmp_path, "a.mp4")
    write_wait_state(datetime(2099, 1, 1, tzinfo=MANAGUA), "a.mp4")
    vistos = []
    watch(s, {}, runner=lambda p, c: "", once=True, sleep=lambda x: None, stable_wait_s=0,
          process=lambda v, *a, **k: vistos.append(v.name) or Result("approved", [], None))
    assert vistos == []


def test_watch_sigue_si_la_espera_ya_paso(tmp_path):
    s = _settings_con_videos(tmp_path, "a.mp4")
    write_wait_state(datetime(2020, 1, 1, tzinfo=MANAGUA), "a.mp4")
    vistos = []
    watch(s, {}, runner=lambda p, c: "", once=True, sleep=lambda x: None, stable_wait_s=0,
          process=lambda v, *a, **k: vistos.append(v.name) or Result("approved", [], None))
    assert vistos == ["a.mp4"]


# --- CLI ---------------------------------------------------------------------------------

def test_run_avisa_de_la_espera(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    cli.main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(cli, "process_video", lambda *a, **k: Result(
        "waiting", [], None, "límite", retry_at=datetime(2026, 9, 22, 19, 20, tzinfo=MANAGUA)))
    assert cli.main(["run", str(video)]) == 3
    assert "EN_ESPERA hasta 19:20" in capsys.readouterr().out


def test_doctor_con_limite_no_dice_sesion_caducada(monkeypatch, capsys):
    def sin_uso(*a, **k):
        raise UsageLimitError(MSG, datetime(2099, 9, 22, 19, 20, tzinfo=MANAGUA))
    monkeypatch.setattr(cli, "run_claude", sin_uso)
    assert cli.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "CRITERIO OK" in out and "sin uso disponible hasta las 19:20" in out
