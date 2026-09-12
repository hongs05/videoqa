from __future__ import annotations

import os
import shutil
from pathlib import Path

from videoqa.config import Settings
from videoqa.findings import Finding
from videoqa.job import Job

_UNSAFE_NAMES = {"", ".", ".."}
_SEPARATORS = {"/", os.sep, os.altsep} - {None}


def decide(findings: list[Finding]) -> str:
    return "rejected" if any(f.severity == "blocker" for f in findings) else "approved"


def _check_safe_name(job: Job) -> None:
    """`job.name` es el *stem* del video y se usa como nombre de carpeta destino.

    Un video llamado ``...mp4`` tiene stem ``..``, y ``base / ".."`` es la raíz de
    Drive: borrarla con rmtree destruiría `01_Entrada/`, `02_Con_errores/` y
    `03_Aprobado/`. Se valida antes de tocar nada.
    """
    name = job.name
    if name in _UNSAFE_NAMES or any(sep in name for sep in _SEPARATORS):
        raise ValueError(f"nombre de video inseguro: {job.video.name!r}")


def deliver(job: Job, settings: Settings, status: str) -> Path:
    _check_safe_name(job)
    base = settings.aprobado if status == "approved" else settings.con_errores
    dest = base / job.name
    base.mkdir(parents=True, exist_ok=True)
    if dest.resolve().parent != base.resolve():
        raise ValueError(f"nombre de video inseguro: {job.video.name!r}")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    # Primero los artefactos, el video AL FINAL: si copiar reporte/guion/evidencia falla,
    # el video sigue en 01_Entrada/ y el watcher puede reintentar en vez de dejarlo en
    # una carpeta de destino a medio armar.
    for name in ("reporte.md", "guion_real.md"):
        src = job.path(name)
        if src.exists():
            shutil.copy2(src, dest / name)
    ev = job.path("evidencia")
    if ev.exists():
        shutil.copytree(ev, dest / "evidencia")
    shutil.move(str(job.video), dest / job.video.name)
    return dest
