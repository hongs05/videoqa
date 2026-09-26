from __future__ import annotations

import shutil
from datetime import datetime
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


def _keep_previous(dest: Path, base: Path) -> Path:
    """Aparta una entrega anterior con el mismo nombre en `_anteriores/`.

    El flujo normal es que el editor corrija y resuba el video con el mismo nombre; la
    versión anterior (video + reporte + evidencia) ya fue revisada y no se borra nunca:
    puede estar publicada o servir para comparar qué cambió.
    """
    keep = base / "_anteriores"
    keep.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = keep / f"{dest.name}_{stamp}"
    n = 1
    while target.exists():
        n += 1
        target = keep / f"{dest.name}_{stamp}_{n}"
    shutil.move(str(dest), target)
    return target


def deliver(job: Job, settings: Settings, status: str, client: str | None = None) -> Path:
    _check_safe_name(job)
    base = settings.aprobado if status == "approved" else settings.con_errores
    if client:
        # Mismo orden que en Entrada: 02_Con_errores/<Cliente>/<video>/.
        check_safe_stem(client, client)
        base = base / client
    dest = base / job.name
    base.mkdir(parents=True, exist_ok=True)
    if dest.resolve().parent != base.resolve():
        raise ValueError(f"nombre de video inseguro: {job.video.name!r}")
    if dest.exists():
        _keep_previous(dest, base)
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
    # El brief de la pieza (mismo nombre, .txt/.md) viaja con el video: así un reintento
    # desde 02_Con_errores lo sigue teniendo al lado.
    from videoqa.profiles import brief_path

    brief = brief_path(job.video)
    if brief is not None:
        shutil.move(str(brief), dest / brief.name)
    return dest
