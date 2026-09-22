from __future__ import annotations

import re
from pathlib import Path

from videoqa.findings import Finding

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")

NSNOTFOUND = 0x7FFFFFFFFFFFFFFF

# Minúscula tras punto seguido de espacio. El lookbehind de dígito evita marcar
# decimales ("3.5 euros"); los de punto/lookahead evitan los puntos suspensivos
# ("espera... y luego"), tras los que la minúscula es correcta. Tras ? o ! tampoco
# se marca: en español puede seguir la misma oración ("¿Vienes?, preguntó").
_LOWER_AFTER_DOT_RE = re.compile(r"(?<![\d.])\.(?!\.)\s+[a-záéíóúüñ]")

# URLs, correos, @usuarios y #hashtags: no son palabras del diccionario. Partirlos en
# trozos ("www", "com", "tiendamx") daba bloqueantes de ortografía falsos.
_NON_WORDS_RE = re.compile(
    r"(?:https?://|www\.)\S+|\S+@\S+\.\S+|[@#][\wÁÉÍÓÚÜÑáéíóúüñ.]+"
    r"|\b[\w-]+\.(?:com|net|org|io|app|mx|es|co|ar|cl|pe|us|info|shop|store|tv|me|link)\b\S*",
    re.I)


class MacSpellChecker:
    """Corrector ortográfico nativo de macOS (NSSpellChecker) en español."""

    def __init__(self, language: str = "es"):
        from AppKit import NSSpellChecker  # pyobjc, ya instalado vía ocrmac
        from Foundation import NSMakeRange

        self._range = NSMakeRange
        self._sc = NSSpellChecker.sharedSpellChecker()
        self._sc.setLanguage_(language)
        self._lang = language

    def is_known(self, word: str) -> bool:
        # API con idioma explícito: `checkSpellingOfString:startingAt:` usa el idioma del
        # panel compartido (que otra app puede haber cambiado) y en la práctica devolvía
        # "conocido" para casi todo. Con esta variante el idioma va en la llamada.
        res = self._sc.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            word, 0, self._lang, False, 0, None)
        r = res[0] if isinstance(res, tuple) else res
        return getattr(r, "location", r) == NSNOTFOUND  # NSNotFound = sin error = palabra conocida

    def unknown(self, words) -> set[str]:
        return {w for w in words if not self.is_known(w)}

    def correction(self, word: str) -> str | None:
        guesses = self._sc.guessesForWordRange_inString_language_inSpellDocumentWithTag_(
            self._range(0, len(word)), word, self._lang, 0)
        return str(guesses[0]) if guesses else None


def load_glossary(path: Path) -> set[str]:
    if not path.exists():
        return set()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def unknown_words(text: str, checker, glossary: set[str]) -> list[str]:
    # Nota: NO se saltan las palabras en MAYÚSCULAS. Los rótulos de reels están casi
    # siempre en caps, así que saltarlas dejaba el check sin nada que revisar. Las siglas
    # habituales (IVA, CDMX, MXN) las reconoce el diccionario de macOS; las que no, van a
    # `glosario.txt`.
    out = []
    for w in WORD_RE.findall(_NON_WORDS_RE.sub(" ", text)):
        if len(w) < 3 or w.lower() in glossary:
            continue
        if checker.unknown([w]):
            out.append(w)
    return out


def _punctuation_issues(text: str, opened: str = "") -> list[str]:
    """`opened`: texto que está en pantalla a la vez (otras líneas del mismo rótulo).

    El OCR devuelve cada LÍNEA por separado: en "¿Sabías que" / "esto funciona?" la
    segunda línea no lleva ¿ porque está en la primera. Por eso el signo de apertura
    se busca también en las líneas simultáneas.
    """
    issues = []
    stripped = _NON_WORDS_RE.sub(" ", text).rstrip()
    if stripped.endswith("?") and "¿" not in text and "¿" not in opened:
        issues.append("falta el signo de apertura ¿")
    if stripped.endswith("!") and "¡" not in text and "¡" not in opened:
        issues.append("falta el signo de apertura ¡")
    if "  " in text.strip():
        issues.append("doble espacio")
    if _LOWER_AFTER_DOT_RE.search(stripped):
        issues.append("minúscula después de punto")
    return issues


def _concurrent_text(appearances: list[dict], i: int) -> str:
    a = appearances[i]
    return " ".join(b["text"] for j, b in enumerate(appearances)
                    if j != i and b["t_start"] < a["t_end"] and a["t_start"] < b["t_end"])


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _also_at(times: list[float]) -> str:
    if not times:
        return ""
    shown = ", ".join(f"{t:.1f} s" for t in times[:5])
    more = f" y {len(times) - 5} más" if len(times) > 5 else ""
    return f" También aparece en {shown}{more}."


def check_spelling(appearances: list[dict], glossary: set[str], rules: dict, checker=None) -> list[Finding]:
    if checker is None:
        from videoqa import backends

        checker = backends.get_speller()()
    sev = rules["severities"]
    min_conf = float(rules["thresholds"].get("ocr_min_conf", 0.0))
    # El mismo rótulo (o la misma palabra mal escrita) suele aparecer varias veces: el
    # OCR parte una aparición en dos si falla un frame, y los subtítulos repiten el
    # nombre de marca. Un hallazgo por repetición inundaba el reporte con el MISMO
    # error; ahora se agrupa y el detalle lista los demás segundos.
    spell: dict[tuple, tuple[Finding, list[float]]] = {}
    punct: dict[tuple, tuple[Finding, list[float]]] = {}
    for i, a in enumerate(appearances):
        # El OCR también lee texturas, bordados y logos del vestuario con confianza
        # baja ("nka" de un escudo escolar). Revisarlos ortográficamente producía
        # bloqueantes falsos; los subtítulos reales llegan con confianza ~1.0.
        if float(a.get("conf", 1.0)) < min_conf:
            continue
        text = a["text"]
        bad = unknown_words(text, checker, glossary)
        if bad:
            key = tuple(sorted({w.lower() for w in bad}))
            if key in spell:
                spell[key][1].append(a["t_start"])
            else:
                fixes = ", ".join(f"{w} → {checker.correction(w) or '?'}" for w in dict.fromkeys(bad))
                spell[key] = (Finding(
                    id=f"spell-{i}", type="ortografia", severity=sev["spelling_unknown_word"],
                    t_start=a["t_start"], t_end=a["t_end"],
                    title=f"Posible error ortográfico: {', '.join(dict.fromkeys(bad))}",
                    detail=f'Texto en pantalla: "{text}".', suggestion=fixes,
                    frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_unknown_word"), [])
        for k, issue in enumerate(_punctuation_issues(text, _concurrent_text(appearances, i))):
            key = (issue, _norm(text))
            if key in punct:
                punct[key][1].append(a["t_start"])
                continue
            punct[key] = (Finding(
                id=f"punct-{i}-{k}", type="ortografia", severity=sev["spelling_punctuation"],
                t_start=a["t_start"], t_end=a["t_end"], title=f"Puntuación: {issue}",
                detail=f'Texto en pantalla: "{text}".', suggestion="Corregir la puntuación.",
                frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_punctuation"), [])
    out = []
    for f, times in [*spell.values(), *punct.values()]:
        f.detail += _also_at(times)
        out.append(f)
    return out
