"""El script corre `claude setup-token` y guarda el token. Se prueba con un
`claude` falso en PATH y un `uv` falso para no depender de nada instalado."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "instalar" / "guardar-token.command"


def _bin_falso(tmp_path: Path, salida_setup_token: str, doctor_exit: int = 0) -> Path:
    b = tmp_path / "bin"
    b.mkdir()
    (b / "claude").write_text(f"#!/bin/bash\nif [ \"$1\" = setup-token ]; then printf '%s\\n' \"$SALIDA\"; fi\n")
    (b / "uv").write_text(f"#!/bin/bash\necho 'CRITERIO OK · sesión guardada'\nexit {doctor_exit}\n")
    for f in ("claude", "uv"):
        (b / f).chmod((b / f).stat().st_mode | stat.S_IEXEC)
    return b


def _run(tmp_path: Path, salida: str, stdin: str = "", doctor_exit: int = 0):
    b = _bin_falso(tmp_path, salida, doctor_exit)
    (tmp_path / "videoqa").mkdir(exist_ok=True)
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "VIDEOQA_HOME": str(tmp_path / "home"),
           "HOME": str(tmp_path), "SALIDA": salida, "GUARDAR_TOKEN_SIN_PAUSA": "1"}
    return subprocess.run(["bash", str(SCRIPT)], input=stdin, capture_output=True, text=True, env=env)


def test_guarda_el_token_de_la_salida(tmp_path):
    res = _run(tmp_path, "Bla bla\nsk-ant-oat01-ABCdef_123-xyz\nListo")
    assert res.returncode == 0, res.stdout + res.stderr
    tok = tmp_path / "home" / "token"
    assert tok.read_text() == "sk-ant-oat01-ABCdef_123-xyz\n"
    assert stat.S_IMODE(tok.stat().st_mode) == 0o600
    assert "guardada" in res.stdout.lower()
    assert "CRITERIO OK" in res.stdout


def test_si_no_hay_token_en_la_salida_lo_pide(tmp_path):
    res = _run(tmp_path, "no salio nada", stdin="sk-ant-oat01-pegado\n")
    assert res.returncode == 0, res.stdout + res.stderr
    assert (tmp_path / "home" / "token").read_text() == "sk-ant-oat01-pegado\n"


def test_sin_token_ni_pegado_falla_claro(tmp_path):
    res = _run(tmp_path, "nada", stdin="\n")
    assert res.returncode == 1
    assert "no se guardó" in res.stdout.lower()
    assert not (tmp_path / "home" / "token").exists()


def test_es_ejecutable():
    assert SCRIPT.stat().st_mode & 0o111
