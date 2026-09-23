# Glosario y diccionario — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el corrector deje de marcar como falta lo que no lo es (inglés, jerga, nombres de marca) y que el glosario del equipo se pueda sembrar de golpe en vez de palabra por palabra.

**Architecture:** (1) El corrector de macOS pasa a consultar VARIOS idiomas (`es` y `en` por defecto, configurable): una palabra solo es desconocida si falla en todos. (2) El glosario acepta plurales y terminaciones habituales, no solo la palabra exacta. (3) Un glosario base viaja dentro del paquete (anglicismos de redes, jerga latinoamericana, nombres de plataformas y herramientas) y se suma al del equipo. (4) Un comando `videoqa glosario` recorre lo ya revisado, propone las palabras candidatas ordenadas por frecuencia y las añade al archivo del equipo sin duplicar.

**Tech Stack:** Python 3.12, pytest, NSSpellChecker (pyobjc), Claude Code plugin (skills en Markdown).

**Spec:** Diagnóstico acordado en conversación el 2026-09-22. Hechos verificados en esta Mac:
- `NSSpellChecker.availableLanguages()` incluye `es` y `en` (y variantes de inglés), **pero ninguna variante regional de español** (`es_MX`, `es_419` no existen). La idea de "diccionario regional" no es posible por esa vía y se sustituye por el glosario base empaquetado.
- De las 40 palabras marcadas en los 7 videos revisados, ~15 son inglés corriente (moment, earnings, calendar, solution, featured, falls, every, wanna, gonna, taming, caring, mock, site, sun, jul), ~14 son basura del OCR (sarte, soue, eluge, estel, avan, nue, oté, ava, vou, jel, aor, jso, detoils, descle), y el resto son nombres propios (educanab, dediktok, canva, klook, carmina) o faltas reales (aprobecha, comun).
- `<drive_root>/_config/glosario.txt` **no existe** todavía: hoy el glosario del equipo está vacío.
- El glosario se compara hoy en minúsculas y de forma exacta (`videoqa/checks/spelling.py::load_glossary` y `unknown_words`).

## Global Constraints

- Idioma de todo texto visible por la persona: español informal (tú), sin jerga técnica.
- Ningún test nuevo requiere `claude`, red, ni el `~/.videoqa` real: se usa `VIDEOQA_HOME` (fixture autouse en `tests/conftest.py`) y un corrector falso.
- Los tests que usan el corrector de macOS real ya existentes deben seguir pasando.
- Comandos del motor siempre como `uv run --project ~/videoqa videoqa …`.
- Commits pequeños, en español, terminados con `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Al terminar: `uv run pytest -q` en verde y versión del plugin subida a `1.4.0` en `plugins/aura/.claude-plugin/plugin.json` y `.claude-plugin/marketplace.json` (un test comprueba que coinciden).
- Toda skill nueva o modificada pasa `tests/unit/test_plugin_layout.py`.

---

### Task 1: El corrector consulta varios idiomas

**Files:**
- Modify: `videoqa/checks/spelling.py` (`MacSpellChecker`)
- Modify: `videoqa/config.py` (`Settings.idiomas`, lectura de `load_settings`)
- Modify: `videoqa/backends.py` (`get_speller`) y el punto de llamada en `check_spelling`
- Test: `tests/unit/test_spelling.py`, `tests/unit/test_config.py`

**Interfaces:**
- Produces: `MacSpellChecker(languages: tuple[str, ...] = ("es",))`. `is_known(word)` es True si el corrector la reconoce en **alguno** de los idiomas; `unknown(words)` devuelve las que fallan en todos; `correction(word)` sigue usando el PRIMER idioma (el principal).
- Produces: `Settings.idiomas: tuple[str, ...] = ("es", "en")`, leído de la clave `idiomas` de `~/.videoqa/config.yaml` (lista de textos). Si la clave no está, ese es el valor por defecto.
- `check_spelling(...)` acepta el checker ya construido como hoy; quien lo construye es `videoqa/pipeline.py`, que pasa `settings.idiomas`.

- [ ] **Step 1: Tests del corrector con varios idiomas**

Añadir a `tests/unit/test_spelling.py` (ahí ya hay un corrector falso; si no, crear este):

```python
from videoqa.checks.spelling import MacSpellChecker


class _FakeNS:
    """Imita NSSpellChecker: cada idioma conoce su propio conjunto de palabras."""

    def __init__(self, por_idioma):
        self.por_idioma = por_idioma
        self.vistas = []

    def setLanguage_(self, lang):
        pass

    def checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            self, word, start, language, wrap, tag, count):
        self.vistas.append((word, language))
        conocida = word.lower() in self.por_idioma.get(language, set())

        class _R:
            location = 0x7FFFFFFFFFFFFFFF if conocida else 0
        return _R()


def _checker(por_idioma, languages=("es", "en")):
    c = MacSpellChecker.__new__(MacSpellChecker)
    c._sc = _FakeNS(por_idioma)
    c._lang = languages[0]
    c._langs = tuple(languages)
    c._range = lambda a, b: (a, b)
    return c


def test_palabra_inglesa_se_acepta_si_el_idioma_ingles_esta_activo():
    c = _checker({"es": {"hola"}, "en": {"earnings"}})
    assert c.is_known("earnings")
    assert c.unknown(["earnings"]) == set()


def test_palabra_desconocida_en_todos_los_idiomas_se_marca():
    c = _checker({"es": {"hola"}, "en": {"earnings"}})
    assert not c.is_known("aprobecha")
    assert c.unknown(["aprobecha"]) == {"aprobecha"}


def test_solo_espanol_vuelve_a_marcar_el_ingles():
    c = _checker({"es": {"hola"}, "en": {"earnings"}}, languages=("es",))
    assert c.unknown(["earnings"]) == {"earnings"}


def test_no_consulta_el_segundo_idioma_si_el_primero_ya_la_conoce():
    c = _checker({"es": {"hola"}, "en": {"hola"}})
    c.is_known("hola")
    assert [l for _, l in c._sc.vistas] == ["es"]
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_spelling.py -q -k idioma`
Expected: FAIL (el constructor no acepta `languages`, no existe `_langs`).

- [ ] **Step 3: Implementar en `videoqa/checks/spelling.py`**

```python
class MacSpellChecker:
    """Corrector ortográfico nativo de macOS (NSSpellChecker).

    Consulta varios idiomas: una palabra solo es un error si NINGUNO la reconoce.
    Los rótulos de redes mezclan idiomas ("earnings", "wanna", "link") y con un solo
    diccionario español esas palabras salían como faltas.
    """

    def __init__(self, languages: tuple[str, ...] = ("es",)):
        from AppKit import NSSpellChecker
        from Foundation import NSMakeRange

        self._range = NSMakeRange
        self._sc = NSSpellChecker.sharedSpellChecker()
        self._langs = tuple(languages) or ("es",)
        self._lang = self._langs[0]
        self._sc.setLanguage_(self._lang)

    def _known_in(self, word: str, language: str) -> bool:
        res = self._sc.checkSpellingOfString_startingAt_language_wrap_inSpellDocumentWithTag_wordCount_(
            word, 0, language, False, 0, None)
        r = res[0] if isinstance(res, tuple) else res
        return getattr(r, "location", r) == NSNOTFOUND

    def is_known(self, word: str) -> bool:
        return any(self._known_in(word, lang) for lang in self._langs)
```

`unknown` y `correction` se quedan igual (`correction` ya usa `self._lang`, que ahora es el primer idioma).

- [ ] **Step 4: Tests de config**

Añadir a `tests/unit/test_config.py`:

```python
def test_idiomas_por_defecto(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("drive_root: /tmp/d\n")
    assert load_settings(p).idiomas == ("es", "en")


def test_idiomas_configurables(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("drive_root: /tmp/d\nidiomas: [es]\n")
    assert load_settings(p).idiomas == ("es",)
```

- [ ] **Step 5: Implementar en `videoqa/config.py`**

En `Settings`, junto a `whisper_model`:

```python
    # Idiomas del corrector ortográfico: una palabra solo es falta si falla en todos.
    # Los rótulos de redes mezclan español e inglés; con solo "es" salían como errores.
    idiomas: tuple[str, ...] = ("es", "en")
```

En `load_settings`, junto a las demás claves opcionales:

```python
    if data.get("idiomas"):
        kwargs["idiomas"] = tuple(str(x) for x in data["idiomas"])
```

Y en `load_all_settings`, al construir las `Settings` de las carpetas extra, pasar `idiomas=principal.idiomas` (como ya se hace con `whisper_model`).

- [ ] **Step 6: Enganchar en el pipeline**

En `videoqa/backends.py`, `get_speller()` devuelve la CLASE del corrector; quien la instancia es `check_spelling` cuando `checker is None`. Para que llegue la configuración sin cambiar la firma pública de `check_spelling`, constrúyelo en `videoqa/pipeline.py` y pásalo:

```python
        checker = backends.get_speller()(settings.idiomas)
        code_findings = (check_spelling(apps, glossary, rules, checker=checker, segments=transcript["segments"])
                         + ...)
```

Comprueba antes cómo llama hoy `pipeline.py` a `check_spelling` y conserva el resto de argumentos tal cual. Si el backend por defecto no acepta argumentos posicionales (backends alternativos registrados por terceros), haz la construcción tolerante:

```python
        try:
            checker = backends.get_speller()(settings.idiomas)
        except TypeError:  # backend de terceros sin soporte de idiomas
            checker = backends.get_speller()()
```

- [ ] **Step 7: Correr toda la suite**

Run: `uv run pytest -q`
Expected: verde.

- [ ] **Step 8: Commit**

```bash
git add videoqa/checks/spelling.py videoqa/config.py videoqa/pipeline.py tests/unit/test_spelling.py tests/unit/test_config.py
git commit -m "feat: el corrector acepta varios idiomas (español e inglés por defecto)"
```

---

### Task 2: El glosario acepta plurales y un glosario base viaja en el paquete

**Files:**
- Create: `videoqa/data/glosario_base.txt`
- Modify: `videoqa/checks/spelling.py` (`load_glossary`, nueva `in_glossary`, uso en `unknown_words` y `_Vocab.known`)
- Modify: `pyproject.toml` (`force-include` del archivo de datos)
- Test: `tests/unit/test_spelling.py`

**Interfaces:**
- Consumes: nada de Task 1.
- Produces: `videoqa.checks.spelling.BASE_GLOSSARY_PATH: Path` (el archivo empaquetado), `load_base_glossary() -> set[str]`, y `load_glossary(path, incluir_base: bool = True) -> set[str]` que devuelve la unión del archivo del equipo y el base.
- Produces: `in_glossary(word: str, glossary: set[str]) -> bool`: True si la palabra en minúsculas está, o si lo está su forma sin la terminación `s` / `es` (plural), o si la palabra es el plural de una entrada. Nunca se recorta por debajo de 3 letras.

- [ ] **Step 1: Tests**

Añadir a `tests/unit/test_spelling.py`:

```python
from videoqa.checks.spelling import (BASE_GLOSSARY_PATH, in_glossary, load_base_glossary,
                                     load_glossary, unknown_words)


def test_in_glossary_exacta_y_plural():
    g = {"corillo", "reel"}
    assert in_glossary("corillo", g)
    assert in_glossary("Corillo", g)
    assert in_glossary("corillos", g)   # plural en -s
    assert in_glossary("reels", g)
    assert not in_glossary("corillito", g)


def test_in_glossary_plural_en_es():
    g = {"mall"}
    assert in_glossary("malles", g)


def test_in_glossary_entrada_en_plural_acepta_singular():
    g = {"stories"}
    assert in_glossary("stories", g)


def test_in_glossary_no_recorta_palabras_cortas():
    g = {"as"}
    assert not in_glossary("ases", g) or in_glossary("as", g)  # no revienta con entradas cortas


def test_el_glosario_base_existe_y_trae_palabras():
    assert BASE_GLOSSARY_PATH.exists()
    base = load_base_glossary()
    assert {"reel", "storie", "hashtag", "canva"} <= base
    assert all(w == w.lower() for w in base)


def test_load_glossary_suma_el_base(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("Kasa\n# comentario\n\nMolinrocha\n")
    g = load_glossary(p)
    assert {"kasa", "molinrocha"} <= g
    assert "reel" in g                      # viene del base
    assert "# comentario" not in g


def test_load_glossary_puede_excluir_el_base(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("Kasa\n")
    assert load_glossary(p, incluir_base=False) == {"kasa"}


def test_load_glossary_sin_archivo_del_equipo_devuelve_el_base(tmp_path):
    g = load_glossary(tmp_path / "no_existe.txt")
    assert "reel" in g


def test_unknown_words_respeta_el_plural_del_glosario():
    class _C:
        def unknown(self, words):
            return set(words)          # el diccionario no conoce nada
    assert unknown_words("Los corillos llegaron", _C(), {"corillo"}) == ["Los", "llegaron"]
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_spelling.py -q -k glossary`
Expected: FAIL por los imports que no existen.

- [ ] **Step 3: Crear `videoqa/data/glosario_base.txt`**

Una palabra por línea, en minúsculas, con comentarios `#` por bloques. Incluye al menos estas, y añade las que consideres del mismo tipo (el criterio: palabras que un equipo de redes en español usa a diario y que el diccionario de macOS no reconoce):

```
# Glosario base de VideoQA. Viaja dentro del programa y se suma al glosario del
# equipo (_config/glosario.txt). Son palabras que un equipo de redes usa a diario y
# que el diccionario no reconoce. Para añadir las vuestras, usad el archivo del equipo.

# --- Redes y formatos ---
reel
reels
storie
stories
story
carrusel
tiktok
tiktoks
igtv
shorts
hashtag
hashtags
caption
captions
copy
copys
feed
thumbnail
engagement
alcance
branding
briefing
lookbook
unboxing
behindthescenes
ugc
cta
kpi
roi

# --- Plataformas y herramientas ---
instagram
whatsapp
facebook
youtube
linkedin
twitter
threads
spotify
canva
capcut
figma
photoshop
premiere
lightroom
notion
trello
metricool
hootsuite
klook

# --- Anglicismos frecuentes en rótulos ---
link
links
online
offline
influencer
influencers
marketing
ecommerce
delivery
combo
outfit
look
tips
tip
must
top
sale
live
lives
pack
packs
gift
skincare
fitness
workout
mood
vibes

# --- Jerga latinoamericana habitual ---
chevere
chévere
bacano
bacana
pana
panas
corillo
corillos
chavo
chava
chido
padrisimo
padrísimo
guay
tuanis
pura
vida
mae
parcero
parcera
chamba
platita
lana
antojo
antojito
rico
riquisimo
riquísimo
```

Nota: `pura` y `vida` van sueltas a propósito ("pura vida" se lee palabra a palabra).

- [ ] **Step 4: Implementar en `videoqa/checks/spelling.py`**

Debajo de `WORD_RE`:

```python
# Glosario base empaquetado: palabras de redes, anglicismos y jerga que el diccionario
# de macOS no reconoce y que NO son faltas. Se suma al glosario del equipo.
BASE_GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "data" / "glosario_base.txt"

# Terminaciones de plural que se prueban contra el glosario: "corillo" en la lista
# también vale para "corillos". Nunca se recorta por debajo de 3 letras para no
# convertir una falta corta en una palabra válida.
_PLURALES = ("es", "s")
_MIN_RAIZ = 3
```

Y las funciones:

```python
def _read_words(path: Path) -> set[str]:
    words = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return words
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            words.add(line.lower())
    return words


def load_base_glossary() -> set[str]:
    return _read_words(BASE_GLOSSARY_PATH)


def load_glossary(path: Path, incluir_base: bool = True) -> set[str]:
    words = _read_words(path)
    return words | load_base_glossary() if incluir_base else words


def in_glossary(word: str, glossary: set[str]) -> bool:
    """La palabra está en el glosario, o es su plural (o su singular)."""
    w = word.lower()
    if w in glossary:
        return True
    for suf in _PLURALES:
        if w.endswith(suf) and len(w) - len(suf) >= _MIN_RAIZ and w[: -len(suf)] in glossary:
            return True
        if f"{w}{suf}" in glossary:
            return True
    return False
```

Sustituye la comprobación `w.lower() in glossary` de `unknown_words` por `in_glossary(w, glossary)`, y en `_Vocab.known` la comprobación `part in self.glossary` por `in_glossary(part, self.glossary)`.

- [ ] **Step 5: Empaquetar el archivo de datos**

En `pyproject.toml`, dentro de `[tool.hatch.build.targets.wheel.force-include]`, añade la línea:

```toml
"videoqa/data/glosario_base.txt" = "videoqa/data/glosario_base.txt"
```

- [ ] **Step 6: Correr toda la suite**

Run: `uv run pytest -q`
Expected: verde. Ojo: algún test existente puede dar por hecho que `load_glossary` de un archivo inexistente devuelve `set()`; si es así, actualízalo para que use `incluir_base=False` o compruebe la inclusión, y deja un comentario de por qué.

- [ ] **Step 7: Commit**

```bash
git add videoqa/data/glosario_base.txt videoqa/checks/spelling.py pyproject.toml tests/unit/test_spelling.py
git commit -m "feat: glosario base empaquetado y plurales aceptados en el glosario"
```

---

### Task 3: Comando `videoqa glosario` para sembrar y ampliar

**Files:**
- Create: `videoqa/glosario.py`
- Modify: `videoqa/cli.py` (subcomando `glosario`)
- Test: `tests/unit/test_glosario.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: `load_glossary`, `in_glossary` (Task 2); `Settings.config_dir` y `Settings.jobs_dir`.
- Produces: `videoqa.glosario.candidatas(jobs_dir: Path, glossary: set[str]) -> list[tuple[str, int, int]]`: recorre `jobs_dir/*/findings_code.json`, saca las palabras de los hallazgos cuyo `check` empieza por `spelling` y cuyo `title` tiene `:` (el formato es `Posible error ortográfico: a, b`), descarta las que ya acepta el glosario, y devuelve `(palabra, apariciones, nº de videos)` ordenado por apariciones y luego alfabéticamente.
- Produces: `videoqa.glosario.agregar(path: Path, palabras: list[str]) -> list[str]`: añade al final del archivo del equipo las que falten (una por línea, en minúsculas, creando el archivo con una cabecera si no existe), y devuelve las realmente añadidas.
- Produces: CLI `videoqa glosario` (lista las candidatas, una por línea, formato `palabra<TAB>apariciones<TAB>videos`, y una primera línea `CANDIDATAS <n>`), y `videoqa glosario --agregar "a,b,c"` (imprime `AGREGADAS: a, b` o `AGREGADAS: ninguna`). Sale 0 siempre que la configuración exista.

- [ ] **Step 1: Tests del módulo**

`tests/unit/test_glosario.py`:

```python
"""El glosario del equipo se siembra desde lo ya revisado: estos tests fijan qué
palabras se proponen y cómo se añaden sin duplicar."""
from __future__ import annotations

import json
from pathlib import Path

from videoqa.glosario import agregar, candidatas


def _job(jobs: Path, nombre: str, titulos: list[str]) -> None:
    d = jobs / nombre
    d.mkdir(parents=True)
    findings = [{"check": "spelling_unknown_word", "title": t} for t in titulos]
    (d / "findings_code.json").write_text(json.dumps(findings, ensure_ascii=False))


def test_candidatas_cuenta_apariciones_y_videos(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva", "Posible error ortográfico: canva, klook"])
    _job(jobs, "b", ["Posible error ortográfico: canva"])
    out = candidatas(jobs, set())
    assert out[0] == ("canva", 3, 2)
    assert ("klook", 1, 1) in out


def test_candidatas_descarta_lo_que_ya_acepta_el_glosario(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva, corillos"])
    out = candidatas(jobs, {"canva", "corillo"})   # "corillos" entra por plural
    assert [w for w, _, _ in out] == []


def test_candidatas_ignora_hallazgos_que_no_son_de_ortografia(tmp_path):
    jobs = tmp_path / "jobs"
    d = jobs / "a"
    d.mkdir(parents=True)
    (d / "findings_code.json").write_text(json.dumps(
        [{"check": "brand_color", "title": "Color de texto fuera de marca: #FFF"}]))
    assert candidatas(jobs, set()) == []


def test_candidatas_sin_carpeta_de_trabajos(tmp_path):
    assert candidatas(tmp_path / "no_existe", set()) == []


def test_candidatas_salta_un_json_roto(tmp_path):
    jobs = tmp_path / "jobs"
    _job(jobs, "a", ["Posible error ortográfico: canva"])
    roto = jobs / "b"
    roto.mkdir()
    (roto / "findings_code.json").write_text("{no es json")
    assert [w for w, _, _ in candidatas(jobs, set())] == ["canva"]


def test_agregar_crea_el_archivo_con_cabecera(tmp_path):
    p = tmp_path / "glosario.txt"
    assert agregar(p, ["Canva", "klook"]) == ["canva", "klook"]
    texto = p.read_text(encoding="utf-8")
    assert texto.startswith("#")
    assert "canva" in texto.splitlines()
    assert "klook" in texto.splitlines()


def test_agregar_no_duplica(tmp_path):
    p = tmp_path / "glosario.txt"
    agregar(p, ["canva"])
    assert agregar(p, ["canva", "klook"]) == ["klook"]
    assert p.read_text(encoding="utf-8").splitlines().count("canva") == 1


def test_agregar_respeta_lo_que_ya_habia(tmp_path):
    p = tmp_path / "glosario.txt"
    p.write_text("# mis palabras\nkasa\n")
    agregar(p, ["klook"])
    lineas = p.read_text(encoding="utf-8").splitlines()
    assert "kasa" in lineas and "klook" in lineas
```

- [ ] **Step 2: Correr y ver fallar**

Run: `uv run pytest tests/unit/test_glosario.py -q`
Expected: FAIL, `ModuleNotFoundError: videoqa.glosario`.

- [ ] **Step 3: Implementar `videoqa/glosario.py`**

```python
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
    if not str(finding.get("check", "")).startswith("spelling"):
        return []
    titulo = str(finding.get("title", ""))
    if ":" not in titulo:
        return []
    return [w.strip().lower() for w in titulo.split(":", 1)[1].split(",") if w.strip()]


def candidatas(jobs_dir: Path, glossary: set[str]) -> list[tuple[str, int, int]]:
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
    with path.open("a", encoding="utf-8") as fh:
        if path.stat().st_size and not path.read_text(encoding="utf-8").endswith("\n"):
            fh.write("\n")
        for w in nuevas:
            fh.write(f"{w}\n")
    return nuevas
```

Nota de implementación: leer el archivo entero dentro del `with` para comprobar el salto final es torpe; calcula ese dato ANTES de abrir en modo append y guarda el booleano.

- [ ] **Step 4: Tests del CLI**

Añadir a `tests/unit/test_cli.py` (siguiendo el patrón de los otros: `main(["init", ...])` primero):

```python
def test_glosario_lista_candidatas(tmp_path, monkeypatch, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    jobs = videoqa_home() / "jobs" / "v1"
    jobs.mkdir(parents=True)
    (jobs / "findings_code.json").write_text(json.dumps(
        [{"check": "spelling_unknown_word", "title": "Posible error ortográfico: klook"}]))
    assert main(["glosario"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "CANDIDATAS 1"
    assert "klook" in out


def test_glosario_agrega_al_archivo_del_equipo(tmp_path, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    assert main(["glosario", "--agregar", "Klook, canva"]) == 0
    assert "AGREGADAS: klook, canva" in capsys.readouterr().out
    assert "klook" in (drive / "_config" / "glosario.txt").read_text(encoding="utf-8")


def test_glosario_agregar_sin_novedades(tmp_path, capsys):
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    main(["glosario", "--agregar", "klook"])
    capsys.readouterr()
    main(["glosario", "--agregar", "klook"])
    assert "AGREGADAS: ninguna" in capsys.readouterr().out
```

- [ ] **Step 5: Implementar el subcomando en `videoqa/cli.py`**

```python
def cmd_glosario(args) -> int:
    settings = load_settings()
    ruta = settings.config_dir / "glosario.txt"
    if args.agregar:
        nuevas = agregar(ruta, [w for w in args.agregar.split(",")])
        print(f"AGREGADAS: {', '.join(nuevas) if nuevas else 'ninguna'}")
        return 0
    glossary = load_glossary(ruta)
    filas = candidatas(settings.jobs_dir, glossary)
    print(f"CANDIDATAS {len(filas)}")
    for palabra, veces, videos in filas:
        print(f"{palabra}\t{veces}\t{videos}")
    return 0
```

En `main`:

```python
    p = sub.add_parser("glosario", help="proponer palabras para el glosario del equipo")
    p.add_argument("--agregar", metavar="PALABRAS", help="añadir estas palabras (separadas por comas)")
    p.set_defaults(fn=cmd_glosario)
```

Con los imports correspondientes (`from videoqa.checks.spelling import load_glossary`, `from videoqa.glosario import agregar, candidatas`).

- [ ] **Step 6: Correr toda la suite**

Run: `uv run pytest -q`
Expected: verde.

- [ ] **Step 7: Commit**

```bash
git add videoqa/glosario.py videoqa/cli.py tests/unit/test_glosario.py tests/unit/test_cli.py
git commit -m "feat: comando glosario para sembrar y ampliar las palabras del equipo"
```

---

### Task 4: Skills de Aura para el glosario y los idiomas

**Files:**
- Modify: `plugins/aura/skills/ajustar/SKILL.md`
- Modify: `plugins/aura/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (versión `1.4.0`)
- Modify: `plugins/aura/README.md`, `LEEME.md` si mencionan el glosario
- Test: `tests/unit/test_plugin_layout.py`

**Interfaces:**
- Consumes: `videoqa glosario` y `videoqa glosario --agregar` (Task 3); la clave `idiomas` de la configuración (Task 1).

- [ ] **Step 1: Añadir el Caso D a `ajustar/SKILL.md`**

Después del "Caso A", con este texto (adaptando el tono al resto del archivo):

```markdown
## Caso D — "Llena el glosario" / "revisa qué palabras marca mal"

Sirve para sembrar el glosario de golpe con lo que ya se revisó, en vez de ir palabra por
palabra. Úsalo también la primera vez que se configura el equipo.

```bash
uv run --project ~/videoqa videoqa glosario
```

La primera línea dice cuántas candidatas hay; luego una por línea con las veces que se marcó
y en cuántos videos. **No le enseñes la tabla en crudo.** Preséntalas agrupadas y en
castellano, empezando por las más repetidas:

> Encontré 18 palabras que se marcaron como error y probablemente no lo son:
>
> - **Nombres de marca o herramientas:** Canva, Klook, Educanab
> - **Palabras en inglés:** earnings, calendar, featured
> - **Jerga:** corillo, chamba
>
> ¿Las añado todas a la lista de palabras válidas? Si alguna SÍ es una falta, dime cuál y la dejo fuera.

Con el sí (y quitando las que te diga):

```bash
uv run --project ~/videoqa videoqa glosario --agregar "canva,klook,educanab,earnings"
```

Confirma en una línea cuántas quedaron añadidas. Si la respuesta es `AGREGADAS: ninguna`, dile
que ya estaban todas.

Si no hay candidatas (`CANDIDATAS 0`), díselo así: "No hay palabras pendientes: el corrector no
está marcando nada raro."
```

- [ ] **Step 2: Añadir el Caso E (idiomas) a `ajustar/SKILL.md`**

```markdown
## Caso E — "Marca mal las palabras en inglés" / "solo revisa español"

El corrector consulta español e inglés: una palabra solo es falta si no existe en ninguno de
los dos. Se cambia con la clave `idiomas` de `~/.videoqa/config.yaml`.

- Si los videos son solo en español y quieren que el inglés SÍ se marque: deja `idiomas: [es]`.
- Si vuelve a marcar inglés correcto: comprueba que la línea diga `idiomas: [es, en]`.

Explícalo así: "Ahora mismo acepto palabras en español y en inglés. Si quieres que marque el
inglés como error, lo dejo solo en español. ¿Lo cambio?" Con el sí, edita esa línea con Edit
(créala si no está) y recuerda que solo afecta a los videos que se revisen a partir de ahora.
```

- [ ] **Step 3: Ampliar el Caso A con el formato del archivo**

En el Caso A, tras el punto 2, añade una línea: "Si el archivo está creciendo, agrupa las palabras por cuenta con un comentario encima (`# Goldstone`), para que dentro de unos meses se entienda por qué está cada una."

Y en "Cómo explicar el resultado", añade: "El programa ya trae de fábrica una lista de palabras de redes, anglicismos y jerga (reel, hashtag, Canva, chévere…). No hace falta añadir esas: si te piden una que ya viene, dilo y no toques el archivo."

- [ ] **Step 4: Actualizar la descripción del frontmatter**

`description` de `ajustar` (máximo 200 caracteres, sin el campo `name`):

```
Cambia qué se marca como error, llena el glosario con las palabras del equipo y sube o baja la gravedad. Úsalo si dice "no marques X", "llena el glosario" o "que el silencio bloquee".
```

- [ ] **Step 5: Versión y documentación**

- `plugins/aura/.claude-plugin/plugin.json` y `.claude-plugin/marketplace.json`: `"version": "1.4.0"`.
- Si `plugins/aura/README.md` o `LEEME.md` describen `/aura:ajustar`, añade que también llena el glosario.

- [ ] **Step 6: Correr**

Run: `uv run pytest tests/unit/test_plugin_layout.py -q && uv run pytest -q`
Expected: verde.

- [ ] **Step 7: Commit**

```bash
git add plugins/aura .claude-plugin/marketplace.json LEEME.md
git commit -m "feat(aura): ajustar llena el glosario y gestiona los idiomas — aura 1.4.0"
```

---

### Task 5: Prueba manual en esta Mac (la hace el orquestador, sin subagente)

- [ ] **Step 1:** `uv run videoqa glosario` lista candidatas y ya NO incluye las palabras inglesas corrientes (moment, earnings, calendar, wanna, gonna) ni las del glosario base.
- [ ] **Step 2:** `uv run videoqa glosario --agregar "canva,klook,educanab,dediktok"` crea `~/Desktop/videos/_config/glosario.txt` con cabecera y sin duplicados; repetirlo dice `AGREGADAS: ninguna`.
- [ ] **Step 3:** Volver a revisar uno de los videos ya revisados (borrando antes su carpeta de trabajo para que no use la caché) y comprobar que bajan los hallazgos de ortografía falsos.
