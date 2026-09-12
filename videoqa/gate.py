from __future__ import annotations

import shutil
from pathlib import Path

from videoqa.config import Settings
from videoqa.findings import Finding
from videoqa.job import Job


def decide(findings: list[Finding]) -> str:
    return "rejected" if any(f.severity == "blocker" for f in findings) else "approved"


def deliver(job: Job, settings: Settings, status: str) -> Path:
    base = settings.aprobado if status == "approved" else settings.con_errores
    dest = base / job.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.move(str(job.video), dest / job.video.name)
    for name in ("reporte.md", "guion_real.md"):
        src = job.path(name)
        if src.exists():
            shutil.copy2(src, dest / name)
    ev = job.path("evidencia")
    if ev.exists():
        shutil.copytree(ev, dest / "evidencia")
    return dest
