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


def wait_state_path() -> Path:
    return videoqa_home() / "espera.json"


def write_wait_state(until: datetime, video: str, respaldo: bool = False) -> Path:
    """Apunta que Claude no tiene uso hasta `until` y qué videos esperan por eso.

    Lo leen el watcher (para no gastar intentos antes de esa hora, también tras reiniciarse)
    y el hook SessionStart de Aura (para avisar de cuántos videos están en espera).
    """
    path = wait_state_path()
    videos: list[str] = []
    try:
        videos = list(json.loads(path.read_text()).get("videos", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        videos = []
    if video and video not in videos:
        videos.append(video)
    path.parent.mkdir(parents=True, exist_ok=True)
    # `respaldo`: el juez local está cubriendo la espera (los videos no se quedan parados).
    path.write_text(json.dumps({"hasta": until.isoformat(timespec="minutes"), "hasta_ts": int(until.timestamp()),
                                "videos": videos, "respaldo": respaldo}, ensure_ascii=False))
    return path


def load_wait_until() -> float | None:
    """Epoch hasta el que Claude está sin uso, o None si no hay espera registrada."""
    try:
        return float(json.loads(wait_state_path().read_text())["hasta_ts"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def clear_wait_state() -> None:
    wait_state_path().unlink(missing_ok=True)
