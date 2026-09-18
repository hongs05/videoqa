from __future__ import annotations

import re
from pathlib import Path

from videoqa.findings import Finding

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")

NSNOTFOUND = 0x7FFFFFFFFFFFFFFF

# Minúscula tras punto (o ? / !) seguido de espacio. El lookbehind de dígito evita
# marcar decimales ("3.5 euros") y otras cifras con punto.
_LOWER_AFTER_DOT_RE = re.compile(r"(?<!\d)[.?!]\s+[a-záéíóúüñ]")


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
    for w in WORD_RE.findall(text):
        if len(w) < 3 or w.lower() in glossary:
            continue
        if checker.unknown([w]):
            out.append(w)
    return out


def _punctuation_issues(text: str) -> list[str]:
    issues = []
    if text.rstrip().endswith("?") and "¿" not in text:
        issues.append("falta el signo de apertura ¿")
    if text.rstrip().endswith("!") and "¡" not in text:
        issues.append("falta el signo de apertura ¡")
    if "  " in text:
        issues.append("doble espacio")
    if _LOWER_AFTER_DOT_RE.search(text):
        issues.append("minúscula después de punto")
    return issues


def check_spelling(appearances: list[dict], glossary: set[str], rules: dict, checker=None) -> list[Finding]:
    if checker is None:
        from videoqa import backends

        checker = backends.get_speller()()
    sev = rules["severities"]
    min_conf = float(rules["thresholds"].get("ocr_min_conf", 0.0))
    out = []
    for i, a in enumerate(appearances):
        # El OCR también lee texturas, bordados y logos del vestuario con confianza
        # baja ("nka" de un escudo escolar). Revisarlos ortográficamente producía
        # bloqueantes falsos; los subtítulos reales llegan con confianza ~1.0.
        if float(a.get("conf", 1.0)) < min_conf:
            continue
        text = a["text"]
        bad = unknown_words(text, checker, glossary)
        if bad:
            fixes = ", ".join(f"{w} → {checker.correction(w) or '?'}" for w in bad)
            out.append(Finding(
                id=f"spell-{i}", type="ortografia", severity=sev["spelling_unknown_word"],
                t_start=a["t_start"], t_end=a["t_end"],
                title=f"Posible error ortográfico: {', '.join(bad)}",
                detail=f'Texto en pantalla: "{text}".', suggestion=fixes,
                frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_unknown_word"))
        for k, issue in enumerate(_punctuation_issues(text)):
            out.append(Finding(
                id=f"punct-{i}-{k}", type="ortografia", severity=sev["spelling_punctuation"],
                t_start=a["t_start"], t_end=a["t_end"], title=f"Puntuación: {issue}",
                detail=f'Texto en pantalla: "{text}".', suggestion="Corregir la puntuación.",
                frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_punctuation"))
    return out
