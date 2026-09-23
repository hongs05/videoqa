"""Candidatas a entrar en el glosario del equipo.

Sembrar el glosario a mano, palabra por palabra y después de cada video en rojo, es
lo que hace que nadie lo llene. Este módulo mira lo YA revisado en esta Mac y propone
de una vez las palabras que más veces se marcaron, para aprobarlas en bloque.
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

from videoqa.checks.spelling import in_glossary

log = logging.getLogger("videoqa")

CABECERA = ("# Palabras válidas del equipo (nombres de marca, productos, jerga).\n"
            "# Una por línea. Las líneas que empiezan por # son comentarios.\n"
            "# Conviene agruparlas por cuenta con un comentario encima.\n")


def _palabras(finding: dict) -> list[str]:
    # Solo "spelling_unknown_word": el título es "Posible error ortográfico: a, b".
    # "spelling_punctuation" también empieza por "spelling" pero su título es una frase
    # ("Puntuación: falta el signo de apertura ¿"), no una lista de palabras -- ofrecerla
    # como candidata metía basura en el glosario del equipo. "spelling_glued_words" son
    # lecturas del OCR con los espacios perdidos, no palabras que valga la pena aceptar.
    if str(finding.get("check", "")) != "spelling_unknown_word":
        return []
    titulo = str(finding.get("title", ""))
    if ":" not in titulo:
        return []
    return [w.strip().lower() for w in titulo.split(":", 1)[1].split(",") if w.strip()]


def candidatas(jobs_dir: Path, glossary: set[str], checker=None) -> list[tuple[str, int, int]]:
    """`checker`: el corrector ya construido (con los idiomas configurados). Las
    revisiones pasadas se hicieron con un corrector que pudo cambiar de idiomas (Task 1);
    sin filtrar contra el corrector ACTUAL, palabras inglesas normales que ya se aceptan
    hoy ("earnings", "moment"...) siguen saliendo como candidatas y entierran a las
    candidatas reales. Sin `checker` (None) el comportamiento es el de siempre: solo se
    descarta lo que ya acepta `glossary`.
    """
    veces: Counter[str] = Counter()
    videos: defaultdict[str, set[str]] = defaultdict(set)
    for f in sorted(Path(jobs_dir).glob("*/findings_code.json")):
        try:
            findings = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("glosario: no pude leer %s (%s)", f, e)
            continue
        if not isinstance(findings, list):
            continue
        for fnd in findings:
            if not isinstance(fnd, dict):
                continue
            for w in _palabras(fnd):
                if in_glossary(w, glossary):
                    continue
                if checker is not None and not checker.unknown([w]):
                    continue
                veces[w] += 1
                videos[w].add(f.parent.name)
    return sorted(((w, n, len(videos[w])) for w, n in veces.items()),
                  key=lambda t: (-t[1], t[0]))


def agregar(path: Path, palabras: list[str]) -> list[str]:
    path = Path(path)
    existentes = set()
    if path.exists():
        existentes = {l.strip().lower() for l in path.read_text(encoding="utf-8").splitlines()
                      if l.strip() and not l.startswith("#")}
    nuevas = []
    for w in palabras:
        w = w.strip().lower()
        if w and w not in existentes:
            existentes.add(w)
            nuevas.append(w)
    if not nuevas:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(CABECERA, encoding="utf-8")
    # El salto de línea final se comprueba ANTES de abrir en modo append: leer el
    # archivo entero dentro del `with` (en modo "a") es torpe y, en según qué
    # implementaciones, puede leer sobre el propio descriptor recién abierto.
    termina_en_salto = path.stat().st_size == 0 or path.read_text(encoding="utf-8").endswith("\n")
    with path.open("a", encoding="utf-8") as fh:
        if not termina_en_salto:
            fh.write("\n")
        for w in nuevas:
            fh.write(f"{w}\n")
    return nuevas
