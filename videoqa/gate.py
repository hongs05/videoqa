from __future__ import annotations

import shutil
from pathlib import Path

from videoqa.config import Settings
from videoqa.findings import Finding
from videoqa.job import Job, check_safe_stem


def decide(findings: list[Finding]) -> str:
    return "rejected" if any(f.severity == "blocker" for f in findings) else "approved"


def _check_safe_name(job: Job) -> None:
    """Guarda redundante con la de `Job.__init__`, a propósito.

    `job.name` es el *stem* del video y da nombre a la carpeta destino: `base / ".."`
    es la raíz de Drive y borrarla con rmtree destruiría `01_Entrada/`,
    `02_Con_errores/` y `03_Aprobado/`. Se revalida aquí por si el Job llegara
    construido/mutado por otra vía.
    """
    check_safe_stem(job.name, job.video.name)


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
    for name in ("reporte.md", "reporte.html", "guion_real.md"):
        src = job.path(name)
        if src.exists():
            shutil.copy2(src, dest / name)
    ev = job.path("evidencia")
    if ev.exists():
        shutil.copytree(ev, dest / "evidencia")
    shutil.move(str(job.video), dest / job.video.name)
    return dest
