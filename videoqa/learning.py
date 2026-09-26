"""Correcciones del equipo: la memoria con la que el juez aprende de sus errores.

Cuando alguien dice "eso no es error" (o "se te pasó esto"), la corrección se guarda en
`<drive_root>/_config/aprendizaje.jsonl`, junto al glosario, para que la compartan todas
las Macs que revisan desde la misma carpeta de Drive.

No son reglas de código: en cada revisión el juez recibe las correcciones que más se
parecen al video que tiene delante y las aplica por analogía ("el logo de una camiseta no
es una falta" sirve para cualquier camiseta, no solo para la del ejemplo).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from videoqa.findings import Finding

log = logging.getLogger("videoqa")

FILE_NAME = "aprendizaje.jsonl"
KINDS = ("falso_positivo", "no_detectado")
MAX_RELEVANT = 20

_WORD = re.compile(r"[a-záéíóúüñ0-9]+", re.I)
# Palabras vacías: no dicen nada sobre de qué trata una corrección.
_STOP = {"de", "la", "el", "en", "y", "a", "que", "es", "un", "una", "los", "las", "no", "se", "por", "con",
         "para", "del", "al", "lo", "su", "texto", "pantalla", "posible", "error", "video"}
_SPELL_CHECKS = {"spelling_unknown_word", "spelling_glued_words"}


def path_for(config_dir: Path) -> Path:
    return config_dir / FILE_NAME


def _tokens(text: str) -> set[str]:
    return {w for w in (t.lower() for t in _WORD.findall(text or "")) if len(w) > 2 and w not in _STOP}


def words_of(finding: dict) -> list[str]:
    """Palabras marcadas por un hallazgo de ortografía ("Posible error ortográfico: a, b")."""
    if finding.get("check") not in _SPELL_CHECKS or ":" not in finding.get("title", ""):
        return []
    return [w.strip() for w in finding["title"].split(":", 1)[1].split(",") if w.strip()]


def load_corrections(config_dir: Path) -> list[dict]:
    """Todas las correcciones guardadas; las líneas rotas se saltan (el archivo es editable a mano)."""
    path = path_for(config_dir)
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            log.warning("%s línea %d ilegible; se ignora", path.name, n)
            continue
        if isinstance(entry, dict) and entry.get("tipo") in KINDS and entry.get("motivo"):
            out.append(entry)
    return out


def add_correction(config_dir: Path, *, tipo: str, video: str, motivo: str, finding: dict | None = None,
                   segundo: float | None = None, now: datetime | None = None, cliente: str | None = None) -> dict:
    """Guarda una corrección y la devuelve. `finding` es el hallazgo corregido (falso positivo)."""
    if tipo not in KINDS:
        raise ValueError(f"tipo de corrección desconocido: {tipo}")
    motivo = motivo.strip()
    if not motivo:
        raise ValueError("la corrección necesita un motivo")
    entry: dict = {"fecha": (now or datetime.now()).isoformat(timespec="seconds"), "tipo": tipo,
                   "video": video, "motivo": motivo}
    if cliente:
        entry["cliente"] = cliente  # sin cliente = vale para todos
    if finding:
        entry.update({"check": finding.get("check", ""), "categoria": finding.get("type", ""),
                      "titulo": finding.get("title", ""), "detalle": finding.get("detail", ""),
                      "palabras": words_of(finding), "segundo": finding.get("t_start")})
    elif segundo is not None:
        entry["segundo"] = segundo
    config_dir.mkdir(parents=True, exist_ok=True)
    with path_for(config_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def repeated_words(corrections: list[dict], words: list[str], min_count: int = 2) -> list[str]:
    """De `words`, las que ya se corrigieron como falso positivo al menos `min_count` veces.

    Son candidatas al glosario: así el código deja de marcarlas aunque Claude no esté.
    """
    counts: dict[str, int] = {}
    for c in corrections:
        if c.get("tipo") == "falso_positivo":
            for w in {w.lower() for w in c.get("palabras", [])}:
                counts[w] = counts.get(w, 0) + 1
    return [w for w in words if counts.get(w.lower(), 0) >= min_count]


def relevant(corrections: list[dict], code_findings: list[Finding], appearances: list[dict],
             transcript: dict, limit: int = MAX_RELEVANT) -> list[dict]:
    """Las correcciones que más se parecen al video actual, como mucho `limit`.

    Puntúa por el mismo tipo de hallazgo, palabras marcadas que vuelven a salir y
    vocabulario compartido con lo que se ve y se dice. Con pocas correcciones van todas;
    a igualdad, las más recientes primero.
    """
    if len(corrections) <= limit:
        return list(reversed(corrections))
    checks = {f.check for f in code_findings}
    categories = {f.type for f in code_findings}
    flagged = {w.lower() for f in code_findings for w in words_of(f.to_dict())}
    context = _tokens(" ".join([transcript.get("text", ""), *(a.get("text", "") for a in appearances),
                                *(f.title for f in code_findings)]))

    def score(c: dict) -> float:
        s = 0.0
        if c.get("check") and c["check"] in checks:
            s += 3
        elif c.get("categoria") and c["categoria"] in categories:
            s += 1
        s += 4 * len({w.lower() for w in c.get("palabras", [])} & flagged)
        s += min(3, len(_tokens(" ".join([c.get("motivo", ""), c.get("titulo", ""), c.get("detalle", "")])) & context))
        return s

    ranked = sorted(enumerate(corrections), key=lambda ic: (score(ic[1]), ic[0]), reverse=True)
    return [c for _, c in ranked[:limit]]


def for_judge(entries: list[dict]) -> list[dict]:
    """Lo que ve el juez de cada corrección: sin rutas ni campos internos."""
    keep = ("tipo", "motivo", "check", "categoria", "titulo", "detalle", "palabras", "video", "segundo")
    return [{k: e[k] for k in keep if e.get(k) not in (None, "", [])} for e in entries]
