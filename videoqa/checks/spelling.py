from __future__ import annotations

import re
from pathlib import Path

from videoqa.checks.scene_text import is_scene_text
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
    """Corrector ortográfico nativo de macOS (NSSpellChecker).

    Consulta varios idiomas: una palabra solo es un error si NINGUNO la reconoce.
    Los rótulos de redes mezclan idiomas ("earnings", "wanna", "link") y con un solo
    diccionario español esas palabras salían como faltas.
    """

    def __init__(self, languages: tuple[str, ...] = ("es",)):
        from AppKit import NSSpellChecker  # pyobjc, ya instalado vía ocrmac
        from Foundation import NSMakeRange

        self._range = NSMakeRange
        self._sc = NSSpellChecker.sharedSpellChecker()
        self._langs = tuple(languages) or ("es",)
        self._lang = self._langs[0]
        self._sc.setLanguage_(self._lang)

    def _known_in(self, word: str, language: str) -> bool:
        # API con idioma explícito: `checkSpellingOfString:startingAt:` usa el idioma del
        # panel compartido (que otra app puede haber cambiado) y en la práctica devolvía
        # "conocido" para casi todo. Con esta variante el idioma va en la llamada.
        res = self._sc.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            word, 0, language, False, 0, None)
        r = res[0] if isinstance(res, tuple) else res
        return getattr(r, "location", r) == NSNOTFOUND  # NSNotFound = sin error = palabra conocida

    def is_known(self, word: str) -> bool:
        return any(self._known_in(word, lang) for lang in self._langs)

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


# Palabras cortas válidas al separar palabras pegadas. Lista cerrada: el diccionario
# acepta muchas abreviaturas de 2 letras y con él una falta real ("kasa") se partía en
# trozos "conocidos" ("ka" + "sa"). "ti" queda fuera a propósito: "IMPORTANTI" no es
# "importan ti".
_SHORT_WORDS = {"y", "a", "o", "e", "u", "de", "la", "el", "en", "es", "un", "lo", "le", "se", "me",
                "te", "mi", "tu", "su", "ya", "no", "si", "sí", "tú", "él", "mí", "al", "ha", "he",
                "va", "ve", "da", "di", "ni", "yo", "os"}


class _Vocab:
    """Decide qué hacer con una palabra que el diccionario no reconoce.

    Tres casos que en los reportes reales salían como bloqueantes y no lo son:
    - El talento la DICE y Whisper la escribe igual ("Mojito", "backdrops", "Stay"):
      es una palabra válida que falta en el diccionario de macOS.
    - Son palabras pegadas ("Yasíescomo" = "Y así es como"): el OCR de Vision pierde los
      espacios en las tipografías de subtítulo apretadas. Se deja como `info`.
    - Es un trozo de una palabra más larga que se dice o se ve en ese momento
      ("ocktails" de "cocktails"): el frame cazó el subtítulo a mitad de animación.
    """

    def __init__(self, checker, glossary: set[str], segments: list[dict], appearances: list[dict]):
        self.checker, self.glossary = checker, glossary
        self.segments, self.appearances = segments, appearances
        self.spoken = {w.lower() for s in segments for w in WORD_RE.findall(s["text"])}
        self._known: dict[str, bool] = {}

    def known(self, part: str) -> bool:
        if len(part) <= 2:
            return part in _SHORT_WORDS
        if part in self.glossary or part in self.spoken:
            return True
        if part not in self._known:
            self._known[part] = not self.checker.unknown([part])
        return self._known[part]

    def split(self, word: str) -> list[str] | None:
        """Parte `word` en ≥2 palabras conocidas (la de menos trozos), o None."""
        w = word.lower()
        best: list[list[str] | None] = [[]] + [None] * len(w)
        for end in range(1, len(w) + 1):
            for start in range(end):
                prev = best[start]
                if prev is None or (best[end] is not None and len(prev) + 1 >= len(best[end])):
                    continue
                if self.known(w[start:end]):
                    best[end] = prev + [w[start:end]]
        parts = best[len(w)]
        # Al menos dos palabras "de verdad" y una de 3+ letras: una palabra más una letra
        # suelta ("casaa" = "casa" + "a") es la forma típica de una errata, no de un pegado.
        if not parts or sum(len(p) >= 2 for p in parts) < 2 or max(len(p) for p in parts) < 3:
            return None
        return parts

    def is_fragment(self, word: str, a: dict) -> bool:
        w = word.lower()
        t0, t1 = a["t_start"] - 2.0, a["t_end"] + 2.0
        near = [s["text"] for s in self.segments if s["start"] < t1 and t0 < s["end"]]
        near += [b["text"] for b in self.appearances if b is not a and b["t_start"] < t1 and t0 < b["t_end"]]
        return any(len(o) > len(w) and w in o.lower() for text in near for o in WORD_RE.findall(text))

    def classify(self, word: str, a: dict) -> str:
        """'ok' (no es error), 'glued' (palabras pegadas) o 'unknown'."""
        if word.lower() in self.spoken or self.is_fragment(word, a):
            return "ok"
        return "glued" if self.split(word) else "unknown"


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


def check_spelling(appearances: list[dict], glossary: set[str], rules: dict, checker=None,
                   segments: list[dict] | None = None) -> list[Finding]:
    if checker is None:
        from videoqa import backends

        checker = backends.get_speller()()
    sev = rules["severities"]
    vocab = _Vocab(checker, glossary, segments or [], appearances)
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
        scene = is_scene_text(a, rules)
        unknown = unknown_words(text, checker, glossary)
        kinds = {w: vocab.classify(w, a) for w in unknown}
        bad = [w for w in unknown if kinds[w] == "unknown"]
        glued = [w for w in unknown if kinds[w] == "glued"]
        if bad:
            key = (scene, *sorted({w.lower() for w in bad}))
            if key in spell:
                spell[key][1].append(a["t_start"])
            else:
                fixes = ", ".join(f"{w} → {checker.correction(w) or '?'}" for w in dict.fromkeys(bad))
                where = "Texto de la escena (ropa, cartel, empaque)" if scene else "Texto en pantalla"
                spell[key] = (Finding(
                    id=f"spell-{i}", type="ortografia",
                    severity=(sev.get("spelling_scene_text", "info") if scene else sev["spelling_unknown_word"]),
                    t_start=a["t_start"], t_end=a["t_end"],
                    title=f"Posible error ortográfico: {', '.join(dict.fromkeys(bad))}",
                    detail=f'{where}: "{text}".', suggestion=fixes,
                    frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_unknown_word"), [])
        if glued:
            key = ("glued", *sorted({w.lower() for w in glued}))
            if key in spell:
                spell[key][1].append(a["t_start"])
            else:
                sep = ", ".join(f'{w} → "{" ".join(vocab.split(w))}"' for w in dict.fromkeys(glued))
                spell[key] = (Finding(
                    id=f"glued-{i}", type="ortografia", severity=sev.get("spelling_glued_words", "info"),
                    t_start=a["t_start"], t_end=a["t_end"],
                    title=f"Palabras juntas: {', '.join(dict.fromkeys(glued))}",
                    detail=(f'Texto leído: "{text}". Casi siempre es el OCR, que pierde los espacios en '
                            "tipografías apretadas; mira el frame para confirmarlo."),
                    suggestion=f"Solo si en el video se ven pegadas, separarlas: {sep}.",
                    frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="spelling_glued_words"), [])
        if scene:
            continue  # la puntuación de un cartel o una camiseta no la decide el editor
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
