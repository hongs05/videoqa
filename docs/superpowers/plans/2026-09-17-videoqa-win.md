# VideoQA para Windows (`videoqa-win`) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que los editores del equipo hagan un pre-chequeo local de sus videos en Windows, sin cuenta de ninguna IA estadounidense, reutilizando el motor `videoqa` como librería.

**Architecture:** Dos proyectos. El motor (`hongs05/videoqa`) gana dependencias de Apple opcionales, un registro de backends y un reporte HTML. Un repo nuevo (`hongs05/videoqa-win`) depende del motor por git y aporta tres backends portables (RapidOCR, faster-whisper, spylls), la interfaz de Windows en `.bat`, el instalador y un juez local opcional por Ollama. Las dos instalaciones trabajan sobre carpetas distintas y nunca se coordinan.

**Tech Stack:** Python 3.12 (uv en desarrollo, venv en Windows), ffmpeg, `rapidocr-onnxruntime`, `faster-whisper` (CTranslate2), `spylls` + diccionario `es_ES` de LibreOffice, `onnxruntime`, opcional Ollama + `qwen2.5vl:3b`, `.bat` para la interfaz, `winget` para instalar dependencias del sistema.

**Spec:** `docs/superpowers/specs/2026-09-17-videoqa-win-design.md`

## Global Constraints

- Python **3.12** en las dos plataformas (`requires-python = ">=3.12,<3.13"`).
- El motor conserva **exactamente** el comportamiento actual en macOS: si no hay backend registrado, usa la pila de Apple. Los 203 tests existentes deben seguir verdes sin modificarse (salvo los que el plan cambia explícitamente).
- Contratos de backend, idénticos a las firmas que ya existen en el motor:
  - OCR: `fn(path: Path) -> list[dict]`, cada dict `{"text": str, "conf": float, "bbox": [x, y, w, h]}` **normalizado 0-1, origen arriba-izquierda**.
  - Transcripción: `fn(job, has_audio: bool, model: str) -> {"language": str, "text": str, "segments": [{"start": float, "end": float, "text": str}]}`.
  - Corrector: `fn() -> objeto` con `is_known(word) -> bool`, `unknown(words) -> set[str]`, `correction(word) -> str | None`.
- **Datos verificados** (no re-investigar):
  - RapidOCR: `engine = RapidOCR()`; `res, elapse = engine(str(path))`; `res` es `list[[box, text, score]]` o `None`; `box` son 4 puntos `[[x,y],…]` **en píxeles**; el modelo incluido (`ch_PP-OCRv4_rec`) **pierde las tildes** (`"No, me lo comí."` → `"No, me lo comi."`).
  - faster-whisper: `WhisperModel(name, device="cpu"|"cuda", compute_type="int8"|"float16")`; `segments, info = m.transcribe(path, language="es")`; `segments` es un generador con `.start`, `.end`, `.text`; `info` tiene `.language` y `.duration`.
  - spylls: `Dictionary.from_files("<ruta sin extensión>")`; `.lookup(word) -> bool`; `.suggest(word) -> generator[str]`. **No trae diccionarios**: hay que descargar `es_ES.aff` (169 KB) y `es_ES.dic` (716 KB) de `https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/es_ES.{aff,dic}`.
- Todo texto de usuario en **español** informal, sin jerga y sin trazas de Python.
- Umbrales y severidades siguen viniendo de `reglas.yaml`. Si un backend necesita otro umbral, se ajusta **dentro del backend**, nunca en `reglas.yaml`.
- Ninguna dependencia con PyTorch ni que requiera compilar.
- Los `.bat` empiezan con `@echo off` y `chcp 65001 >nul` (UTF-8) y citan todas las rutas.
- Commits con mensaje en español, prefijo `feat:`/`fix:`/`docs:`/`test:`/`chore:`.

---

## Mapa de archivos

### Parte A — motor `videoqa` (repo actual)

| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml` | mueve `mlx-whisper`/`ocrmac`/`pyobjc` a `[project.optional-dependencies].macos`; añade *package data* de `videoqa/prompts` |
| `videoqa/backends.py` | registro de los tres backends + resolución con respaldo Apple |
| `videoqa/stages/ocr.py` | `ocr_frame` consulta el registro |
| `videoqa/stages/transcribe.py` | `transcribe` consulta el registro |
| `videoqa/checks/spelling.py` | el corrector por defecto viene del registro |
| `videoqa/prompts/revisor-video.md` | prompt del juez, dentro del paquete |
| `videoqa/config.py` | `SKILL_PATH` apunta al prompt del paquete, con respaldo al repo |
| `videoqa/report_html.py` | `reporte.html` con evidencia incrustada |
| `videoqa/pipeline.py` | escribe también el HTML cuando `reglas.yaml` lo pide |
| `reglas.yaml` | `salida.reporte_html: false` (true en Windows) |
| `tests/unit/test_backends.py` | registro y respaldo |
| `tests/unit/test_prompt_packaged.py` | el prompt del paquete y el de `.claude/skills` coinciden |
| `tests/unit/test_report_html.py` | estructura del HTML |

### Parte B — repo nuevo `videoqa-win`

| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml` | depende de `videoqa @ git+…`, `rapidocr-onnxruntime`, `faster-whisper`, `spylls`; script `videoqa-win` |
| `videoqa_win/__init__.py` | `activar()` registra los tres backends |
| `videoqa_win/ocr_rapid.py` | backend OCR + conversión de caja + tolerancia a tildes |
| `videoqa_win/asr_faster.py` | backend de transcripción + elección CPU/GPU |
| `videoqa_win/spell_spylls.py` | backend corrector + descarga del diccionario |
| `videoqa_win/acentos.py` | normalización y regla "solo difiere en tildes" |
| `videoqa_win/paths.py` | rutas de Windows (`%USERPROFILE%\VideoQA`, modelos, registro) |
| `videoqa_win/cli.py` | `videoqa-win instalar-datos | revisar | watch | diagnostico` |
| `videoqa_win/judge_ollama.py` | `Runner` contra Ollama (opcional) |
| `bat/Instalar VideoQA.bat` | instalador |
| `bat/Revisar video.bat` | arrastrar y soltar |
| `bat/Activar automatico.bat` | alta/baja en Inicio |
| `bat/Diagnostico.bat` | informe de diagnóstico |
| `bat/Actualizar VideoQA.bat` | actualización |
| `LEEME.md` | guía de una página para el editor |
| `tests/…` | unitarios por backend + integración |

---

## Parte A — cambios en el motor

### Task 1: Dependencias de Apple opcionales y registro de backends

**Files:**
- Create: `videoqa/backends.py`, `tests/unit/test_backends.py`
- Modify: `pyproject.toml`, `videoqa/stages/ocr.py`, `videoqa/stages/transcribe.py`, `videoqa/checks/spelling.py`, `instalar/install.sh`, `plugins/aura/skills/instalar/SKILL.md`

**Interfaces:**
- Produces:
  - `videoqa.backends.register_ocr(fn)`, `register_transcriber(fn)`, `register_speller(fn)`
  - `videoqa.backends.get_ocr()`, `get_transcriber()`, `get_speller()` — devuelven lo registrado o el valor por defecto de Apple
  - `videoqa.backends.reset()` — solo para tests

- [ ] **Step 1: Escribir el test que falla**

`tests/unit/test_backends.py`:
```python
import pytest
from videoqa import backends


@pytest.fixture(autouse=True)
def _limpio():
    backends.reset()
    yield
    backends.reset()


def test_sin_registro_devuelve_los_de_apple():
    from videoqa.stages.ocr import _ocr_frame_apple
    from videoqa.stages.transcribe import _transcribe_apple
    from videoqa.checks.spelling import MacSpellChecker

    assert backends.get_ocr() is _ocr_frame_apple
    assert backends.get_transcriber() is _transcribe_apple
    assert backends.get_speller() is MacSpellChecker


def test_registrar_reemplaza():
    def ocr(path):
        return [{"text": "x", "conf": 1.0, "bbox": [0, 0, 1, 1]}]

    backends.register_ocr(ocr)
    assert backends.get_ocr() is ocr


def test_reset_vuelve_al_defecto():
    backends.register_ocr(lambda path: [])
    backends.reset()
    from videoqa.stages.ocr import _ocr_frame_apple

    assert backends.get_ocr() is _ocr_frame_apple


def test_ocr_frame_usa_el_registrado(tmp_path):
    from videoqa.stages.ocr import ocr_frame

    llamadas = []

    def ocr(path):
        llamadas.append(path)
        return [{"text": "hola", "conf": 0.9, "bbox": [0.1, 0.2, 0.3, 0.4]}]

    backends.register_ocr(ocr)
    out = ocr_frame(tmp_path / "f.jpg")
    assert out[0]["text"] == "hola" and llamadas == [tmp_path / "f.jpg"]


def test_transcribe_usa_el_registrado(tmp_path):
    from videoqa.job import Job
    from videoqa.stages.transcribe import transcribe

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")

    def asr(job, has_audio, model):
        return {"language": "es", "text": "hola", "segments": [{"start": 0.0, "end": 1.0, "text": "hola"}]}

    backends.register_transcriber(asr)
    assert transcribe(job, True, "modelo")["text"] == "hola"


def test_check_spelling_usa_el_corrector_registrado():
    from videoqa.checks.spelling import check_spelling
    from videoqa.config import load_rules

    class Corrector:
        def is_known(self, w):
            return w.lower() != "kasa"

        def unknown(self, words):
            return {w for w in words if not self.is_known(w)}

        def correction(self, w):
            return "casa"

    backends.register_speller(lambda: Corrector())
    apps = [{"text": "la kasa", "bbox": [0.1, 0.4, 0.5, 0.1], "t_start": 1.0, "t_end": 3.0,
             "frame": "frames/a.jpg", "frames": [], "conf": 1.0}]
    fs = check_spelling(apps, set(), load_rules())
    assert len(fs) == 1 and "kasa" in fs[0].title and "casa" in fs[0].suggestion
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_backends.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa.backends` (y no existen `_ocr_frame_apple` / `_transcribe_apple`).

- [ ] **Step 3: Crear `videoqa/backends.py`**

```python
"""Registro de implementaciones dependientes del sistema operativo.

El motor trae la pila de Apple (Vision, MLX, NSSpellChecker) como valor por
defecto. Un proyecto que corra en otra plataforma — por ejemplo videoqa-win —
registra aquí sus propias implementaciones antes de usar el pipeline.
"""
from __future__ import annotations

from typing import Callable

_ocr: Callable | None = None
_transcriber: Callable | None = None
_speller: Callable | None = None


def register_ocr(fn: Callable) -> None:
    """fn(path) -> [{"text", "conf", "bbox": [x, y, w, h] normalizado}]"""
    global _ocr
    _ocr = fn


def register_transcriber(fn: Callable) -> None:
    """fn(job, has_audio, model) -> {"language", "text", "segments"}"""
    global _transcriber
    _transcriber = fn


def register_speller(fn: Callable) -> None:
    """fn() -> objeto con is_known / unknown / correction"""
    global _speller
    _speller = fn


def reset() -> None:
    """Vuelve a los valores por defecto. Pensado para los tests."""
    global _ocr, _transcriber, _speller
    _ocr = _transcriber = _speller = None


def get_ocr() -> Callable:
    if _ocr is not None:
        return _ocr
    from videoqa.stages.ocr import _ocr_frame_apple

    return _ocr_frame_apple


def get_transcriber() -> Callable:
    if _transcriber is not None:
        return _transcriber
    from videoqa.stages.transcribe import _transcribe_apple

    return _transcribe_apple


def get_speller() -> Callable:
    if _speller is not None:
        return _speller
    from videoqa.checks.spelling import MacSpellChecker

    return MacSpellChecker
```

- [ ] **Step 4: Renombrar las implementaciones de Apple y delegar al registro**

En `videoqa/stages/ocr.py`, renombra la función actual `ocr_frame` a `_ocr_frame_apple` (deja su cuerpo intacto, incluido el import tardío de `ocrmac` y la conversión de origen) y añade:

```python
def ocr_frame(path: Path) -> list[dict]:
    from videoqa import backends

    return backends.get_ocr()(path)
```

En `videoqa/stages/transcribe.py`, renombra la función actual `transcribe` a `_transcribe_apple` y añade:

```python
def transcribe(job: Job, has_audio: bool, model: str) -> dict:
    from videoqa import backends

    return backends.get_transcriber()(job, has_audio, model)
```

Cuidado: `_transcribe_apple` conserva el atajo de "sin audio" (`return empty_transcript()`), porque ese comportamiento es común a cualquier backend y los tests actuales lo cubren. Deja también esa comprobación en `transcribe` **antes** de delegar, para que un backend nuevo no tenga que repetirla:

```python
def transcribe(job: Job, has_audio: bool, model: str) -> dict:
    from videoqa import backends

    if not has_audio:
        return empty_transcript()
    return backends.get_transcriber()(job, has_audio, model)
```

En `videoqa/checks/spelling.py`, dentro de `check_spelling`, sustituye la construcción directa del corrector:

```python
    if checker is None:
        from videoqa import backends

        checker = backends.get_speller()()
```

- [ ] **Step 5: Correr los tests del registro y la suite completa**

Run: `uv run pytest tests/unit/test_backends.py -q`
Expected: 6 passed.

Run: `uv run pytest -q`
Expected: los 203 de antes + 6 = 209 passed, 1 skipped. Si alguno falla por el renombrado (algún test importa `ocr_frame` o `transcribe` directamente), el fallo es correcto solo si el test esperaba la implementación de Apple: en ese caso apunta al nombre nuevo `_ocr_frame_apple` / `_transcribe_apple` y explica el cambio en el informe.

- [ ] **Step 6: Mover las dependencias de Apple a un extra**

En `pyproject.toml`, `dependencies` queda:

```toml
dependencies = [
    "pyyaml>=6.0",
    "numpy>=1.26",
    "pillow>=10.0",
    "gspread>=6.0",
    "google-auth>=2.0",
]

[project.optional-dependencies]
macos = [
    "mlx-whisper>=0.4",
    "ocrmac>=1.0",
    # Usado por videoqa/checks/spelling.py (NSSpellChecker de AppKit).
    "pyobjc-framework-Cocoa>=10",
]
```

Actualiza quien instala el motor en macOS:
- `instalar/install.sh`: donde haga `uv sync`/instalación del motor, que use el extra (`uv sync --extra macos` en el repo, o `pip install "videoqa[macos] @ git+…"`).
- `plugins/aura/skills/instalar/SKILL.md`: el paso que prepara Python pasa a `uv sync --extra macos --project ~/videoqa`.

- [ ] **Step 7: Verificar que el extra funciona y que sin él el motor importa**

```bash
uv sync --extra macos
uv run pytest -q
uv run python -c "import videoqa.pipeline, videoqa.backends; print('el motor importa sin tocar Apple')"
```
Expected: suite verde y el import sin errores.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock videoqa/backends.py videoqa/stages/ocr.py videoqa/stages/transcribe.py videoqa/checks/spelling.py tests/unit/test_backends.py instalar/install.sh "plugins/aura/skills/instalar/SKILL.md"
git commit -m "feat: registro de backends y dependencias de Apple opcionales"
```

---

### Task 2: El prompt del juez viaja dentro del paquete

**Files:**
- Create: `videoqa/prompts/__init__.py`, `videoqa/prompts/revisor-video.md`, `tests/unit/test_prompt_packaged.py`
- Modify: `videoqa/config.py`, `pyproject.toml`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces: `videoqa.config.SKILL_PATH` resuelve al prompt del paquete; el archivo de `.claude/skills/revisor-video/SKILL.md` sigue existiendo y su cuerpo coincide con el del paquete.

- [ ] **Step 1: Escribir el test que falla**

`tests/unit/test_prompt_packaged.py`:
```python
from pathlib import Path

from videoqa.config import SKILL_PATH

REPO_SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "revisor-video" / "SKILL.md"


def _cuerpo(texto: str) -> str:
    """Devuelve el contenido sin el frontmatter YAML (--- … ---)."""
    if texto.startswith("---"):
        return texto.split("---", 2)[2].strip()
    return texto.strip()


def test_el_prompt_vive_dentro_del_paquete():
    import videoqa

    paquete = Path(videoqa.__file__).resolve().parent
    assert SKILL_PATH.exists()
    assert SKILL_PATH.is_relative_to(paquete), f"{SKILL_PATH} está fuera del paquete"


def test_el_prompt_del_paquete_y_el_de_claude_code_coinciden():
    assert REPO_SKILL.exists(), "la skill que lee Claude Code tiene que seguir ahí"
    assert _cuerpo(SKILL_PATH.read_text(encoding="utf-8")) == _cuerpo(REPO_SKILL.read_text(encoding="utf-8"))


def test_el_prompt_tiene_las_secciones_clave():
    texto = SKILL_PATH.read_text(encoding="utf-8")
    for seccion in ("# Rol", "# Entradas", "# Qué revisar", "# Guion real", "# Salida", "# Seguridad"):
        assert seccion in texto, f"falta la sección {seccion}"
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_prompt_packaged.py -q`
Expected: FAIL — `SKILL_PATH` apunta fuera del paquete (`test_el_prompt_vive_dentro_del_paquete`).

- [ ] **Step 3: Copiar el prompt al paquete**

```bash
mkdir -p videoqa/prompts
touch videoqa/prompts/__init__.py
cp .claude/skills/revisor-video/SKILL.md videoqa/prompts/revisor-video.md
```

- [ ] **Step 4: Resolver `SKILL_PATH` desde el paquete**

En `videoqa/config.py`, sustituye la línea de `SKILL_PATH` por:

```python
_PROMPT_PAQUETE = Path(__file__).resolve().parent / "prompts" / "revisor-video.md"
_PROMPT_REPO = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "revisor-video" / "SKILL.md"

# El prompt del juez viaja dentro del paquete para que funcione instalado con
# pip; en el repo de desarrollo se prefiere el del paquete igualmente, y el de
# .claude/skills queda como el que lee Claude Code (un test comprueba que no se
# desincronicen).
SKILL_PATH = _PROMPT_PAQUETE if _PROMPT_PAQUETE.exists() else _PROMPT_REPO
```

- [ ] **Step 5: Incluir el prompt en el paquete instalado**

En `pyproject.toml`, bajo la sección de build:

```toml
[tool.hatch.build.targets.wheel]
packages = ["videoqa"]

[tool.hatch.build.targets.wheel.force-include]
"videoqa/prompts/revisor-video.md" = "videoqa/prompts/revisor-video.md"
```

- [ ] **Step 6: Correr los tests**

Run: `uv run pytest tests/unit/test_prompt_packaged.py tests/unit/test_judge.py -q`
Expected: 3 + 30 passed.

Run: `uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Comprobar que el wheel lleva el prompt**

```bash
uv build --wheel -o /tmp/vqa-wheel
python3 -c "
import zipfile, glob
w = glob.glob('/tmp/vqa-wheel/*.whl')[0]
nombres = zipfile.ZipFile(w).namelist()
assert 'videoqa/prompts/revisor-video.md' in nombres, nombres[:20]
print('el wheel incluye el prompt')
"
```
Expected: "el wheel incluye el prompt".

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml videoqa/config.py videoqa/prompts tests/unit/test_prompt_packaged.py
git commit -m "feat: el prompt del juez viaja dentro del paquete"
```

---

### Task 3: Reporte HTML con evidencia incrustada

**Files:**
- Create: `videoqa/report_html.py`, `tests/unit/test_report_html.py`
- Modify: `videoqa/pipeline.py`, `videoqa/gate.py`, `reglas.yaml`

**Interfaces:**
- Consumes: `videoqa.report.fmt_t`, `CHECK_LABELS`, `TYPE_LABELS`, `STATUS`, `JUDGE_CHECKS` y `videoqa.findings.sort_findings/count_by_severity`.
- Produces: `videoqa.report_html.render_html(video_name, probe, findings, status, evidence, when) -> str` y `build_html_report(job, probe, findings, status, evidence, when=None) -> Path` (escribe `reporte.html` en el job dir). `videoqa/gate.py::deliver` copia `reporte.html` si existe.

- [ ] **Step 1: Escribir el test que falla**

`tests/unit/test_report_html.py`:
```python
from datetime import datetime

from PIL import Image

from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.report_html import build_html_report, render_html

PROBE = {"duration": 58.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}


def fnd(id, sev, t, check="brand_color", typ="marca", frame=None):
    return Finding(id=id, type=typ, severity=sev, t_start=t, t_end=t + 1, title=f"T{id}",
                   detail=f"D{id}", suggestion="S", frame=frame, check=check)


def test_html_rechazado_tiene_semaforo_y_secciones():
    fs = [fnd("b", "blocker", 12), fnd("w", "warning", 3, check="silence", typ="tecnico")]
    html = render_html("promo.mp4", PROBE, fs, "rejected", {}, datetime(2026, 9, 17, 14, 32))
    assert html.startswith("<!doctype html>")
    assert "promo.mp4" in html and "NO APROBADO" in html
    assert "Bloqueantes" in html and "Advertencias" in html
    assert "0:12" in html and "0:03" in html
    assert html.index("Bloqueantes") < html.index("Advertencias")
    assert "<html lang=\"es\">" in html


def test_html_aprobado_no_lista_bloqueantes():
    html = render_html("ok.mp4", PROBE, [], "approved", {}, datetime(2026, 9, 17))
    assert "APROBADO" in html and "NO APROBADO" not in html
    assert "Bloqueantes" not in html


def test_la_evidencia_va_incrustada_en_base64(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "evidencia").mkdir()
    Image.new("RGB", (40, 30), (255, 0, 0)).save(job.path("evidencia/01_0m12s.jpg"))
    fs = [fnd("b", "blocker", 12, frame="frames/x.jpg")]
    html = render_html("v.mp4", PROBE, fs, "rejected", {"b": "evidencia/01_0m12s.jpg"},
                       datetime(2026, 9, 17), job=job)
    assert "data:image/jpeg;base64," in html
    assert "evidencia/01_0m12s.jpg" not in html.split("data:image")[0][-200:]


def test_evidencia_ausente_no_rompe(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    fs = [fnd("b", "blocker", 12)]
    html = render_html("v.mp4", PROBE, fs, "rejected", {"b": "evidencia/no_existe.jpg"},
                       datetime(2026, 9, 17), job=job)
    assert "data:image" not in html and "T b" not in html and "Tb" in html


def test_build_html_report_escribe_el_archivo(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    p = build_html_report(job, PROBE, [], "approved", {})
    assert p == job.path("reporte.html") and "APROBADO" in p.read_text(encoding="utf-8")


def test_el_html_escapa_el_texto():
    fs = [Finding(id="x", type="marca", severity="blocker", t_start=0, t_end=1,
                  title="<script>alerta</script>", detail="a & b", suggestion="")]
    html = render_html("v.mp4", PROBE, fs, "rejected", {}, datetime(2026, 9, 17))
    assert "<script>alerta</script>" not in html
    assert "&lt;script&gt;" in html and "a &amp; b" in html
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_report_html.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa.report_html`.

- [ ] **Step 3: Implementar `videoqa/report_html.py`**

```python
"""Reporte en HTML con las fotos de evidencia incrustadas.

Pensado para quien no lee markdown a gusto (Windows, o mandar el archivo por
chat): un solo archivo, sin dependencias externas, que se abre con doble clic.
"""
from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from pathlib import Path

from videoqa.findings import Finding, count_by_severity, sort_findings
from videoqa.job import Job
from videoqa.report import CHECK_LABELS, JUDGE_CHECKS, STATUS, TYPE_LABELS, fmt_t

_CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.5 -apple-system, "Segoe UI", system-ui, sans-serif;
       margin: 0 auto; max-width: 52rem; padding: 2rem 1.25rem; }
h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
.meta { color: #666; font-size: .9rem; margin-bottom: 2rem; }
h2 { font-size: 1.15rem; margin: 2rem 0 .75rem; }
.hallazgo { border-left: 4px solid #ccc; padding: .25rem 0 .25rem 1rem; margin: 0 0 1.5rem; }
.hallazgo.blocker { border-color: #d33; }
.hallazgo.warning { border-color: #e9a13b; }
.hallazgo.info { border-color: #4a90d9; }
.hallazgo h3 { font-size: 1rem; margin: 0 0 .35rem; }
.t { font-variant-numeric: tabular-nums; color: #666; font-weight: normal; }
.sug { color: #2a7; }
.hallazgo img { max-width: 100%; border-radius: 6px; margin-top: .6rem; display: block; }
.pasados { color: #666; font-size: .9rem; }
"""


def _img_data_uri(ruta: Path) -> str | None:
    try:
        datos = ruta.read_bytes()
    except OSError:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(datos).decode("ascii")


def _bloque(n: int, f: Finding, evidence: dict[str, str], job: Job | None) -> str:
    span = fmt_t(f.t_start) if f.t_end - f.t_start <= 1.0 else f"{fmt_t(f.t_start)}–{fmt_t(f.t_end)}"
    tipo = TYPE_LABELS.get(f.type, f.type)
    partes = [f'<div class="hallazgo {escape(f.severity)}">',
              f'<h3>{n}. <span class="t">[{escape(span)}]</span> {escape(tipo)} — {escape(f.title)}</h3>',
              f"<p>{escape(f.detail)}</p>"]
    if f.suggestion:
        partes.append(f'<p class="sug">Sugerencia: {escape(f.suggestion)}</p>')
    rel = evidence.get(f.id)
    if rel and job is not None:
        uri = _img_data_uri(job.path(rel))
        if uri:
            partes.append(f'<img alt="Evidencia en {escape(span)}" src="{uri}">')
    partes.append("</div>")
    return "\n".join(partes)


def render_html(video_name: str, probe: dict, findings: list[Finding], status: str,
                evidence: dict[str, str], when: datetime, job: Job | None = None) -> str:
    icono, etiqueta = STATUS[status]
    cuentas = count_by_severity(findings)
    ordenados = sort_findings(findings)
    partes = ["<!doctype html>", '<html lang="es">', "<head>", '<meta charset="utf-8">',
              '<meta name="viewport" content="width=device-width, initial-scale=1">',
              f"<title>{escape(video_name)} — {escape(etiqueta)}</title>",
              f"<style>{_CSS}</style>", "</head>", "<body>",
              f"<h1>{icono} {escape(video_name)} — {escape(etiqueta)}</h1>",
              f'<p class="meta">Revisado: {when:%Y-%m-%d %H:%M} · Duración {fmt_t(probe["duration"])} · '
              f'{probe["width"]}×{probe["height"]} · {cuentas["blocker"]} bloqueantes · '
              f'{cuentas["warning"]} advertencias</p>']
    n = 0
    for sev, titulo in (("blocker", "🔴 Bloqueantes"), ("warning", "⚠️ Advertencias"), ("info", "ℹ️ Información")):
        items = [f for f in ordenados if f.severity == sev]
        if not items:
            continue
        partes.append(f"<h2>{titulo}</h2>")
        for f in items:
            n += 1
            partes.append(_bloque(n, f, evidence, job))

    fallados = {f.check for f in findings}
    juez_caido = status == "error" or "judge_unavailable" in fallados
    pasados = [etq for clave, etq in CHECK_LABELS.items()
               if clave not in fallados and not (juez_caido and clave in JUDGE_CHECKS)]
    partes.append("<h2>✅ Checks pasados</h2>")
    partes.append(f'<p class="pasados">{escape(" · ".join(pasados)) if pasados else "—"}</p>')
    if juez_caido:
        pendientes = [CHECK_LABELS[c] for c in JUDGE_CHECKS if c in CHECK_LABELS]
        partes.append("<h2>⏳ Pendientes de revisión</h2>")
        partes.append(f'<p class="pasados">{escape(" · ".join(pendientes))}</p>')
    partes += ["</body>", "</html>"]
    return "\n".join(partes)


def build_html_report(job: Job, probe: dict, findings: list[Finding], status: str,
                      evidence: dict[str, str], when: datetime | None = None) -> Path:
    html = render_html(job.video.name, probe, findings, status, evidence, when or datetime.now(), job=job)
    out = job.path("reporte.html")
    out.write_text(html, encoding="utf-8")
    return out
```

Si `videoqa/report.py` no expone `TYPE_LABELS` o `JUDGE_CHECKS` con esos nombres exactos, úsalos como estén y ajusta el import (no los redefinas aquí).

- [ ] **Step 4: Correr los tests del HTML**

Run: `uv run pytest tests/unit/test_report_html.py -q`
Expected: 6 passed.

- [ ] **Step 5: Engancharlo al pipeline y al gate**

En `reglas.yaml`, añade al final:

```yaml
salida:
  reporte_html: false    # true para generar también reporte.html (Windows lo activa)
```

En `videoqa/pipeline.py`, justo después de `build_report(...)` (que devuelve la ruta del `.md` y ya calculó la evidencia), genera el HTML cuando toque. `build_report` escribe la evidencia con `write_evidence`, así que reutiliza ese diccionario: cambia la llamada para quedarte con el mapa de evidencia.

En `videoqa/report.py::build_report`, devuelve también la evidencia:

```python
def build_report(job: Job, probe: dict, findings: list[Finding], status: str,
                 when: datetime | None = None) -> tuple[Path, dict[str, str]]:
    evidence = write_evidence(job, findings)
    md = render_report(job.video.name, probe, findings, status, evidence, when or datetime.now())
    out = job.path("reporte.md")
    out.write_text(md, encoding="utf-8")
    return out, evidence
```

Actualiza sus dos llamadores (`videoqa/pipeline.py` y `tests/unit/test_report.py::test_build_report_writes_file`) y en el pipeline añade:

```python
    _, evidencia = build_report(job, p, findings, status)
    if rules.get("salida", {}).get("reporte_html"):
        from videoqa.report_html import build_html_report

        build_html_report(job, p, findings, status, evidencia)
```

En `videoqa/gate.py::deliver`, añade `"reporte.html"` a la tupla de archivos que se copian al destino (junto a `reporte.md` y `guion_real.md`).

- [ ] **Step 6: Test de que el pipeline genera el HTML cuando la regla está activa**

Añade a `tests/integration/test_pipeline.py`:

```python
def test_genera_reporte_html_cuando_la_regla_esta_activa(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    rules = load_rules()
    rules["salida"] = {"reporte_html": True}
    res = process_video(video, s, rules, runner=lambda p, cwd: GOOD_VERDICT)
    assert (res.dest / "reporte.html").exists()
    assert "APROBADO" in (res.dest / "reporte.html").read_text(encoding="utf-8")
```

- [ ] **Step 7: Correr la suite completa**

Run: `uv run pytest -q`
Expected: todo verde (los tests de `test_report.py` y del pipeline ajustados al nuevo valor de retorno de `build_report`).

- [ ] **Step 8: Commit**

```bash
git add videoqa/report_html.py videoqa/report.py videoqa/pipeline.py videoqa/gate.py reglas.yaml tests/unit/test_report_html.py tests/unit/test_report.py tests/integration/test_pipeline.py
git commit -m "feat: reporte HTML con evidencia incrustada"
```

---

## Parte B — el repo `videoqa-win`

Todas las tareas de esta parte se hacen **dentro de `~/videoqa-win`**, un repo git nuevo e independiente. El motor se consume como librería.

### Task 4: Esqueleto del repo y dependencia del motor

**Files (en `~/videoqa-win`):**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `README.md`, `videoqa_win/__init__.py`, `videoqa_win/paths.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/unit/__init__.py`, `tests/unit/test_paths.py`

**Interfaces:**
- Produces:
  - `videoqa_win.paths.datos_dir() -> Path` — `%LOCALAPPDATA%\VideoQA` en Windows, `~/.videoqa-win` en otros (respeta `VIDEOQA_WIN_HOME`)
  - `videoqa_win.paths.trabajo_dir() -> Path` — `%USERPROFILE%\VideoQA` en Windows, `~/VideoQA` en otros (respeta `VIDEOQA_WIN_TRABAJO`)
  - `videoqa_win.paths.modelos_dir()`, `dicts_dir()`, `log_path()` — subcarpetas de `datos_dir()`
  - `videoqa_win.paths.es_windows() -> bool`

- [ ] **Step 1: Crear el repo y el esqueleto**

```bash
mkdir -p ~/videoqa-win && cd ~/videoqa-win && git init -q
mkdir -p videoqa_win tests/unit bat
touch videoqa_win/__init__.py tests/__init__.py tests/unit/__init__.py
cat > .gitignore <<'GI'
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
datos/
GI
curl -fsSL https://raw.githubusercontent.com/hongs05/videoqa/main/LICENSE -o LICENSE
```

- [ ] **Step 2: `pyproject.toml`**

```toml
[project]
name = "videoqa-win"
version = "0.1.0"
description = "VideoQA para Windows — pre-chequeo local de videos antes de subirlos"
requires-python = ">=3.12,<3.13"
dependencies = [
    "videoqa @ git+https://github.com/hongs05/videoqa@main",
    "rapidocr-onnxruntime>=1.3",
    "faster-whisper>=1.1",
    "spylls>=0.1.7",
    "requests>=2.31",
]

[project.scripts]
videoqa-win = "videoqa_win.cli:main"

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["videoqa_win"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["lento: descarga modelos o corre ffmpeg; VIDEOQA_WIN_LENTO=1 para incluirlos"]
```

- [ ] **Step 3: `tests/conftest.py`**

```python
import os

import pytest


def pytest_runtest_setup(item):
    if "lento" in item.keywords and not os.environ.get("VIDEOQA_WIN_LENTO"):
        pytest.skip("test lento: exporta VIDEOQA_WIN_LENTO=1 para correrlo")


@pytest.fixture(autouse=True)
def _aisla_rutas(tmp_path, monkeypatch):
    """Ningún test escribe en las carpetas reales del usuario."""
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "VideoQA"))
```

- [ ] **Step 4: Escribir el test de rutas**

`tests/unit/test_paths.py`:
```python
from pathlib import Path

from videoqa_win import paths


def test_respeta_las_variables_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "t"))
    assert paths.datos_dir() == tmp_path / "d"
    assert paths.trabajo_dir() == tmp_path / "t"


def test_subcarpetas_bajo_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    assert paths.modelos_dir() == tmp_path / "d" / "modelos"
    assert paths.dicts_dir() == tmp_path / "d" / "diccionarios"
    assert paths.log_path() == tmp_path / "d" / "registro.log"


def test_crear_carpetas_de_trabajo(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "t"))
    creadas = paths.crear_carpetas_trabajo()
    for nombre in ("01_Entrada", "02_Con_errores", "03_Aprobado", "_config"):
        assert (tmp_path / "t" / nombre).is_dir()
    assert creadas == tmp_path / "t"


def test_es_windows_es_booleano():
    assert isinstance(paths.es_windows(), bool)
```

- [ ] **Step 5: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.paths`.

- [ ] **Step 6: Implementar `videoqa_win/paths.py`**

```python
"""Rutas del sistema, con variables de entorno para poder aislarlas en tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

CARPETAS_TRABAJO = ("01_Entrada", "02_Con_errores", "03_Aprobado", "_config")


def es_windows() -> bool:
    return sys.platform.startswith("win")


def datos_dir() -> Path:
    """Donde viven modelos, diccionarios y el registro."""
    env = os.environ.get("VIDEOQA_WIN_HOME")
    if env:
        return Path(env).expanduser()
    if es_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "VideoQA"
    return Path.home() / ".videoqa-win"


def trabajo_dir() -> Path:
    """Carpeta visible donde el editor deja los videos."""
    env = os.environ.get("VIDEOQA_WIN_TRABAJO")
    if env:
        return Path(env).expanduser()
    return Path.home() / "VideoQA"


def modelos_dir() -> Path:
    return datos_dir() / "modelos"


def dicts_dir() -> Path:
    return datos_dir() / "diccionarios"


def log_path() -> Path:
    return datos_dir() / "registro.log"


def crear_carpetas_trabajo() -> Path:
    raiz = trabajo_dir()
    for nombre in CARPETAS_TRABAJO:
        (raiz / nombre).mkdir(parents=True, exist_ok=True)
    return raiz
```

- [ ] **Step 7: Instalar y correr**

```bash
cd ~/videoqa-win
uv python install 3.12
uv sync
uv run pytest -q
uv run python -c "import videoqa, videoqa_win.paths; print('motor + win importan')"
```
Expected: 4 passed y el import correcto. Si `uv sync` falla al traer `videoqa` desde git, comprueba que la Task 1 y 2 estén ya en `main` del motor (este repo depende de `@main`) y repórtalo.

- [ ] **Step 8: `README.md` y commit**

`README.md` (corto, en español): qué es, que es el pre-chequeo local para Windows, que el gate oficial sigue en la Mac, cómo instalar (apunta a `LEEME.md`, que llega en la Task 13) y cómo desarrollar (`uv sync`, `uv run pytest`).

```bash
git add -A && git commit -m "chore: esqueleto de videoqa-win con el motor como dependencia"
```

---

### Task 5: Utilidad de acentos

**Files:**
- Create: `videoqa_win/acentos.py`, `tests/unit/test_acentos.py`

**Interfaces:**
- Produces:
  - `videoqa_win.acentos.sin_tildes(texto: str) -> str` — quita diacríticos y pasa a minúsculas
  - `videoqa_win.acentos.solo_difiere_en_tildes(a: str, b: str) -> bool`

- [ ] **Step 1: Escribir el test**

`tests/unit/test_acentos.py`:
```python
from videoqa_win.acentos import sin_tildes, solo_difiere_en_tildes


def test_sin_tildes():
    assert sin_tildes("comí") == "comi"
    assert sin_tildes("TRAICIÓN") == "traicion"
    assert sin_tildes("sándwich") == "sandwich"
    assert sin_tildes("niño") == "nino"
    assert sin_tildes("hola") == "hola"


def test_solo_difiere_en_tildes():
    assert solo_difiere_en_tildes("comi", "comí") is True
    assert solo_difiere_en_tildes("TRAICION", "traición") is True
    assert solo_difiere_en_tildes("nino", "niño") is True
    assert solo_difiere_en_tildes("comi", "como") is False
    assert solo_difiere_en_tildes("aprobecha", "aprovecha") is False
    assert solo_difiere_en_tildes("", "") is True
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_acentos.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `videoqa_win/acentos.py`**

```python
"""Tildes: el OCR local no las distingue, así que hay que compararlas aparte.

El modelo de reconocimiento que trae RapidOCR no incluye los caracteres
acentuados del español: lee "comí" como "comi". Sin esto, cada palabra con
tilde sería un error de ortografía inventado.
"""
from __future__ import annotations

import unicodedata


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    plano = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", plano).lower()


def solo_difiere_en_tildes(a: str, b: str) -> bool:
    """True si las dos palabras son la misma salvo diacríticos y mayúsculas."""
    return sin_tildes(a) == sin_tildes(b)
```

- [ ] **Step 4: Correr los tests**

Run: `uv run pytest tests/unit/test_acentos.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add videoqa_win/acentos.py tests/unit/test_acentos.py
git commit -m "feat: utilidad de comparación sin tildes"
```

---

### Task 6: Backend de corrector ortográfico (spylls)

**Files:**
- Create: `videoqa_win/spell_spylls.py`, `tests/unit/test_spell_spylls.py`

**Interfaces:**
- Consumes: `videoqa_win.paths.dicts_dir()`, `videoqa_win.acentos.solo_difiere_en_tildes`.
- Produces:
  - `videoqa_win.spell_spylls.URLS_DICCIONARIO: dict[str, str]`
  - `descargar_diccionario(destino: Path | None = None) -> Path` — devuelve el prefijo sin extensión (`…/es_ES`)
  - `class SpyllsChecker` con `is_known(word) -> bool`, `unknown(words) -> set[str]`, `correction(word) -> str | None`, y `tilde_probable(word) -> str | None` (la sugerencia que solo difiere en tildes, si existe)

- [ ] **Step 1: Escribir el test**

`tests/unit/test_spell_spylls.py`:
```python
import pytest

from videoqa_win.spell_spylls import URLS_DICCIONARIO, SpyllsChecker, descargar_diccionario


def test_urls_del_diccionario():
    assert set(URLS_DICCIONARIO) == {"aff", "dic"}
    for url in URLS_DICCIONARIO.values():
        assert url.startswith("https://raw.githubusercontent.com/LibreOffice/dictionaries/")


class DiccionarioFalso:
    """Imita spylls.hunspell.Dictionary con un vocabulario mínimo."""

    VOCAB = {"comí", "aprovecha", "oferta", "niño", "casa"}

    def lookup(self, palabra):
        return palabra in self.VOCAB or palabra.lower() in self.VOCAB

    def suggest(self, palabra):
        from videoqa_win.acentos import sin_tildes

        for v in sorted(self.VOCAB):
            if sin_tildes(v) == sin_tildes(palabra):
                yield v
        for v in sorted(self.VOCAB):
            if v.startswith(palabra[:3].lower()) and sin_tildes(v) != sin_tildes(palabra):
                yield v


@pytest.fixture
def checker():
    return SpyllsChecker(diccionario=DiccionarioFalso())


def test_is_known(checker):
    assert checker.is_known("comí") is True
    assert checker.is_known("casa") is True
    assert checker.is_known("kasa") is False


def test_unknown_filtra(checker):
    assert checker.unknown(["casa", "kasa", "oferta"]) == {"kasa"}


def test_correction_devuelve_la_primera_sugerencia(checker):
    assert checker.correction("kasa") == "casa"
    assert checker.correction("comí") is None


def test_tilde_probable_detecta_el_caso_del_ocr(checker):
    # "comi" no está en el diccionario, pero la única diferencia con "comí"
    # son las tildes: es artefacto del OCR, no una falta del editor.
    assert checker.is_known("comi") is False
    assert checker.tilde_probable("comi") == "comí"
    assert checker.tilde_probable("nino") == "niño"
    # "kasa" no es un problema de tildes.
    assert checker.tilde_probable("kasa") is None


@pytest.mark.lento
def test_diccionario_real_de_libreoffice(tmp_path):
    prefijo = descargar_diccionario(tmp_path)
    assert prefijo.with_suffix(".aff").exists() and prefijo.with_suffix(".dic").exists()
    c = SpyllsChecker(prefijo=prefijo)
    assert c.is_known("aprovecha") and c.is_known("sándwich")
    assert not c.is_known("aprobecha")
    assert c.correction("aprobecha") == "aprovecha"
    assert c.tilde_probable("comi") == "comí"
    assert c.tilde_probable("aprobecha") is None
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_spell_spylls.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.spell_spylls`.

- [ ] **Step 3: Implementar `videoqa_win/spell_spylls.py`**

```python
"""Corrector ortográfico español con spylls (Hunspell en Python puro).

spylls no trae diccionarios: se descargan los de LibreOffice una vez y quedan
en la carpeta de datos.
"""
from __future__ import annotations

import logging
from pathlib import Path

from videoqa_win.acentos import solo_difiere_en_tildes
from videoqa_win.paths import dicts_dir

log = logging.getLogger("videoqa")

_BASE = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/es_ES"
URLS_DICCIONARIO = {"aff": f"{_BASE}.aff", "dic": f"{_BASE}.dic"}
MAX_SUGERENCIAS = 5


def descargar_diccionario(destino: Path | None = None) -> Path:
    """Baja es_ES.aff y es_ES.dic si faltan. Devuelve el prefijo sin extensión."""
    import requests

    carpeta = Path(destino) if destino else dicts_dir()
    carpeta.mkdir(parents=True, exist_ok=True)
    prefijo = carpeta / "es_ES"
    for ext, url in URLS_DICCIONARIO.items():
        archivo = prefijo.with_suffix(f".{ext}")
        if archivo.exists() and archivo.stat().st_size > 1000:
            continue
        log.info("descargando diccionario %s", ext)
        respuesta = requests.get(url, timeout=120)
        respuesta.raise_for_status()
        archivo.write_bytes(respuesta.content)
    return prefijo


class SpyllsChecker:
    """Corrector con la interfaz que espera el motor."""

    def __init__(self, prefijo: Path | None = None, diccionario=None):
        if diccionario is not None:
            self._dic = diccionario
            return
        from spylls.hunspell import Dictionary

        ruta = Path(prefijo) if prefijo else descargar_diccionario()
        self._dic = Dictionary.from_files(str(ruta))

    def is_known(self, word: str) -> bool:
        return bool(self._dic.lookup(word))

    def unknown(self, words) -> set[str]:
        return {w for w in words if not self.is_known(w)}

    def _sugerencias(self, word: str) -> list[str]:
        salida = []
        for s in self._dic.suggest(word):
            salida.append(str(s))
            if len(salida) >= MAX_SUGERENCIAS:
                break
        return salida

    def correction(self, word: str) -> str | None:
        if self.is_known(word):
            return None
        sugerencias = self._sugerencias(word)
        return sugerencias[0] if sugerencias else None

    def tilde_probable(self, word: str) -> str | None:
        """Si la única diferencia con una palabra válida son las tildes, la devuelve.

        Sirve para no acusar de falta de ortografía lo que en realidad es el OCR
        local, que no lee los acentos.
        """
        if self.is_known(word):
            return None
        for s in self._sugerencias(word):
            if solo_difiere_en_tildes(word, s):
                return s
        return None
```

- [ ] **Step 4: Correr los tests rápidos**

Run: `uv run pytest tests/unit/test_spell_spylls.py -q`
Expected: 5 passed, 1 skipped.

- [ ] **Step 5: Correr el test con el diccionario real (descarga ~0,9 MB)**

Run: `VIDEOQA_WIN_LENTO=1 uv run pytest tests/unit/test_spell_spylls.py -q`
Expected: 6 passed. Valores ya verificados: `aprovecha`/`sándwich` conocidas, `aprobecha` desconocida con sugerencia `aprovecha`, `comi` → tilde probable `comí`.

- [ ] **Step 6: Commit**

```bash
git add videoqa_win/spell_spylls.py tests/unit/test_spell_spylls.py
git commit -m "feat: corrector español con spylls y diccionario de LibreOffice"
```

---

### Task 7: Backend de OCR (RapidOCR)

**Files:**
- Create: `videoqa_win/ocr_rapid.py`, `tests/unit/test_ocr_rapid.py`

**Interfaces:**
- Consumes: nada de tareas anteriores (la tolerancia a tildes se aplica en la Task 9, en el check).
- Produces:
  - `videoqa_win.ocr_rapid.convertir_caja(box, ancho, alto) -> list[float]` — 4 puntos en píxeles → `[x, y, w, h]` normalizado, origen arriba-izquierda, recortado a 0-1
  - `videoqa_win.ocr_rapid.ocr_frame(path: Path) -> list[dict]` — `{"text", "conf", "bbox"}`
  - `videoqa_win.ocr_rapid.MIN_CONF = 0.4`

- [ ] **Step 1: Escribir el test**

`tests/unit/test_ocr_rapid.py`:
```python
import pytest
from PIL import Image, ImageDraw

from videoqa_win import ocr_rapid


def test_convertir_caja_centrada():
    box = [[100.0, 200.0], [300.0, 200.0], [300.0, 260.0], [100.0, 260.0]]
    assert ocr_rapid.convertir_caja(box, 1000, 1000) == [0.1, 0.2, 0.2, 0.06]


def test_convertir_caja_inclinada_usa_el_rectangulo_que_la_contiene():
    box = [[100.0, 190.0], [300.0, 210.0], [300.0, 270.0], [100.0, 250.0]]
    x, y, w, h = ocr_rapid.convertir_caja(box, 1000, 1000)
    assert (x, y) == (0.1, 0.19)
    assert round(w, 3) == 0.2 and round(h, 3) == 0.08


def test_convertir_caja_recorta_a_cero_uno():
    box = [[-50.0, -20.0], [1100.0, -20.0], [1100.0, 1050.0], [-50.0, 1050.0]]
    assert ocr_rapid.convertir_caja(box, 1000, 1000) == [0.0, 0.0, 1.0, 1.0]


def test_ocr_frame_traduce_la_salida_de_rapidocr(monkeypatch, tmp_path):
    img = tmp_path / "f.jpg"
    Image.new("RGB", (1000, 500), (0, 0, 0)).save(img)

    class MotorFalso:
        def __call__(self, ruta):
            assert ruta == str(img)
            return ([[[[100.0, 200.0], [300.0, 200.0], [300.0, 260.0], [100.0, 260.0]],
                      "No, me lo comi.", 0.9979]], 0.12)

    monkeypatch.setattr(ocr_rapid, "_motor", lambda: MotorFalso())
    out = ocr_rapid.ocr_frame(img)
    assert len(out) == 1
    assert out[0]["text"] == "No, me lo comi."
    assert round(out[0]["conf"], 4) == 0.9979
    assert out[0]["bbox"] == [0.1, 0.4, 0.2, 0.12]


def test_ocr_frame_sin_detecciones(monkeypatch, tmp_path):
    img = tmp_path / "f.jpg"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(img)
    monkeypatch.setattr(ocr_rapid, "_motor", lambda: (lambda ruta: (None, 0.0)))
    assert ocr_rapid.ocr_frame(img) == []


def test_ocr_frame_descarta_confianza_baja(monkeypatch, tmp_path):
    img = tmp_path / "f.jpg"
    Image.new("RGB", (1000, 500), (0, 0, 0)).save(img)
    caja = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    monkeypatch.setattr(ocr_rapid, "_motor",
                        lambda: (lambda ruta: ([[caja, "ruido", 0.1], [caja, "bueno", 0.95]], 0.0)))
    textos = [i["text"] for i in ocr_rapid.ocr_frame(img)]
    assert textos == ["bueno"]


@pytest.mark.lento
def test_ocr_real_lee_un_subtitulo(tmp_path):
    img = tmp_path / "sub.jpg"
    imagen = Image.new("RGB", (1280, 720), (20, 30, 60))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.text((430, 640), "OFERTA DE VERANO", fill=(255, 255, 255))
    imagen.save(img)
    out = ocr_rapid.ocr_frame(img)
    textos = " ".join(i["text"].upper() for i in out)
    assert "OFERTA" in textos
    x, y, w, h = out[0]["bbox"]
    assert 0.0 <= x <= 1.0 and 0.8 <= y + h <= 1.05
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_ocr_rapid.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.ocr_rapid`.

- [ ] **Step 3: Implementar `videoqa_win/ocr_rapid.py`**

```python
"""OCR con RapidOCR (onnxruntime), sin PaddlePaddle ni PyTorch.

RapidOCR devuelve, por cada detección, cuatro puntos en píxeles, el texto y la
confianza. El motor espera la caja normalizada 0-1 con origen arriba-izquierda,
así que aquí se convierte al rectángulo que contiene los cuatro puntos.

Aviso conocido: el modelo de reconocimiento incluido no trae los caracteres
acentuados del español ("comí" se lee "comi"). Eso NO se corrige aquí: se trata
en el check de ortografía (ver videoqa_win/checks_win.py).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image

log = logging.getLogger("videoqa")

# La confianza de RapidOCR no es comparable con la de Apple Vision: en la
# prueba real un subtítulo nítido dio 0.998 y el ruido de fondo, 0.1-0.3.
MIN_CONF = 0.4


@lru_cache(maxsize=1)
def _motor():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def convertir_caja(box, ancho: int, alto: int) -> list[float]:
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    x0 = max(0.0, min(xs) / ancho)
    y0 = max(0.0, min(ys) / alto)
    x1 = min(1.0, max(xs) / ancho)
    y1 = min(1.0, max(ys) / alto)
    return [round(x0, 4), round(y0, 4), round(max(0.0, x1 - x0), 4), round(max(0.0, y1 - y0), 4)]


def ocr_frame(path: Path) -> list[dict]:
    path = Path(path)
    with Image.open(path) as img:
        ancho, alto = img.size
    try:
        resultado, _ = _motor()(str(path))
    except Exception as e:  # noqa: BLE001 — el OCR no debe tumbar la revisión
        log.warning("OCR falló en %s: %s", path.name, type(e).__name__)
        return []
    salida = []
    for deteccion in resultado or []:
        box, texto, conf = deteccion[0], str(deteccion[1]).strip(), float(deteccion[2])
        if not texto or conf < MIN_CONF:
            continue
        salida.append({"text": texto, "conf": conf, "bbox": convertir_caja(box, ancho, alto)})
    return salida
```

- [ ] **Step 4: Correr los tests rápidos**

Run: `uv run pytest tests/unit/test_ocr_rapid.py -q`
Expected: 6 passed, 1 skipped.

- [ ] **Step 5: Correr el test real (descarga ~16 MB de modelos la primera vez)**

Run: `VIDEOQA_WIN_LENTO=1 uv run pytest tests/unit/test_ocr_rapid.py -q`
Expected: 7 passed. Si el texto dibujado con la fuente por defecto de PIL sale demasiado pequeño para el OCR, agranda la imagen o usa `ImageFont.truetype` con `/System/Library/Fonts/Supplemental/Arial.ttf` a tamaño 48 y explícalo en el informe.

- [ ] **Step 6: Commit**

```bash
git add videoqa_win/ocr_rapid.py tests/unit/test_ocr_rapid.py
git commit -m "feat: backend de OCR con RapidOCR"
```

---

### Task 8: Backend de transcripción (faster-whisper)

**Files:**
- Create: `videoqa_win/asr_faster.py`, `tests/unit/test_asr_faster.py`

**Interfaces:**
- Consumes: `videoqa.stages.transcribe.extract_audio` (del motor), `videoqa_win.paths.modelos_dir()`.
- Produces:
  - `videoqa_win.asr_faster.elegir_dispositivo() -> tuple[str, str, str]` — `(device, compute_type, nombre_modelo)`; `("cuda", "float16", "medium")` si hay GPU NVIDIA, `("cpu", "int8", "small")` si no
  - `videoqa_win.asr_faster.normalizar(segmentos, info) -> dict` — puro
  - `videoqa_win.asr_faster.transcribe(job, has_audio, model) -> dict`

- [ ] **Step 1: Escribir el test**

`tests/unit/test_asr_faster.py`:
```python
from types import SimpleNamespace

import pytest

from videoqa_win import asr_faster


def seg(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


def test_normalizar_limpia_y_arma_el_texto():
    info = SimpleNamespace(language="es", duration=10.0)
    segmentos = [seg(0.0, 2.004, "  ¡Oye! ¿Tienes mi sándwich? "), seg(2.0, 4.0, "   "),
                 seg(4.0, 6.0, "¡Era mi almuerzo!")]
    out = asr_faster.normalizar(segmentos, info)
    assert out["language"] == "es"
    assert out["segments"] == [{"start": 0.0, "end": 2.0, "text": "¡Oye! ¿Tienes mi sándwich?"},
                               {"start": 4.0, "end": 6.0, "text": "¡Era mi almuerzo!"}]
    assert out["text"] == "¡Oye! ¿Tienes mi sándwich? ¡Era mi almuerzo!"


def test_normalizar_sin_segmentos():
    info = SimpleNamespace(language="es", duration=0.0)
    assert asr_faster.normalizar([], info) == {"language": "es", "text": "", "segments": []}


def test_elegir_dispositivo_con_gpu(monkeypatch):
    monkeypatch.setattr(asr_faster, "_hay_gpu_nvidia", lambda: True)
    assert asr_faster.elegir_dispositivo() == ("cuda", "float16", "medium")


def test_elegir_dispositivo_sin_gpu(monkeypatch):
    monkeypatch.setattr(asr_faster, "_hay_gpu_nvidia", lambda: False)
    assert asr_faster.elegir_dispositivo() == ("cpu", "int8", "small")


def test_transcribe_usa_el_modelo_y_normaliza(monkeypatch, tmp_path):
    from videoqa.job import Job

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.path("audio.wav").write_bytes(b"RIFF")

    monkeypatch.setattr(asr_faster, "extract_audio", lambda video, wav: None)
    monkeypatch.setattr(asr_faster, "_hay_gpu_nvidia", lambda: False)

    class ModeloFalso:
        def __init__(self, nombre, device, compute_type, download_root):
            assert (nombre, device, compute_type) == ("small", "cpu", "int8")

        def transcribe(self, ruta, language, vad_filter=True):
            assert language == "es"
            return iter([seg(0.0, 1.0, "hola")]), SimpleNamespace(language="es", duration=1.0)

    monkeypatch.setattr(asr_faster, "_cargar_modelo", lambda n, d, c: ModeloFalso(n, d, c, None))
    out = asr_faster.transcribe(job, True, "auto")
    assert out["text"] == "hola" and out["segments"][0]["end"] == 1.0


def test_transcribe_si_falla_devuelve_vacio_y_no_lanza(monkeypatch, tmp_path):
    from videoqa.job import Job

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    monkeypatch.setattr(asr_faster, "extract_audio", lambda video, wav: None)
    monkeypatch.setattr(asr_faster, "_hay_gpu_nvidia", lambda: False)

    def explota(*a, **k):
        raise RuntimeError("modelo corrupto")

    monkeypatch.setattr(asr_faster, "_cargar_modelo", explota)
    out = asr_faster.transcribe(job, True, "auto")
    assert out == {"language": "es", "text": "", "segments": []}


@pytest.mark.lento
def test_transcripcion_real_de_un_fixture(tmp_path):
    """Usa el audio del fixture 'clean' del motor si está disponible."""
    import subprocess
    from pathlib import Path

    from videoqa.job import Job

    fixture = Path.home() / "videoqa" / "tests" / "fixtures" / "out" / "clean.mp4"
    if not fixture.exists():
        pytest.skip("fixture del motor no generado")
    job = Job(fixture, tmp_path / "jobs")
    out = asr_faster.transcribe(job, True, "auto")
    assert out["language"] == "es"
    assert "oferta" in out["text"].lower() or "verano" in out["text"].lower()
    assert all(s["end"] >= s["start"] for s in out["segments"])
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_asr_faster.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.asr_faster`.

- [ ] **Step 3: Implementar `videoqa_win/asr_faster.py`**

```python
"""Transcripción con faster-whisper (CTranslate2): CPU o GPU NVIDIA, sin PyTorch.

Verificado en la prueba: el modelo `small` en CPU transcribe un video de 10 s en
segundos y devuelve las tildes y la puntuación correctas.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from functools import lru_cache

from videoqa.job import Job
from videoqa.stages.transcribe import extract_audio

from videoqa_win.paths import modelos_dir

log = logging.getLogger("videoqa")

VACIO = {"language": "es", "text": "", "segments": []}


def _hay_gpu_nvidia() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def elegir_dispositivo() -> tuple[str, str, str]:
    """(device, compute_type, modelo). Con GPU NVIDIA sube a `medium`."""
    if _hay_gpu_nvidia():
        return "cuda", "float16", "medium"
    return "cpu", "int8", "small"


@lru_cache(maxsize=2)
def _cargar_modelo(nombre: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    carpeta = modelos_dir()
    carpeta.mkdir(parents=True, exist_ok=True)
    return WhisperModel(nombre, device=device, compute_type=compute_type, download_root=str(carpeta))


def normalizar(segmentos, info) -> dict:
    limpios = []
    for s in segmentos:
        texto = str(s.text).strip()
        if texto:
            limpios.append({"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": texto})
    return {"language": getattr(info, "language", "es") or "es",
            "text": " ".join(s["text"] for s in limpios),
            "segments": limpios}


def transcribe(job: Job, has_audio: bool, model: str) -> dict:
    """`model` se ignora salvo que sea un nombre de faster-whisper distinto de 'auto'."""
    if not has_audio:
        return dict(VACIO, segments=[])
    wav = job.path("audio.wav")
    try:
        extract_audio(job.video, wav)
        device, compute_type, nombre = elegir_dispositivo()
        if model and model != "auto" and "/" not in model:
            nombre = model
        log.info("[%s] transcribiendo con %s en %s", job.name, nombre, device)
        modelo = _cargar_modelo(nombre, device, compute_type)
        segmentos, info = modelo.transcribe(str(wav), language="es", vad_filter=True)
        return normalizar(segmentos, info)
    except Exception as e:  # noqa: BLE001 — sin transcripción se sigue con los checks visuales
        log.warning("[%s] no se pudo transcribir (%s): %s", job.name, type(e).__name__, e)
        return dict(VACIO, segments=[])
```

- [ ] **Step 4: Correr los tests rápidos**

Run: `uv run pytest tests/unit/test_asr_faster.py -q`
Expected: 6 passed, 1 skipped.

- [ ] **Step 5: Correr el test real (descarga ~250 MB la primera vez)**

Run: `VIDEOQA_WIN_LENTO=1 uv run pytest tests/unit/test_asr_faster.py -q`
Expected: 7 passed. Si el fixture del motor no existe, el test se salta solo: genera los fixtures en el repo del motor (`uv run python tests/fixtures/make_fixtures.py`) y vuelve a correrlo.

- [ ] **Step 6: Commit**

```bash
git add videoqa_win/asr_faster.py tests/unit/test_asr_faster.py
git commit -m "feat: backend de transcripción con faster-whisper"
```

---

### Task 9: Tolerancia a tildes en el check de ortografía

**Files:**
- Create: `videoqa_win/checks_win.py`, `tests/unit/test_checks_win.py`

**Interfaces:**
- Consumes: `videoqa.checks.spelling.check_spelling` y `unknown_words` (del motor), `videoqa_win.spell_spylls.SpyllsChecker`, `videoqa.config.load_rules`.
- Produces: `videoqa_win.checks_win.check_spelling_win(appearances, glossary, rules, checker=None) -> list[Finding]` — igual que el del motor, pero los hallazgos cuya única diferencia es la tilde salen como **advertencia** con el `check` `"spelling_tilde_ocr"` y un texto que lo explica.
- Además: `reglas.yaml` del motor no se toca; la severidad nueva se lee con `rules["severities"].get("spelling_tilde_ocr", "warning")`.

- [ ] **Step 1: Escribir el test**

`tests/unit/test_checks_win.py`:
```python
from videoqa.config import load_rules

from videoqa_win.checks_win import check_spelling_win


class CorrectorFalso:
    VOCAB = {"comí", "aprovecha", "oferta", "verano"}

    def is_known(self, w):
        return w.lower() in self.VOCAB

    def unknown(self, words):
        return {w for w in words if not self.is_known(w)}

    def correction(self, w):
        return "aprovecha" if w.lower().startswith("aprob") else "comí"

    def tilde_probable(self, w):
        from videoqa_win.acentos import solo_difiere_en_tildes

        for v in self.VOCAB:
            if solo_difiere_en_tildes(w, v):
                return v
        return None


def app(text, t=1.0, conf=1.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.5, 0.1], "t_start": t, "t_end": t + 2,
            "frame": "frames/a.jpg", "frames": [], "conf": conf}


def test_falta_real_sigue_siendo_bloqueante():
    fs = check_spelling_win([app("Aprobecha la oferta")], set(), load_rules(), checker=CorrectorFalso())
    assert len(fs) == 1
    assert fs[0].severity == "blocker" and fs[0].check == "spelling_unknown_word"
    assert "Aprobecha" in fs[0].title


def test_tilde_perdida_por_el_ocr_es_advertencia_explicada():
    fs = check_spelling_win([app("No, me lo comi.")], set(), load_rules(), checker=CorrectorFalso())
    assert len(fs) == 1
    f = fs[0]
    assert f.severity == "warning" and f.check == "spelling_tilde_ocr"
    assert "comi" in f.title and "comí" in f.suggestion
    assert "no distingue" in f.detail  # explica que puede ser el OCR
    assert f.t_start == 1.0 and f.frame == "frames/a.jpg"


def test_texto_correcto_no_produce_nada():
    assert check_spelling_win([app("oferta de verano")], set(), load_rules(), checker=CorrectorFalso()) == []


def test_el_glosario_manda():
    fs = check_spelling_win([app("Kasa de verano")], {"kasa"}, load_rules(), checker=CorrectorFalso())
    assert fs == []


def test_confianza_baja_se_ignora():
    fs = check_spelling_win([app("Aprobecha", conf=0.2)], set(), load_rules(), checker=CorrectorFalso())
    assert fs == []


def test_ids_no_se_repiten():
    fs = check_spelling_win([app("Aprobecha", t=1.0), app("comi", t=5.0)], set(), load_rules(),
                            checker=CorrectorFalso())
    assert len({f.id for f in fs}) == len(fs) == 2
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_checks_win.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.checks_win`.

- [ ] **Step 3: Implementar `videoqa_win/checks_win.py`**

```python
"""Check de ortografía adaptado al OCR local.

El modelo de RapidOCR no lee las tildes, así que una palabra que solo difiere de
una válida en los acentos no se puede juzgar: sale como advertencia explicada,
no como bloqueante. Las faltas de verdad ("Aprobecha") siguen bloqueando.
"""
from __future__ import annotations

from videoqa.checks.spelling import WORD_RE
from videoqa.findings import Finding

TILDE_CHECK = "spelling_tilde_ocr"


def _palabras(texto: str) -> list[str]:
    return [w for w in WORD_RE.findall(texto) if len(w) >= 3]


def check_spelling_win(appearances: list[dict], glossary: set[str], rules: dict,
                       checker=None) -> list[Finding]:
    if checker is None:
        from videoqa_win.spell_spylls import SpyllsChecker

        checker = SpyllsChecker()

    sev = rules["severities"]
    sev_falta = sev["spelling_unknown_word"]
    sev_tilde = sev.get(TILDE_CHECK, "warning")
    min_conf = float(rules["thresholds"].get("ocr_min_conf", 0.5))

    salida: list[Finding] = []
    for i, a in enumerate(appearances):
        if float(a.get("conf", 1.0)) < min_conf:
            continue
        texto = a["text"]
        faltas, tildes = [], []
        for w in _palabras(texto):
            if w.lower() in glossary or checker.is_known(w):
                continue
            correcta = checker.tilde_probable(w)
            if correcta:
                tildes.append((w, correcta))
            else:
                faltas.append(w)

        if faltas:
            arreglos = ", ".join(f"{w} → {checker.correction(w) or '?'}" for w in faltas)
            salida.append(Finding(
                id=f"spell-{i}", type="ortografia", severity=sev_falta,
                t_start=a["t_start"], t_end=a["t_end"],
                title=f"Posible error ortográfico: {', '.join(faltas)}",
                detail=f'Texto en pantalla: "{texto}".', suggestion=arreglos,
                frame=a.get("frame"), bbox=a.get("bbox"), source="code",
                check="spelling_unknown_word"))

        if tildes:
            palabras = ", ".join(w for w, _ in tildes)
            arreglos = ", ".join(f"{w} → {c}" for w, c in tildes)
            salida.append(Finding(
                id=f"tilde-{i}", type="ortografia", severity=sev_tilde,
                t_start=a["t_start"], t_end=a["t_end"],
                title=f"Revisa las tildes: {palabras}",
                detail=(f'Texto en pantalla: "{texto}". El lector de texto de esta versión '
                        "no distingue las tildes, así que puede que en el video estén bien puestas. "
                        "Compruébalo a ojo en el video."),
                suggestion=arreglos, frame=a.get("frame"), bbox=a.get("bbox"),
                source="code", check=TILDE_CHECK))
    return salida
```

- [ ] **Step 4: Correr los tests**

Run: `uv run pytest tests/unit/test_checks_win.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add videoqa_win/checks_win.py tests/unit/test_checks_win.py
git commit -m "feat: ortografía tolerante a las tildes que el OCR local no lee"
```

---

### Task 10: Activación, configuración y pipeline propio

**Files:**
- Create: `videoqa_win/setup_win.py`, `videoqa_win/pipeline_win.py`, `tests/unit/test_setup_win.py`, `tests/integration/__init__.py`, `tests/integration/test_pipeline_win.py`
- Modify: `videoqa_win/__init__.py`

**Interfaces:**
- Consumes: los tres backends (Tasks 6-8), `videoqa_win.checks_win.check_spelling_win`, `videoqa.backends.register_*`, `videoqa.config.Settings/load_rules`, `videoqa.pipeline.process_video`, `videoqa_win.paths`.
- Produces:
  - `videoqa_win.setup_win.activar() -> None` — registra los tres backends (idempotente)
  - `videoqa_win.setup_win.cargar_config() -> tuple[Settings, dict]` — `Settings` apuntando a `trabajo_dir()` y las reglas con `salida.reporte_html: true`, `severities.spelling_tilde_ocr`, `thresholds.ocr_min_conf` ajustado a RapidOCR (0.4) y el juez de `config.yaml`
  - `videoqa_win.pipeline_win.revisar(video: Path) -> Result` — activa, carga config, parchea el check de ortografía y llama a `process_video`
  - `videoqa_win.pipeline_win.runner_actual(cfg: dict)` — devuelve el `Runner` según `juez` (`ninguno` → runner que lanza `ClaudeError`)

- [ ] **Step 1: Escribir los tests**

`tests/unit/test_setup_win.py`:
```python
from videoqa import backends

from videoqa_win import setup_win


def test_activar_registra_los_tres():
    backends.reset()
    setup_win.activar()
    from videoqa_win.asr_faster import transcribe
    from videoqa_win.ocr_rapid import ocr_frame
    from videoqa_win.spell_spylls import SpyllsChecker

    assert backends.get_ocr() is ocr_frame
    assert backends.get_transcriber() is transcribe
    assert backends.get_speller() is SpyllsChecker
    backends.reset()


def test_activar_es_idempotente():
    backends.reset()
    setup_win.activar()
    primero = backends.get_ocr()
    setup_win.activar()
    assert backends.get_ocr() is primero
    backends.reset()


def test_config_apunta_a_la_carpeta_de_trabajo(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    settings, rules = setup_win.cargar_config()
    assert settings.drive_root == tmp_path / "T"
    assert settings.entrada == tmp_path / "T" / "01_Entrada"
    assert rules["salida"]["reporte_html"] is True
    assert rules["thresholds"]["ocr_min_conf"] == 0.4
    assert rules["severities"]["spelling_tilde_ocr"] == "warning"


def test_config_lee_el_juez_del_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    (tmp_path / "d").mkdir(parents=True)
    (tmp_path / "d" / "config.yaml").write_text("juez: ollama\n", encoding="utf-8")
    _, rules = setup_win.cargar_config()
    assert rules["juez"] == "ollama"


def test_config_sin_yaml_usa_juez_ninguno(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    _, rules = setup_win.cargar_config()
    assert rules["juez"] == "ninguno"
```

`tests/integration/test_pipeline_win.py`:
```python
import shutil
from pathlib import Path

import pytest

from videoqa_win import pipeline_win

FIXTURES = Path.home() / "videoqa" / "tests" / "fixtures"


def _entorno(tmp_path, monkeypatch, nombre):
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    from videoqa_win.paths import crear_carpetas_trabajo

    raiz = crear_carpetas_trabajo()
    shutil.copy(FIXTURES / "brand.json", raiz / "_config" / "brand.json")
    shutil.copy(FIXTURES / "glosario.txt", raiz / "_config" / "glosario.txt")
    origen = FIXTURES / "out" / f"{nombre}.mp4"
    if not origen.exists():
        pytest.skip("fixtures del motor no generados")
    destino = raiz / "01_Entrada" / f"{nombre}.mp4"
    shutil.copy(origen, destino)
    return raiz, destino


@pytest.mark.lento
def test_el_fixture_con_errores_sale_rechazado(tmp_path, monkeypatch):
    raiz, video = _entorno(tmp_path, monkeypatch, "spelling_color")
    res = pipeline_win.revisar(video)
    assert res.status == "rejected"
    checks = {f.check for f in res.findings}
    assert "brand_color" in checks
    assert res.dest == raiz / "02_Con_errores" / "spelling_color"
    assert (res.dest / "reporte.html").exists()
    assert (res.dest / "reporte.md").exists()
    assert "judge_unavailable" in checks  # sin juez configurado


@pytest.mark.lento
def test_el_fixture_limpio_no_tiene_bloqueantes_de_color(tmp_path, monkeypatch):
    raiz, video = _entorno(tmp_path, monkeypatch, "clean")
    res = pipeline_win.revisar(video)
    bloqueantes = {f.check for f in res.findings if f.severity == "blocker"}
    assert "brand_color" not in bloqueantes
    assert "spelling_unknown_word" not in bloqueantes


@pytest.mark.lento
def test_video_sin_audio_no_rompe(tmp_path, monkeypatch):
    raiz, video = _entorno(tmp_path, monkeypatch, "no_audio")
    res = pipeline_win.revisar(video)
    assert res.status in ("rejected", "error")
    assert "no_audio" in {f.check for f in res.findings}
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_setup_win.py -q`
Expected: FAIL — `ModuleNotFoundError: videoqa_win.setup_win`.

- [ ] **Step 3: Implementar `videoqa_win/setup_win.py`**

```python
"""Activación de los backends portables y configuración propia de Windows."""
from __future__ import annotations

import copy
import logging
from pathlib import Path

import yaml
from videoqa import backends
from videoqa.config import Settings, load_rules

from videoqa_win.paths import datos_dir, trabajo_dir

log = logging.getLogger("videoqa")

# Ajustes propios de esta pila. No se tocan las reglas del motor: se aplican
# encima al cargar la configuración.
AJUSTES = {
    "salida": {"reporte_html": True},
    # La confianza de RapidOCR no es la de Apple Vision (ver videoqa_win/ocr_rapid.py).
    "thresholds": {"ocr_min_conf": 0.4},
    "severities": {"spelling_tilde_ocr": "warning"},
}


def activar() -> None:
    """Registra OCR, transcripción y corrector portables en el motor."""
    from videoqa_win.asr_faster import transcribe
    from videoqa_win.ocr_rapid import ocr_frame
    from videoqa_win.spell_spylls import SpyllsChecker

    backends.register_ocr(ocr_frame)
    backends.register_transcriber(transcribe)
    backends.register_speller(SpyllsChecker)


def _config_yaml() -> dict:
    ruta = datos_dir() / "config.yaml"
    if not ruta.exists():
        return {}
    try:
        return yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        log.warning("config.yaml ilegible (%s): se usan los valores por defecto", type(e).__name__)
        return {}


def cargar_config() -> tuple[Settings, dict]:
    reglas = copy.deepcopy(load_rules())
    for seccion, valores in AJUSTES.items():
        reglas.setdefault(seccion, {}).update(valores)

    propia = _config_yaml()
    reglas["juez"] = str(propia.get("juez", "ninguno"))
    if propia.get("whisper_model"):
        reglas.setdefault("asr", {})["model"] = str(propia["whisper_model"])

    settings = Settings(drive_root=trabajo_dir(), jobs_dir=datos_dir() / "jobs")
    return settings, reglas
```

- [ ] **Step 4: Implementar `videoqa_win/pipeline_win.py`**

```python
"""Punto de entrada de la revisión en Windows.

Reutiliza `videoqa.pipeline.process_video` tal cual; lo único propio es
sustituir el check de ortografía por el tolerante a tildes y elegir el juez.
"""
from __future__ import annotations

import logging
from pathlib import Path

from videoqa.claude_runner import ClaudeError
from videoqa.pipeline import Result

from videoqa_win.checks_win import check_spelling_win
from videoqa_win.setup_win import activar, cargar_config

log = logging.getLogger("videoqa")


def _sin_juez(prompt: str, cwd: Path) -> str:
    raise ClaudeError("no hay juez configurado en esta instalación")


def runner_actual(cfg: dict):
    juez = cfg.get("juez", "ninguno")
    if juez == "ollama":
        from videoqa_win.judge_ollama import runner_ollama

        return runner_ollama
    if juez != "ninguno":
        log.warning("juez '%s' desconocido: se sigue sin juez", juez)
    return _sin_juez


def revisar(video: Path) -> Result:
    """Revisa un video y devuelve el Result del motor."""
    activar()
    settings, reglas = cargar_config()

    # El motor llama a videoqa.checks.spelling.check_spelling desde el pipeline;
    # aquí se sustituye por la versión tolerante a tildes.
    import videoqa.pipeline as pl

    pl.check_spelling = check_spelling_win
    from videoqa.sheet import SheetWriter

    sheet = SheetWriter(None, settings.jobs_dir / "sheet_pending.json")
    return pl.process_video(Path(video), settings, reglas, runner_actual(reglas), sheet=sheet)


def revisar_pendientes() -> list[Result]:
    """Revisa todo lo que haya en 01_Entrada, uno por uno."""
    from videoqa.watcher import list_videos

    activar()
    settings, _ = cargar_config()
    resultados = []
    for video in list_videos(settings.entrada):
        resultados.append(revisar(video))
    return resultados
```

Comprueba que `videoqa/pipeline.py` importe `check_spelling` a nivel de módulo (`from videoqa.checks.spelling import check_spelling`): si lo importa dentro de la función, el parcheo no surte efecto — en ese caso mueve el import al nivel de módulo en el motor (cambio de una línea, con su commit aparte en el repo del motor) y anótalo en el informe.

- [ ] **Step 5: `videoqa_win/__init__.py`**

```python
"""VideoQA para Windows: pre-chequeo local de videos antes de subirlos."""
from videoqa_win.setup_win import activar

__all__ = ["activar"]
__version__ = "0.1.0"
```

- [ ] **Step 6: Correr los tests rápidos**

Run: `uv run pytest tests/unit -q`
Expected: todo verde (paths 4, acentos 2, spylls 5+1 skip, ocr 6+1 skip, asr 6+1 skip, checks_win 6, setup_win 5).

- [ ] **Step 7: Correr la integración con los fixtures reales**

Primero genera los fixtures en el repo del motor si no existen:
```bash
(cd ~/videoqa && uv run python tests/fixtures/make_fixtures.py)
```
Run: `VIDEOQA_WIN_LENTO=1 uv run pytest tests/integration -q -x`
Expected: 3 passed. Notas de depuración probables:
- Si `spelling_color` no marca `brand_color`: imprime el `ocr_color.json` del job (`~/.videoqa-win/jobs/spelling_color/`) y comprueba que `color_hex` sea cercano a `#FF3B30`; el fixture usa rojo puro, así que el ΔE contra la paleta debe ser alto.
- Si el OCR no lee "Aprobecha" en el fixture: los fixtures usan `fontsize=72` sobre 1080×1920; RapidOCR debería leerlo. Si no, baja `MIN_CONF` a 0.3 y documéntalo.
- Si aparece `text_occluded` en los fixtures: son verticales, así que la zona segura sí aplica; es correcto.

- [ ] **Step 8: Commit**

```bash
git add videoqa_win/setup_win.py videoqa_win/pipeline_win.py videoqa_win/__init__.py tests/unit/test_setup_win.py tests/integration
git commit -m "feat: activación de backends, configuración y pipeline de Windows"
```

---

### Task 11: CLI y juez opcional por Ollama

**Files:**
- Create: `videoqa_win/cli.py`, `videoqa_win/judge_ollama.py`, `tests/unit/test_cli_win.py`, `tests/unit/test_judge_ollama.py`

**Interfaces:**
- Consumes: `videoqa_win.pipeline_win.revisar/revisar_pendientes`, `videoqa_win.paths`, `videoqa.watcher.watch`.
- Produces:
  - CLI `videoqa-win` con `instalar-datos`, `revisar [archivos...]`, `watch [--once]`, `diagnostico`; `main(argv=None) -> int`
  - `videoqa_win.judge_ollama.runner_ollama(prompt: str, cwd: Path) -> str`
  - `videoqa_win.judge_ollama.MODELO = "qwen2.5vl:3b"`, `MAX_FRAMES = 6`

- [ ] **Step 1: Escribir los tests**

`tests/unit/test_judge_ollama.py`:
```python
import json

import pytest

from videoqa.claude_runner import ClaudeError

from videoqa_win import judge_ollama


def test_recoge_las_imagenes_del_prompt(tmp_path):
    (tmp_path / "claude_frames").mkdir()
    for i in range(8):
        (tmp_path / "claude_frames" / f"{i:02d}_0000.{i}s.jpg").write_bytes(b"jpg")
    prompt = "\n".join(f"- claude_frames/{i:02d}_0000.{i}s.jpg  (t = 0.{i} s)" for i in range(8))
    imagenes = judge_ollama.imagenes_del_prompt(prompt, tmp_path)
    assert len(imagenes) == judge_ollama.MAX_FRAMES
    assert all(p.exists() for p in imagenes)


def test_ignora_rutas_que_no_existen(tmp_path):
    prompt = "- claude_frames/99_0099.0s.jpg"
    assert judge_ollama.imagenes_del_prompt(prompt, tmp_path) == []


def test_runner_devuelve_el_texto(monkeypatch, tmp_path):
    def fake_post(url, json=None, timeout=None):
        assert "api/generate" in url
        assert json["model"] == judge_ollama.MODELO

        class R:
            status_code = 200

            @staticmethod
            def raise_for_status():
                pass

            @staticmethod
            def json():
                return {"response": '{"findings": []}'}

        return R

    monkeypatch.setattr(judge_ollama.requests, "post", fake_post)
    assert judge_ollama.runner_ollama("prompt", tmp_path) == '{"findings": []}'


def test_si_ollama_no_responde_lanza_claude_error(monkeypatch, tmp_path):
    def fake_post(url, json=None, timeout=None):
        raise OSError("conexión rechazada")

    monkeypatch.setattr(judge_ollama.requests, "post", fake_post)
    with pytest.raises(ClaudeError):
        judge_ollama.runner_ollama("prompt", tmp_path)
```

`tests/unit/test_cli_win.py`:
```python
from pathlib import Path

from videoqa.pipeline import Result

from videoqa_win import cli


def test_revisar_un_archivo(monkeypatch, tmp_path, capsys):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    dest = tmp_path / "02_Con_errores" / "v"
    dest.mkdir(parents=True)
    (dest / "reporte.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(cli, "revisar", lambda p: Result("rejected", [], dest))
    abiertos = []
    monkeypatch.setattr(cli, "abrir", abiertos.append)

    assert cli.main(["revisar", str(video)]) == 0
    salida = capsys.readouterr().out
    assert "NO APROBADO" in salida or "errores" in salida.lower()
    assert abiertos == [dest / "reporte.html"]


def test_revisar_sin_argumentos_usa_los_pendientes(monkeypatch, capsys):
    monkeypatch.setattr(cli, "revisar_pendientes", lambda: [])
    assert cli.main(["revisar"]) == 0
    assert "no hay videos" in capsys.readouterr().out.lower()


def test_revisar_devuelve_1_si_hay_error(monkeypatch, tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(cli, "revisar", lambda p: Result("error", [], None, "algo falló"))
    assert cli.main(["revisar", str(video)]) == 1


def test_instalar_datos_crea_carpetas(monkeypatch, tmp_path):
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    monkeypatch.setattr(cli, "descargar_diccionario", lambda: tmp_path / "d" / "es_ES")
    assert cli.main(["instalar-datos"]) == 0
    for nombre in ("01_Entrada", "02_Con_errores", "03_Aprobado", "_config"):
        assert (tmp_path / "T" / nombre).is_dir()


def test_diagnostico_escribe_informe(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VIDEOQA_WIN_TRABAJO", str(tmp_path / "T"))
    monkeypatch.setenv("VIDEOQA_WIN_HOME", str(tmp_path / "d"))
    destino = tmp_path / "diagnostico.txt"
    assert cli.main(["diagnostico", "--salida", str(destino)]) == 0
    texto = destino.read_text(encoding="utf-8")
    assert "Python" in texto and "ffmpeg" in texto and "carpeta de trabajo" in texto.lower()
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_cli_win.py tests/unit/test_judge_ollama.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implementar `videoqa_win/judge_ollama.py`**

```python
"""Juez local opcional con Ollama.

Experimental: un modelo de 3B ve mucho menos que Claude. Sirve para lo evidente
(marca de agua, texto cortado) y se le escapa el matiz. Apagado por defecto.
"""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

import requests
from videoqa.claude_runner import ClaudeError

log = logging.getLogger("videoqa")

MODELO = "qwen2.5vl:3b"
URL = "http://127.0.0.1:11434/api/generate"
MAX_FRAMES = 6          # un 3B se pierde con quince imágenes
TIMEOUT = 600

_RUTA_FRAME = re.compile(r"(claude_frames/[\w.\-]+\.jpg)")


def imagenes_del_prompt(prompt: str, cwd: Path) -> list[Path]:
    vistas, salida = set(), []
    for rel in _RUTA_FRAME.findall(prompt):
        if rel in vistas:
            continue
        vistas.add(rel)
        ruta = Path(cwd) / rel
        if ruta.exists():
            salida.append(ruta)
        if len(salida) >= MAX_FRAMES:
            break
    return salida


def runner_ollama(prompt: str, cwd: Path) -> str:
    """Runner compatible con el motor: (prompt, cwd) -> texto de la respuesta."""
    imagenes = [base64.b64encode(p.read_bytes()).decode("ascii") for p in imagenes_del_prompt(prompt, cwd)]
    cuerpo = {"model": MODELO, "prompt": prompt, "images": imagenes, "stream": False,
              "options": {"temperature": 0}}
    try:
        respuesta = requests.post(URL, json=cuerpo, timeout=TIMEOUT)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except Exception as e:  # noqa: BLE001 — cualquier fallo se traduce al error del motor
        raise ClaudeError(f"Ollama no respondió ({type(e).__name__}): {e}") from e
    texto = str(datos.get("response", "")).strip()
    if not texto:
        raise ClaudeError("Ollama devolvió una respuesta vacía")
    return texto
```

- [ ] **Step 4: Implementar `videoqa_win/cli.py`**

```python
"""Interfaz de línea de comandos. La usan los .bat; el editor no la ve."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from videoqa_win.paths import (crear_carpetas_trabajo, datos_dir, log_path, modelos_dir,
                               trabajo_dir)
from videoqa_win.pipeline_win import revisar, revisar_pendientes
from videoqa_win.spell_spylls import descargar_diccionario

ESTADOS = {"approved": "🟢 APROBADO", "rejected": "🔴 NO APROBADO — hay que corregir",
           "error": "❌ No se pudo revisar del todo"}


def preparar_log() -> None:
    datos_dir().mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    raiz = logging.getLogger("videoqa")
    raiz.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(log_path(), maxBytes=2_000_000, backupCount=2,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    raiz.handlers = [fh]


def abrir(ruta: Path) -> None:
    """Abre un archivo con el programa por defecto del sistema."""
    try:
        if sys.platform.startswith("win"):
            import os

            os.startfile(str(ruta))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(ruta)], check=False)
        else:
            subprocess.run(["xdg-open", str(ruta)], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"    (no pude abrir {ruta.name}: {type(e).__name__})")


def _contar(res) -> tuple[int, int]:
    bloq = sum(1 for f in res.findings if f.severity == "blocker")
    avisos = sum(1 for f in res.findings if f.severity == "warning")
    return bloq, avisos


def _informar(res) -> None:
    print(f"\n  {ESTADOS.get(res.status, res.status)}")
    if res.status == "error" and res.dest is None:
        print(f"    Motivo: {res.error}")
        print("    El video sigue en 01_Entrada; se puede volver a intentar.")
        return
    bloq, avisos = _contar(res)
    print(f"    {bloq} cosas que corregir · {avisos} avisos")
    for f in sorted((f for f in res.findings if f.severity == "blocker"), key=lambda f: f.t_start):
        seg = int(f.t_start)
        print(f"      · [{seg // 60}:{seg % 60:02d}] {f.title}")
    if res.dest:
        print(f"    Detalle completo: {res.dest / 'reporte.html'}")


def cmd_revisar(args) -> int:
    if args.archivos:
        codigos = []
        for ruta in args.archivos:
            res = revisar(Path(ruta))
            _informar(res)
            if res.dest:
                html = res.dest / "reporte.html"
                if html.exists():
                    abrir(html)
            codigos.append(0 if res.status in ("approved", "rejected") else 1)
        return max(codigos)

    resultados = revisar_pendientes()
    if not resultados:
        print("\n  No hay videos esperando en 01_Entrada.")
        return 0
    for res in resultados:
        _informar(res)
    ultimo = resultados[-1]
    if ultimo.dest and (ultimo.dest / "reporte.html").exists():
        abrir(ultimo.dest / "reporte.html")
    return 0 if all(r.status in ("approved", "rejected") for r in resultados) else 1


def cmd_watch(args) -> int:
    from videoqa.watcher import watch

    from videoqa_win.pipeline_win import runner_actual
    from videoqa_win.setup_win import activar, cargar_config

    activar()
    settings, reglas = cargar_config()

    def procesar(video, settings, rules, runner, sheet=None):
        return revisar(video)

    print(f"  Vigilando {settings.entrada}")
    watch(settings, reglas, runner_actual(reglas), once=args.once, process=procesar)
    return 0


def cmd_instalar_datos(args) -> int:
    raiz = crear_carpetas_trabajo()
    modelos_dir().mkdir(parents=True, exist_ok=True)
    print(f"  Carpetas listas en {raiz}")
    try:
        descargar_diccionario()
        print("  Diccionario de español listo.")
    except Exception as e:  # noqa: BLE001
        print(f"  No pude bajar el diccionario ({type(e).__name__}). Revisa tu internet y vuelve a intentarlo.")
        return 1
    return 0


def cmd_diagnostico(args) -> int:
    lineas = ["INFORME DE DIAGNÓSTICO — VideoQA para Windows", ""]
    lineas.append(f"Sistema: {platform.platform()}")
    lineas.append(f"Python: {sys.version.split()[0]} ({sys.executable})")
    lineas.append(f"ffmpeg: {shutil.which('ffmpeg') or 'NO ENCONTRADO'}")
    lineas.append(f"ffprobe: {shutil.which('ffprobe') or 'NO ENCONTRADO'}")
    lineas.append(f"nvidia-smi: {shutil.which('nvidia-smi') or 'no hay GPU NVIDIA visible'}")
    lineas.append("")
    lineas.append(f"Carpeta de trabajo: {trabajo_dir()} (existe: {trabajo_dir().exists()})")
    lineas.append(f"Carpeta de datos: {datos_dir()} (existe: {datos_dir().exists()})")
    lineas.append(f"Modelos: {modelos_dir()} (existe: {modelos_dir().exists()})")
    for nombre, modulo in (("rapidocr", "rapidocr_onnxruntime"), ("faster-whisper", "faster_whisper"),
                           ("spylls", "spylls"), ("motor videoqa", "videoqa")):
        try:
            __import__(modulo)
            lineas.append(f"{nombre}: OK")
        except Exception as e:  # noqa: BLE001
            lineas.append(f"{nombre}: FALLA ({type(e).__name__}: {e})")
    lineas.append("")
    registro = log_path()
    if registro.exists():
        lineas.append("Últimas líneas del registro:")
        lineas += registro.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
    texto = "\n".join(lineas) + "\n"
    destino = Path(args.salida) if args.salida else Path.home() / "Desktop" / "diagnostico.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"  Guardado en {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    preparar_log()
    ap = argparse.ArgumentParser(prog="videoqa-win",
                                 description="Pre-chequeo local de videos antes de subirlos")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("instalar-datos", help="crear carpetas y bajar el diccionario")
    p.set_defaults(fn=cmd_instalar_datos)

    p = sub.add_parser("revisar", help="revisar archivos concretos o lo pendiente en 01_Entrada")
    p.add_argument("archivos", nargs="*")
    p.set_defaults(fn=cmd_revisar)

    p = sub.add_parser("watch", help="vigilar 01_Entrada")
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)

    p = sub.add_parser("diagnostico", help="informe para soporte")
    p.add_argument("--salida")
    p.set_defaults(fn=cmd_diagnostico)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Correr los tests**

Run: `uv run pytest tests/unit -q`
Expected: todo verde, incluidos los 5 del CLI y los 4 del juez.

Run: `uv run videoqa-win --help` y `uv run videoqa-win diagnostico --salida /tmp/diag.txt`
Expected: la ayuda lista los cuatro subcomandos; el diagnóstico imprime y guarda el informe.

- [ ] **Step 6: Commit**

```bash
git add videoqa_win/cli.py videoqa_win/judge_ollama.py tests/unit/test_cli_win.py tests/unit/test_judge_ollama.py
git commit -m "feat: CLI de Windows y juez opcional por Ollama"
```

---

### Task 12: Los `.bat` y el instalador

**Files:**
- Create: `bat/Instalar VideoQA.bat`, `bat/Revisar video.bat`, `bat/Activar automatico.bat`, `bat/Diagnostico.bat`, `bat/Actualizar VideoQA.bat`, `tests/unit/test_bat.py`

**Interfaces:**
- Consumes: el CLI (`videoqa-win …`) y el entorno en `%USERPROFILE%\VideoQA\.venv`.
- Produces: los cinco `.bat` y un test que valida su forma (no se pueden ejecutar en macOS).

Convenciones de todos los `.bat`: empiezan con `@echo off`, `chcp 65001 >nul`, `setlocal`, definen `set "VQ=%USERPROFILE%\VideoQA"` y `set "PY=%VQ%\.venv\Scripts\python.exe"`, citan todas las rutas, y terminan con `pause` salvo el watcher.

- [ ] **Step 1: Escribir el test de forma**

`tests/unit/test_bat.py`:
```python
from pathlib import Path

import pytest

BAT = Path(__file__).resolve().parents[2] / "bat"
NOMBRES = ["Instalar VideoQA.bat", "Revisar video.bat", "Activar automatico.bat",
           "Diagnostico.bat", "Actualizar VideoQA.bat"]


@pytest.mark.parametrize("nombre", NOMBRES)
def test_existe_y_tiene_la_cabecera(nombre):
    ruta = BAT / nombre
    assert ruta.exists(), f"falta {nombre}"
    texto = ruta.read_text(encoding="utf-8")
    assert texto.startswith("@echo off"), nombre
    assert "chcp 65001" in texto, nombre
    assert "setlocal" in texto, nombre


@pytest.mark.parametrize("nombre", NOMBRES)
def test_saltos_de_linea_de_windows(nombre):
    crudo = (BAT / nombre).read_bytes()
    assert b"\r\n" in crudo, f"{nombre} necesita saltos CRLF"
    assert b"\n" not in crudo.replace(b"\r\n", b""), f"{nombre} mezcla saltos"


@pytest.mark.parametrize("nombre", NOMBRES)
def test_las_rutas_van_entre_comillas(nombre):
    texto = (BAT / nombre).read_text(encoding="utf-8")
    for linea in texto.splitlines():
        if "%VQ%\\" in linea or "%PY%" in linea:
            assert '"' in linea, f"{nombre}: ruta sin comillas → {linea}"


def test_el_instalador_usa_winget_y_el_repo_correcto():
    texto = (BAT / "Instalar VideoQA.bat").read_text(encoding="utf-8")
    assert "winget" in texto
    assert "github.com/hongs05/videoqa-win" in texto
    assert "instalar-datos" in texto


def test_revisar_acepta_argumentos_arrastrados():
    texto = (BAT / "Revisar video.bat").read_text(encoding="utf-8")
    assert "%*" in texto or "%1" in texto


def test_activar_automatico_usa_la_carpeta_de_inicio():
    texto = (BAT / "Activar automatico.bat").read_text(encoding="utf-8")
    assert "Startup" in texto or "shell:startup" in texto
    assert "watch" in texto
```

- [ ] **Step 2: Correr para ver el fallo**

Run: `uv run pytest tests/unit/test_bat.py -q`
Expected: FAIL — faltan los cinco archivos.

- [ ] **Step 3: Escribir `bat/Instalar VideoQA.bat`**

```bat
@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Instalar VideoQA

set "VQ=%USERPROFILE%\VideoQA"
set "PY=%VQ%\.venv\Scripts\python.exe"

echo.
echo   VideoQA — instalacion
echo   Esto deja tu PC listo para revisar videos antes de subirlos.
echo   Puede tardar entre 10 y 20 minutos. No cierres la ventana.
echo.

where winget >nul 2>&1
if errorlevel 1 (
  echo   [X] Falta "winget", que es lo que instala programas en Windows.
  echo       Abre la Microsoft Store, busca "Instalador de aplicaciones"
  echo       e instalalo. Despues vuelve a ejecutar este archivo.
  pause
  exit /b 1
)

echo   [1/5] Python 3.12
where python >nul 2>&1
if errorlevel 1 (
  echo         Instalando Python...
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent
) else (
  echo         Ya estaba.
)

echo   [2/5] ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo         Instalando ffmpeg...
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements --silent
) else (
  echo         Ya estaba.
)

echo   [3/5] Preparando la carpeta de trabajo
if not exist "%VQ%" mkdir "%VQ%"
if not exist "%PY%" (
  py -3.12 -m venv "%VQ%\.venv" 2>nul || python -m venv "%VQ%\.venv"
)
if not exist "%PY%" (
  echo   [X] No pude preparar Python. Cierra esta ventana, abrela de nuevo
  echo       y vuelve a ejecutar este archivo (Windows necesita reiniciar
  echo       la ventana despues de instalar Python).
  pause
  exit /b 1
)

echo   [4/5] Instalando VideoQA (descarga unos 300 MB)
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install --upgrade "videoqa-win @ git+https://github.com/hongs05/videoqa-win@main"
if errorlevel 1 (
  echo   [X] La descarga fallo. Revisa tu internet y vuelve a ejecutar
  echo       este archivo: continua donde se quedo.
  pause
  exit /b 1
)

echo   [5/5] Carpetas, diccionario y prueba
"%PY%" -m videoqa_win.cli instalar-datos
if errorlevel 1 (
  echo   [!] No pude bajar el diccionario. Se puede reintentar despues.
)

copy /Y "%~dp0Revisar video.bat" "%USERPROFILE%\Desktop\Revisar video.bat" >nul 2>&1
copy /Y "%~dp0Activar automatico.bat" "%USERPROFILE%\Desktop\Activar automatico.bat" >nul 2>&1
copy /Y "%~dp0Diagnostico.bat" "%USERPROFILE%\Desktop\Diagnostico.bat" >nul 2>&1
copy /Y "%~dp0Actualizar VideoQA.bat" "%USERPROFILE%\Desktop\Actualizar VideoQA.bat" >nul 2>&1

echo.
echo   Listo. En tu Escritorio tienes "Revisar video".
echo.
echo   Como se usa:
echo     - Arrastra un video encima de "Revisar video" y espera.
echo     - O deja los videos en:  %VQ%\01_Entrada
echo       y haz doble clic en "Revisar video".
echo.
echo   La primera revision descarga el modelo de voz (unos 250 MB):
echo   tarda mas solo esa vez.
echo.
start "" "%VQ%"
pause
exit /b 0
```

- [ ] **Step 4: Escribir los otros cuatro `.bat`**

`bat/Revisar video.bat`:
```bat
@echo off
chcp 65001 >nul
setlocal
title Revisar video

set "VQ=%USERPROFILE%\VideoQA"
set "PY=%VQ%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo   [X] VideoQA no esta instalado todavia.
  echo       Ejecuta primero "Instalar VideoQA.bat".
  pause
  exit /b 1
)

if "%~1"=="" (
  echo   Revisando lo que haya en %VQ%\01_Entrada ...
  "%PY%" -m videoqa_win.cli revisar
) else (
  echo   Revisando los archivos que arrastraste...
  "%PY%" -m videoqa_win.cli revisar %*
)

echo.
pause
exit /b 0
```

`bat/Activar automatico.bat`:
```bat
@echo off
chcp 65001 >nul
setlocal
title Revision automatica

set "VQ=%USERPROFILE%\VideoQA"
set "PY=%VQ%\.venv\Scripts\python.exe"
set "INICIO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TAREA=%INICIO%\VideoQA automatico.bat"

if not exist "%PY%" (
  echo   [X] VideoQA no esta instalado todavia.
  echo       Ejecuta primero "Instalar VideoQA.bat".
  pause
  exit /b 1
)

if exist "%TAREA%" (
  del "%TAREA%"
  echo   Revision automatica APAGADA.
  echo   Los videos ya no se revisan solos: usa "Revisar video".
) else (
  >"%TAREA%" echo @echo off
  >>"%TAREA%" echo chcp 65001 ^>nul
  >>"%TAREA%" echo start "" /min "%PY%" -m videoqa_win.cli watch
  echo   Revision automatica ENCENDIDA.
  echo   Desde ahora, todo lo que dejes en %VQ%\01_Entrada
  echo   se revisa solo. Arranca cada vez que enciendes el PC.
  start "" /min "%PY%" -m videoqa_win.cli watch
)

echo.
pause
exit /b 0
```

`bat/Diagnostico.bat`:
```bat
@echo off
chcp 65001 >nul
setlocal
title Diagnostico VideoQA

set "VQ=%USERPROFILE%\VideoQA"
set "PY=%VQ%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo   VideoQA no esta instalado: no hay nada que revisar.
  echo   Ejecuta "Instalar VideoQA.bat".
  pause
  exit /b 1
)

"%PY%" -m videoqa_win.cli diagnostico
echo.
echo   Se guardo "diagnostico.txt" en tu Escritorio.
echo   Mandalo por chat a quien te paso la herramienta.
echo.
pause
exit /b 0
```

`bat/Actualizar VideoQA.bat`:
```bat
@echo off
chcp 65001 >nul
setlocal
title Actualizar VideoQA

set "VQ=%USERPROFILE%\VideoQA"
set "PY=%VQ%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo   [X] VideoQA no esta instalado todavia.
  pause
  exit /b 1
)

echo   Buscando novedades...
"%PY%" -m pip install --upgrade "videoqa-win @ git+https://github.com/hongs05/videoqa-win@main"
if errorlevel 1 (
  echo   [X] No pude actualizar. Revisa tu internet y vuelve a intentarlo.
  pause
  exit /b 1
)
echo   Listo, ya tienes la ultima version.
echo.
pause
exit /b 0
```

- [ ] **Step 5: Asegurar los saltos de línea CRLF**

```bash
cd ~/videoqa-win
python3 - <<'PY'
from pathlib import Path
for p in Path("bat").glob("*.bat"):
    crudo = p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    p.write_bytes(crudo)
    print(p.name, "CRLF")
PY
printf 'bat/*.bat -text\n' >> .gitattributes
```

- [ ] **Step 6: Correr los tests**

Run: `uv run pytest tests/unit/test_bat.py -q`
Expected: 20 passed (5 archivos × 3 paramétricos + 4 sueltos… el conteo exacto depende de los paramétricos; lo que importa es que no falle ninguno).

Run: `uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add bat .gitattributes tests/unit/test_bat.py
git commit -m "feat: instalador y accesos directos de Windows"
```

---

### Task 13: Documentación para el editor y cierre

**Files:**
- Create: `LEEME.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: la guía de una página que se le entrega al editor.

- [ ] **Step 1: Escribir `LEEME.md`**

Una sola página, en español, tuteando, sin jerga. Contenido exacto:

```markdown
# VideoQA — revisa tus videos antes de subirlos

Esta herramienta revisa un video en tu PC y te dice qué corregir **antes** de que lo subas a
Drive. Así evitas que te lo devuelvan por cosas como una palabra mal escrita o un color que no
es de la marca.

No reemplaza la revisión oficial: esa sigue haciéndose después. Esto es para que llegues limpio.

## Instalar (una sola vez, ~15 minutos)

1. Descomprime el archivo que te pasaron.
2. Haz doble clic en **`Instalar VideoQA.bat`**. Si Windows avisa que es de un origen
   desconocido, elige **Más información → Ejecutar de todas formas**.
3. Espera. Cuando termine, en tu Escritorio aparecen cuatro accesos: **Revisar video**,
   **Activar automatico**, **Diagnostico** y **Actualizar VideoQA**.

## Usar

**La forma rápida:** arrastra el video encima de **Revisar video** y espera. Al terminar se abre
el reporte en el navegador.

**La otra forma:** deja los videos en `C:\Users\<tu usuario>\VideoQA\01_Entrada` y haz doble clic
en **Revisar video**.

**Para que lo haga solo:** doble clic en **Activar automatico**. Desde entonces, todo lo que
dejes en `01_Entrada` se revisa sin que hagas nada. Para apagarlo, doble clic otra vez.

## Qué te va a decir

Cada video acaba en una de dos carpetas, con su reporte al lado:

- **`03_Aprobado`** 🟢 — no encontró nada que corregir. Súbelo.
- **`02_Con_errores`** 🔴 — hay cosas que arreglar. Abre **`reporte.html`**: cada problema viene
  con el segundo exacto y una foto del momento.

También te deja `guion_real.md`, que es la transcripción de lo que realmente se dice en el video.

## Cosas que conviene saber

- **La primera revisión tarda mucho más** (descarga un modelo de voz de unos 250 MB). Solo pasa
  una vez.
- **Las tildes**: esta versión lee el texto del video pero no distingue los acentos, así que
  cuando te avise de una tilde, compruébalo a ojo — puede estar bien puesta.
- **Palabras que marca mal**: si marca como error un nombre de marca o una palabra que usan
  ustedes, añádela al archivo `VideoQA\_config\glosario.txt`, una por línea.
- **Si algo falla**: doble clic en **Diagnostico**, y manda por chat el `diagnostico.txt` que
  deja en el Escritorio.
```

- [ ] **Step 2: Actualizar `README.md`**

Añade al README del repo: enlace a `LEEME.md` para el editor, la nota de que el gate oficial está en la Mac con el plugin `aura`, y la sección de desarrollo (`uv sync`, `uv run pytest -q`, `VIDEOQA_WIN_LENTO=1` para los tests con modelos, y que lo específico de Windows solo se valida en un PC real).

- [ ] **Step 3: Correr la suite completa una última vez**

```bash
uv run pytest -q
VIDEOQA_WIN_LENTO=1 uv run pytest -q
```
Expected: la primera todo verde con los lentos salteados; la segunda todo verde con los lentos incluidos (descarga modelos la primera vez).

- [ ] **Step 4: Commit**

```bash
git add LEEME.md README.md
git commit -m "docs: guía del editor y notas de desarrollo"
```

- [ ] **Step 5: Publicar el repo**

```bash
cd ~/videoqa-win
gh repo create videoqa-win --public --source=. --remote=origin \
  --description "VideoQA para Windows — pre-chequeo local de videos (usa el motor videoqa)"
git push -u origin main
git tag -a v0.1.0 -m "VideoQA para Windows v0.1.0"
git push origin --tags
```

- [ ] **Step 6: Verificar que se instala desde cero como lo hará el editor**

En un entorno limpio (no en el repo), comprueba que el paquete se resuelve desde GitHub:
```bash
cd /tmp && rm -rf probar-win && mkdir probar-win && cd probar-win
uv venv --python 3.12 && uv pip install "videoqa-win @ git+https://github.com/hongs05/videoqa-win@main"
uv run python -c "import videoqa_win, videoqa; videoqa_win.activar(); print('instalación desde git OK')"
```
Expected: "instalación desde git OK". Esto valida la cadena completa de dependencias (motor incluido) tal como la vivirá el PC del editor; lo que queda sin probar son los `.bat` y `winget`, que solo existen en Windows.

---

## Auto-revisión del plan

**Cobertura del spec:**
- §3 arquitectura de dos proyectos → Tasks 1, 4 (dependencia por git) y 13 (publicación)
- §4.1 dependencias opcionales → Task 1; §4.2 registro de backends → Task 1; §4.3 prompt en el paquete → Task 2; §4.4 reporte HTML → Task 3
- §5 backends (RapidOCR, faster-whisper, spylls) → Tasks 6, 7, 8; diferencias conocidas de confianza y tildes → Tasks 7 (`MIN_CONF`), 9 (tildes) y 10 (`ocr_min_conf: 0.4`)
- §6 interfaz (carpeta vigilada, arrastrar y soltar, HTML, automático, diagnóstico) → Tasks 11 y 12
- §7 instalador → Task 12; actualización → Task 12 (`Actualizar VideoQA.bat`)
- §8 juez Ollama opcional → Task 11
- §9 manejo de errores → Task 8 (sin GPU y fallo de modelo), Task 7 (OCR que falla), Task 11 (Ollama), Task 12 (rutas citadas y UTF-8), y el motor ya cubre el resto
- §10 pruebas → cada task trae las suyas; integración en Task 10; límite de Windows documentado en Tasks 12, 13
- §11 fuera de alcance → respetado: no se toca el gate de la Mac, no hay Sheet ni notificaciones

**Consistencia de tipos:** `bbox` es `[x, y, w, h]` normalizado con origen arriba-izquierda en el contrato del motor (Task 1), en `convertir_caja` (Task 7) y en los tests de `checks_win` (Task 9). El contrato de transcripción devuelve `{"language", "text", "segments"}` en Tasks 1, 8 y 10. `Runner` es `(prompt, cwd) -> str` en Tasks 11 (`runner_ollama`, `_sin_juez`) y en el motor. `Result(status, findings, dest, error)` se consume igual en Tasks 10, 11 y 12.

**Diferencia consciente respecto al spec:** el spec menciona `%USERPROFILE%\VideoQA` como única carpeta; el plan separa la carpeta **visible** de trabajo (`%USERPROFILE%\VideoQA`, donde el editor deja los videos) de la de **datos** (`%LOCALAPPDATA%\VideoQA`, con modelos, diccionarios, trabajos intermedios y registro), para que el editor no vea 300 MB de modelos mezclados con sus videos.
