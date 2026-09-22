from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from videoqa.config import videoqa_home


def write_doctor_state(ok: bool, motivo: str) -> Path:
    """Escribe ``<videoqa_home>/doctor.json`` con el mismo formato que ``videoqa doctor``.

    Lo usan tanto `cmd_doctor` (comprobación explícita) como el pipeline (cuando el juez
    falla por sesión caducada), para que el hook SessionStart de la próxima sesión avise
    sin esperar a que alguien lance `videoqa doctor` a mano.
    """
    home = videoqa_home()
    home.mkdir(parents=True, exist_ok=True)
    path = home / "doctor.json"
    path.write_text(json.dumps(
        {"ok": ok, "motivo": motivo, "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False))
    return path
