"""Registros de videoqa: el general y uno por video.

- ``~/.videoqa/videoqa.log``: todo lo que hace el motor (rota a los 5 MB, guarda 3).
- ``registro.log`` en la carpeta de trabajo de cada video: solo lo de ese video, con lo
  que tardó cada etapa. Viaja con el reporte a ``02_Con_errores``/``03_Aprobado``.

``VIDEOQA_LOG_LEVEL=DEBUG`` sube el detalle (por defecto INFO).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import sys
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from videoqa.config import videoqa_home

LOGGER = "videoqa"
MAIN_LOG = "videoqa.log"
VIDEO_LOG = "registro.log"
LAUNCHD_LOGS = ("launchd.out.log", "launchd.err.log")
FORMAT = "%(asctime)s %(levelname)s %(message)s"
_PROBLEMS = ("WARNING", "ERROR", "CRITICAL")
# Los registros de launchd no rotan: en el paquete de soporte basta con el final.
_BUNDLE_TAIL_BYTES = 2_000_000


def log_level() -> int:
    """Nivel pedido en VIDEOQA_LOG_LEVEL (DEBUG, INFO, WARNING…); INFO si no vale."""
    level = logging.getLevelName(os.environ.get("VIDEOQA_LOG_LEVEL", "INFO").strip().upper())
    return level if isinstance(level, int) else logging.INFO


def setup_logging(console: bool = True) -> None:
    """Registro general en ~/.videoqa/videoqa.log y, si *console*, también por stderr."""
    log_dir = videoqa_home()
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(FORMAT)
    root = logging.getLogger(LOGGER)
    root.setLevel(log_level())
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    fh = logging.handlers.RotatingFileHandler(log_dir / MAIN_LOG, maxBytes=5_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)


@contextmanager
def video_log(path: Path) -> Iterator[None]:
    """Mientras dure el bloque, copia todo lo que se registra a *path* (se añade al final).

    Los videos se revisan de uno en uno, así que todo lo registrado mientras tanto es de
    ese video (incluidos los avisos del Sheet o del juez).
    """
    logger = logging.getLogger(LOGGER)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    previous = logger.level
    if logger.level == logging.NOTSET:  # sin setup_logging (uso como librería, tests)
        logger.setLevel(log_level())
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous)


def tail(path: Path, lines: int = 40, problems_only: bool = False) -> list[str]:
    """Últimas *lines* líneas de un registro; con *problems_only*, solo avisos y errores.

    Las líneas de continuación (un traceback) van con la línea a la que pertenecen.
    """
    if not path.exists():
        return []
    out: list[str] = []
    keep = not problems_only
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(" ", 3)
        is_entry = len(parts) >= 3 and parts[2] in ("DEBUG", "INFO", *_PROBLEMS)
        if is_entry:
            keep = not problems_only or parts[2] in _PROBLEMS
        if keep:
            out.append(line)
    return out[-lines:] if lines > 0 else out


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("videoqa")
    except Exception:  # noqa: BLE001 — motor sin instalar como paquete
        return "desconocida"


def support_bundle(dest_dir: Path, job_dir: Path | None = None) -> Path:
    """Zip con los registros para mandar a soporte. Nunca incluye config ni tokens."""
    home = videoqa_home()
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"videoqa_registros_{datetime.now():%Y%m%d_%H%M%S}.zip"
    info = [
        f"fecha: {datetime.now().isoformat(timespec='seconds')}",
        f"videoqa: {_version()}",
        f"python: {platform.python_version()}",
        f"sistema: {platform.platform()} ({platform.machine()})",
        f"VIDEOQA_LOG_LEVEL: {os.environ.get('VIDEOQA_LOG_LEVEL', 'INFO')}",
    ]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", "\n".join(info) + "\n")
        for p in sorted(home.glob(MAIN_LOG + "*")):
            z.write(p, p.name)
        for name in LAUNCHD_LOGS:
            p = home / name
            if p.exists():
                with p.open("rb") as f:
                    f.seek(max(0, p.stat().st_size - _BUNDLE_TAIL_BYTES))
                    z.writestr(name, f.read())
        if job_dir is not None:
            for name in (VIDEO_LOG, "state.json"):
                p = job_dir / name
                if p.exists():
                    z.write(p, f"video_{job_dir.name}/{name}")
    return out
