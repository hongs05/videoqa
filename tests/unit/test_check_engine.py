"""El hook saluda con una línea de estado. Se ejecuta con HOME/VIDEOQA_HOME
falsos y un `claude`/`launchctl` falsos en PATH."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "plugins" / "aura" / "scripts" / "check-engine.sh"


def _entorno(tmp_path: Path, auth_exit: int = 1) -> dict:
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "claude").write_text(f"#!/bin/bash\nexit {auth_exit}\n")
    (b / "launchctl").write_text("#!/bin/bash\nexit 1\n")
    for f in ("claude", "launchctl"):
        (b / f).chmod((b / f).stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    (home / "videoqa").mkdir(parents=True)
    vq = home / ".videoqa"
    vq.mkdir()
    drive = tmp_path / "drive"
    (drive / "01_Entrada").mkdir(parents=True)
    (vq / "config.yaml").write_text(f"drive_root: {drive}\n")
    return {**os.environ, "HOME": str(home), "PATH": f"{b}:/usr/bin:/bin", "VIDEOQA_HOME": str(vq)}


def _run(env: dict) -> str:
    res = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env)
    assert res.returncode == 0
    return res.stdout.strip()


def test_sin_token_y_sin_sesion_avisa(tmp_path):
    out = _run(_entorno(tmp_path, auth_exit=1))
    assert "sesión de Claude caducada" in out and "arregla la sesión" in out


def test_sin_token_con_sesion_del_cli_ok(tmp_path):
    out = _run(_entorno(tmp_path, auth_exit=0))
    assert "sesión OK" in out


def test_con_token_ok_sin_lanzar_claude(tmp_path):
    env = _entorno(tmp_path, auth_exit=1)
    (Path(env["VIDEOQA_HOME"]) / "token").write_text("sk-ant-oat01-x\n")
    assert "sesión OK" in _run(env)


def test_doctor_reciente_en_falso_gana_al_token(tmp_path):
    env = _entorno(tmp_path)
    vq = Path(env["VIDEOQA_HOME"])
    (vq / "token").write_text("sk-ant-oat01-x\n")
    viejo = time.time() - 3600
    os.utime(vq / "token", (viejo, viejo))
    (vq / "doctor.json").write_text(json.dumps({"ok": False, "motivo": "caducó", "at": "x"}))
    assert "caducada" in _run(env)


def test_doctor_viejo_en_falso_no_gana_a_un_token_nuevo(tmp_path):
    env = _entorno(tmp_path)
    vq = Path(env["VIDEOQA_HOME"])
    (vq / "doctor.json").write_text(json.dumps({"ok": False, "motivo": "caducó", "at": "x"}))
    viejo = time.time() - 3600
    os.utime(vq / "doctor.json", (viejo, viejo))
    (vq / "token").write_text("sk-ant-oat01-x\n")
    assert "sesión OK" in _run(env)


def test_cuenta_solo_videos(tmp_path):
    env = _entorno(tmp_path, auth_exit=0)
    entrada = tmp_path / "drive" / "01_Entrada"
    (entrada / ".DS_Store").write_text("")
    (entrada / "notas.txt").write_text("")
    (entrada / "a.mp4").write_text("")
    (entrada / "b.MOV").write_text("")
    assert "2 videos pendientes" in _run(env)


def test_sin_videos(tmp_path):
    assert "sin videos pendientes" in _run(_entorno(tmp_path, auth_exit=0))
