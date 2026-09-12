from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SEVERITIES = ("blocker", "warning", "info")
SEVERITY_ORDER = {s: i for i, s in enumerate(SEVERITIES)}
TYPES = ("ortografia", "marca", "inconsistencia", "blooper", "tecnico")


@dataclass
class Finding:
    id: str
    type: str
    severity: str
    t_start: float
    t_end: float
    title: str
    detail: str
    suggestion: str = ""
    frame: str | None = None        # ruta relativa al job dir (frames/sec_0003.jpg)
    bbox: list[float] | None = None  # [x, y, w, h] normalizado, origen arriba-izquierda
    source: str = "code"            # code | claude
    check: str = ""                 # clave en reglas.yaml

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def save_findings(path: Path, findings: list[Finding]) -> None:
    path.write_text(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))


def load_findings(path: Path) -> list[Finding]:
    return [Finding.from_dict(d) for d in json.loads(path.read_text())]


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.t_start))


def count_by_severity(findings: list[Finding]) -> dict[str, int]:
    counts = {s: 0 for s in SEVERITIES}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts
