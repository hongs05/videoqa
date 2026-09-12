# VideoQA Pipeline — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline local en macOS que revisa automáticamente cada video subido a `01_Entrada/` de Drive (ortografía, marca, inconsistencias, bloopers), genera `reporte.md` + `guion_real.md`, y lo mueve a `03_Aprobado/` o `02_Con_errores/`, actualizando un Google Sheet.

**Architecture:** Paquete Python `videoqa` con etapas idempotentes por video (ffprobe → Whisper → análisis ffmpeg → frames → OCR → color), checks deterministas en código, y un "juez" que invoca `claude -p` con un skill de revisor. Un watcher por polling procesa la cola de `01_Entrada/`; `launchd` lo mantiene vivo. Estado intermedio en `~/.videoqa/jobs/<video>/`.

**Tech Stack:** Python 3.12 + `uv`, `ffmpeg`/`ffprobe`, `mlx-whisper`, `ocrmac` (Apple Vision), `numpy`, `pillow`, `pyspellchecker`, `pyyaml`, `gspread` + `google-auth`, Claude Code CLI (`claude -p --output-format json`), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-11-video-qa-pipeline-design.md`

## Global Constraints

- macOS Apple Silicon; Python **3.12** gestionado por `uv`.
- Sin API de pago de Anthropic: todo juicio de Claude va por `claude -p` (suscripción claude.ai).
- Claude Code en modo `-p` solo puede leer archivos **dentro de su `cwd`** sin pedir permiso → todo lo que Claude deba leer se copia al job dir (o se ejecuta con `cwd=_config/` para el PDF).
- Nunca aprobar por defecto: si el juez falla, el video va a `02_Con_errores/` con estado `❌ Error`.
- Sin versionado: mismo nombre de video = re-revisar y sobreescribir.
- Idioma de textos de usuario (reportes, títulos de hallazgos, skill): **español**.
- Carpetas Drive: `_config/`, `01_Entrada/`, `02_Con_errores/`, `03_Aprobado/` bajo `drive_root`.
- Severidades y umbrales viven en `reglas.yaml`; ningún check hardcodea severidad.
- Coordenadas de cajas OCR: normalizadas `[x, y, w, h]` con origen **arriba-izquierda** (Apple Vision devuelve origen abajo-izquierda; se convierte en la etapa OCR).
- Frames a **2 fps** (`frames.fps` en reglas) + un frame por corte de escena; período de muestreo = 0.5 s.
- Todas las salidas de etapa son JSON en el job dir; `Job.run_stage` las cachea.
- Commits pequeños, mensajes en inglés con prefijo `feat:`/`test:`/`docs:`/`chore:`.

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml` | deps, entry point `videoqa`, config pytest |
| `reglas.yaml` | severidades, umbrales, parámetros de frames/claude |
| `videoqa/config.py` | `Settings` (rutas Drive, jobs, sheet, claude) y `load_rules` |
| `videoqa/findings.py` | dataclass `Finding`, (de)serialización, orden, conteo |
| `videoqa/job.py` | `Job`: job dir, `run_stage` idempotente, `state.json` |
| `videoqa/stages/probe.py` | ffprobe → `probe.json` |
| `videoqa/stages/technical.py` | ffmpeg blackdetect/freezedetect/scene/silencedetect/astats → `technical.json` |
| `videoqa/stages/frames.py` | extracción de frames → `frames/` + `frames.json` |
| `videoqa/stages/transcribe.py` | audio wav + mlx-whisper → `transcript.json` |
| `videoqa/stages/ocr.py` | Apple Vision por frame + deduplicado en apariciones → `ocr.json` |
| `videoqa/stages/color.py` | color dominante del trazo por aparición → `ocr_color.json` |
| `videoqa/checks/colors.py` | sRGB→Lab y ΔE2000 |
| `videoqa/checks/brand_color.py` | color de texto vs paleta |
| `videoqa/checks/spelling.py` | diccionario ES + glosario + puntuación |
| `videoqa/checks/timing.py` | texto <1 s, zona tapada, desincronía |
| `videoqa/checks/technical.py` | negro/congelado/silencio/clipping/aspecto/sin audio |
| `videoqa/claude_runner.py` | `run_claude(prompt, cwd)` vía subprocess, `extract_json` |
| `videoqa/brand.py` | PDF → `brand.json` con Claude, cache por sha256/mtime |
| `videoqa/judge.py` | selección de frames, prompt, parseo/validación del veredicto |
| `.claude/skills/revisor-video/SKILL.md` | prompt del revisor (rol, reglas, esquema JSON, ejemplos) |
| `videoqa/report.py` | `reporte.md` + `evidencia/` |
| `videoqa/gate.py` | decisión 🟢/🔴 y movimiento a carpeta destino |
| `videoqa/sheet.py` | upsert en Google Sheet + cola de pendientes |
| `videoqa/pipeline.py` | `process_video`: orquesta etapas, checks, juez, reporte, gate, sheet |
| `videoqa/watcher.py` | polling de `01_Entrada/`, estabilidad de archivo, cola |
| `videoqa/cli.py` | `videoqa init|brand|run|watch` |
| `launchd/com.videoqa.watcher.plist` | LaunchAgent |
| `tests/fixtures/make_fixtures.py` | genera videos sintéticos con ffmpeg + `say` |
| `tests/unit/*` | un archivo por módulo |
| `tests/integration/test_pipeline.py` | pipeline completo con juez stub sobre fixtures |
| `docs/SETUP.md` | instalación y operación para el equipo |

---

### Task 1: Bootstrap del proyecto

**Files:**
- Create: `pyproject.toml`, `reglas.yaml`, `.gitignore`, `videoqa/__init__.py`, `videoqa/stages/__init__.py`, `videoqa/checks/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/conftest.py`
- Test: `tests/unit/test_rules.py`

**Interfaces:**
- Produces: `reglas.yaml` con claves `severities`, `thresholds`, `frames`, `claude` usadas por todos los checks.

- [ ] **Step 1: Instalar herramientas del sistema**

```bash
brew install uv ffmpeg
uv --version && ffmpeg -version | head -1
```

- [ ] **Step 2: Crear `pyproject.toml`**

```toml
[project]
name = "videoqa"
version = "0.1.0"
description = "Pipeline de revisión automática de videos (QA pre-publicación)"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pyyaml>=6.0",
    "numpy>=1.26",
    "pillow>=10.0",
    "pyspellchecker>=0.8",
    "mlx-whisper>=0.4",
    "ocrmac>=1.0",
    "gspread>=6.0",
    "google-auth>=2.0",
]

[project.scripts]
videoqa = "videoqa.cli:main"

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["videoqa"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: requiere modelos/CLI reales (Whisper, Claude); correr con VIDEOQA_SLOW=1"]
```

- [ ] **Step 3: Crear `reglas.yaml`**

```yaml
# Severidades: blocker | warning | info
severities:
  spelling_unknown_word: blocker
  spelling_punctuation: warning
  brand_color: blocker
  text_visible_short: warning
  subtitle_desync: warning
  text_occluded: warning
  black_frame: blocker
  frozen_frame: blocker
  silence: warning
  audio_clipping: warning
  aspect_ratio: warning
  no_audio: warning
  judge_unavailable: warning

thresholds:
  color_delta_e: 8.0        # ΔE2000 máximo para considerar un color "de paleta"
  min_text_visible_s: 1.0   # texto visible menos tiempo = ilegible
  desync_s: 1.0             # subtítulo vs audio
  black_min_s: 0.5
  freeze_min_s: 0.5
  silence_min_s: 2.0
  edge_margin_s: 0.5        # ignorar negro/silencio en los primeros/últimos N s
  occluded_bottom: 0.80     # y+h por encima de esto = tapado por UI de TikTok/Reels
  occluded_right: 0.85      # x+w por encima de esto = tapado por iconos laterales
  aspect_tolerance: 0.02
  clipping_peak_db: -0.1
  clipping_min_count: 100

frames:
  fps: 2                    # frames por segundo para OCR
  scene_threshold: 0.3      # sensibilidad de corte de escena (0-1)

claude:
  max_frames: 15
  frame_height: 720
  timeout_s: 600
```

- [ ] **Step 4: Crear `.gitignore` y paquetes vacíos**

```bash
cat > .gitignore <<'GI'
.venv/
__pycache__/
*.pyc
.pytest_cache/
tests/fixtures/out/
*.egg-info/
GI
mkdir -p videoqa/stages videoqa/checks tests/unit tests/integration tests/fixtures
touch videoqa/__init__.py videoqa/stages/__init__.py videoqa/checks/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 5: `tests/conftest.py`**

```python
import os
import pytest

def pytest_runtest_setup(item):
    if "slow" in item.keywords and not os.environ.get("VIDEOQA_SLOW"):
        pytest.skip("test lento: exporta VIDEOQA_SLOW=1 para correrlo")
```

- [ ] **Step 6: Test que valida `reglas.yaml`**

`tests/unit/test_rules.py`:
```python
from pathlib import Path
import yaml

RULES = Path(__file__).resolve().parents[2] / "reglas.yaml"

def test_rules_have_required_sections():
    data = yaml.safe_load(RULES.read_text())
    assert set(data) >= {"severities", "thresholds", "frames", "claude"}
    assert all(v in {"blocker", "warning", "info"} for v in data["severities"].values())
    assert data["frames"]["fps"] == 2
```

- [ ] **Step 7: Instalar dependencias y correr el test**

```bash
uv python install 3.12
uv sync
uv run pytest -q
```
Expected: `1 passed`

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: bootstrap videoqa project with uv, rules and pytest"
```

---

### Task 2: Config y modelo de hallazgos

**Files:**
- Create: `videoqa/config.py`, `videoqa/findings.py`
- Test: `tests/unit/test_config.py`, `tests/unit/test_findings.py`

**Interfaces:**
- Produces:
  - `Settings(drive_root, jobs_dir, sheet_id, service_account_json, claude_bin, whisper_model)` con propiedades `entrada`, `con_errores`, `aprobado`, `config_dir`.
  - `load_settings(path: Path | None = None) -> Settings` (lee YAML; `VIDEOQA_CONFIG` o `~/.videoqa/config.yaml`).
  - `load_rules(path: Path = RULES_PATH) -> dict`.
  - `Finding(id, type, severity, t_start, t_end, title, detail, suggestion="", frame=None, bbox=None, source="code", check="")`, `Finding.to_dict()`, `Finding.from_dict(d)`.
  - `save_findings(path, findings)`, `load_findings(path) -> list[Finding]`, `sort_findings(findings)`, `count_by_severity(findings) -> dict`.

- [ ] **Step 1: Tests de config**

`tests/unit/test_config.py`:
```python
from pathlib import Path
import pytest
from videoqa.config import Settings, load_settings, load_rules

def test_load_settings_from_yaml(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("drive_root: /tmp/drive\nsheet_id: abc\n")
    s = load_settings(cfg)
    assert s.drive_root == Path("/tmp/drive")
    assert s.entrada == Path("/tmp/drive/01_Entrada")
    assert s.con_errores == Path("/tmp/drive/02_Con_errores")
    assert s.aprobado == Path("/tmp/drive/03_Aprobado")
    assert s.config_dir == Path("/tmp/drive/_config")
    assert s.sheet_id == "abc"
    assert s.service_account_json is None
    assert s.claude_bin == "claude"
    assert s.jobs_dir == Path.home() / ".videoqa" / "jobs"

def test_load_settings_requires_drive_root(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sheet_id: abc\n")
    with pytest.raises(ValueError):
        load_settings(cfg)

def test_load_rules_default():
    rules = load_rules()
    assert rules["severities"]["brand_color"] == "blocker"
```

- [ ] **Step 2: Correr para ver fallo**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: FAIL `ModuleNotFoundError: videoqa.config`

- [ ] **Step 3: Implementar `videoqa/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path.home() / ".videoqa" / "config.yaml"
RULES_PATH = Path(__file__).resolve().parent.parent / "reglas.yaml"
SKILL_PATH = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "revisor-video" / "SKILL.md"


@dataclass
class Settings:
    drive_root: Path
    jobs_dir: Path = field(default_factory=lambda: Path.home() / ".videoqa" / "jobs")
    sheet_id: str | None = None
    service_account_json: Path | None = None
    claude_bin: str = "claude"
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"

    @property
    def entrada(self) -> Path:
        return self.drive_root / "01_Entrada"

    @property
    def con_errores(self) -> Path:
        return self.drive_root / "02_Con_errores"

    @property
    def aprobado(self) -> Path:
        return self.drive_root / "03_Aprobado"

    @property
    def config_dir(self) -> Path:
        return self.drive_root / "_config"


def load_settings(path: Path | None = None) -> Settings:
    path = path or Path(os.environ.get("VIDEOQA_CONFIG", DEFAULT_CONFIG))
    data = yaml.safe_load(path.read_text()) or {}
    if "drive_root" not in data:
        raise ValueError(f"{path}: falta la clave 'drive_root'")
    kwargs = {"drive_root": Path(data["drive_root"]).expanduser()}
    if "jobs_dir" in data:
        kwargs["jobs_dir"] = Path(data["jobs_dir"]).expanduser()
    if data.get("sheet_id"):
        kwargs["sheet_id"] = str(data["sheet_id"])
    if data.get("service_account_json"):
        kwargs["service_account_json"] = Path(data["service_account_json"]).expanduser()
    if data.get("claude_bin"):
        kwargs["claude_bin"] = str(data["claude_bin"])
    if data.get("whisper_model"):
        kwargs["whisper_model"] = str(data["whisper_model"])
    return Settings(**kwargs)


def load_rules(path: Path = RULES_PATH) -> dict:
    return yaml.safe_load(path.read_text())
```

- [ ] **Step 4: Correr tests de config**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: `3 passed`

- [ ] **Step 5: Tests de findings**

`tests/unit/test_findings.py`:
```python
from videoqa.findings import Finding, save_findings, load_findings, sort_findings, count_by_severity

def make(id, severity, t):
    return Finding(id=id, type="tecnico", severity=severity, t_start=t, t_end=t + 1,
                   title="t", detail="d")

def test_roundtrip_json(tmp_path):
    f = Finding(id="a", type="marca", severity="blocker", t_start=1.0, t_end=2.0,
                title="Color", detail="x", suggestion="y", frame="frames/sec_0001.jpg",
                bbox=[0.1, 0.2, 0.3, 0.4], source="code", check="brand_color")
    p = tmp_path / "f.json"
    save_findings(p, [f])
    assert load_findings(p) == [f]

def test_from_dict_ignores_unknown_keys():
    f = Finding.from_dict({"id": "a", "type": "blooper", "severity": "warning", "t_start": 0,
                           "t_end": 1, "title": "t", "detail": "d", "extra": 1})
    assert f.id == "a" and f.suggestion == ""

def test_sort_by_severity_then_time():
    fs = [make("w2", "warning", 5), make("b", "blocker", 9), make("w1", "warning", 2), make("i", "info", 0)]
    assert [f.id for f in sort_findings(fs)] == ["b", "w1", "w2", "i"]

def test_count_by_severity():
    fs = [make("a", "blocker", 0), make("b", "warning", 0), make("c", "warning", 0)]
    assert count_by_severity(fs) == {"blocker": 1, "warning": 2, "info": 0}
```

- [ ] **Step 6: Implementar `videoqa/findings.py`**

```python
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
```

- [ ] **Step 7: Correr todo**

Run: `uv run pytest -q`
Expected: `8 passed`

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: settings loader and Finding model"
```

---

### Task 3: Fixtures sintéticos de video

**Files:**
- Create: `tests/fixtures/make_fixtures.py`, `tests/fixtures/brand.json`, `tests/fixtures/glosario.txt`
- Test: `tests/unit/test_fixtures.py`

**Interfaces:**
- Produces: `tests/fixtures/out/{spelling_color.mp4, black_screen.mp4, clean.mp4, no_audio.mp4}` (12 s, 1080×1920, 30 fps). Función `build_all(out_dir: Path) -> dict[str, Path]` y fixture pytest `fixture_videos` (session) en `tests/conftest.py`.
- Contenido:
  - `spelling_color.mp4`: fondo `#1A1A1A`, texto **"Aprobecha la oferta"** en `#FF3B30` visible t=2–8 s; voz `say` "Aprovecha la oferta de verano".
  - `black_screen.mp4`: fondo `#1A1A1A`, texto "Oferta de verano" en `#FFFFFF` t=1–10 s, pantalla negra t=5–6 s; misma voz.
  - `clean.mp4`: fondo `#1A1A1A`, texto "Oferta de verano" `#F5C518` t=1–10 s; voz.
  - `no_audio.mp4`: igual a clean pero `-an`.

- [ ] **Step 1: Crear `tests/fixtures/brand.json` y `glosario.txt`**

```json
{
  "palette": [
    {"name": "Negro", "hex": "#1A1A1A"},
    {"name": "Blanco", "hex": "#FFFFFF"},
    {"name": "Amarillo", "hex": "#F5C518"}
  ],
  "fonts": ["Arial"],
  "rules": ["Los títulos nunca en rojo"],
  "logo_required": false,
  "source_pdf_sha256": "fixture"
}
```

`glosario.txt`:
```
VideoQA
TikTok
```

- [ ] **Step 2: Test de fixtures**

`tests/unit/test_fixtures.py`:
```python
import subprocess, json
from tests.fixtures.make_fixtures import build_all

def test_build_all_creates_four_videos(fixture_videos):
    assert set(fixture_videos) == {"spelling_color", "black_screen", "clean", "no_audio"}
    for p in fixture_videos.values():
        assert p.exists() and p.stat().st_size > 10_000

def test_no_audio_fixture_has_no_audio_stream(fixture_videos):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
                          str(fixture_videos["no_audio"])], capture_output=True, text=True, check=True).stdout
    assert all(s["codec_type"] != "audio" for s in json.loads(out)["streams"])
```

Añadir a `tests/conftest.py`:
```python
from pathlib import Path
import pytest
from tests.fixtures.make_fixtures import build_all

FIXTURE_OUT = Path(__file__).resolve().parent / "fixtures" / "out"

@pytest.fixture(scope="session")
def fixture_videos():
    return build_all(FIXTURE_OUT)
```

- [ ] **Step 3: Correr para ver fallo**

Run: `uv run pytest tests/unit/test_fixtures.py -q`
Expected: FAIL `ModuleNotFoundError: tests.fixtures.make_fixtures`

- [ ] **Step 4: Implementar `tests/fixtures/make_fixtures.py`**

```python
"""Genera videos sintéticos con errores sembrados, usando ffmpeg y `say` de macOS."""
from __future__ import annotations

import subprocess
from pathlib import Path

FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
SIZE = "1080x1920"
DUR = 12
BG = "0x1A1A1A"
VOICE_TEXT = "Aprovecha la oferta de verano, solo por esta semana"


def _say(out_aiff: Path) -> None:
    if not out_aiff.exists():
        subprocess.run(["say", "-v", "Monica", "-o", str(out_aiff), VOICE_TEXT], check=True)


def _drawtext(text: str, color: str, start: float, end: float) -> str:
    return (f"drawtext=fontfile={FONT}:text='{text}':fontcolor={color}:fontsize=90:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{start},{end})'")


def _render(out: Path, vf: str, audio: Path | None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"color=c={BG}:s={SIZE}:r=30:d={DUR}"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-vf", vf, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-t", str(DUR), str(out)]
    subprocess.run(cmd, check=True)


def build_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    voice = out_dir / "voz.aiff"
    _say(voice)
    specs = {
        "spelling_color": (_drawtext("Aprobecha la oferta", "0xFF3B30", 2, 8), voice),
        "black_screen": (_drawtext("Oferta de verano", "0xFFFFFF", 1, 10)
                         + ",drawbox=enable='between(t,5,6)':x=0:y=0:w=iw:h=ih:color=black:t=fill", voice),
        "clean": (_drawtext("Oferta de verano", "0xF5C518", 1, 10), voice),
        "no_audio": (_drawtext("Oferta de verano", "0xF5C518", 1, 10), None),
    }
    result = {}
    for name, (vf, audio) in specs.items():
        out = out_dir / f"{name}.mp4"
        if not out.exists():
            _render(out, vf, audio)
        result[name] = out
    return result


if __name__ == "__main__":
    for k, v in build_all(Path(__file__).parent / "out").items():
        print(k, v)
```

- [ ] **Step 5: Correr tests**

Run: `uv run pytest tests/unit/test_fixtures.py -q`
Expected: `2 passed` (la primera vez tarda ~20 s generando los videos)

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "test: synthetic video fixtures with seeded errors"
```

---

### Task 4: Job dir con etapas idempotentes

**Files:**
- Create: `videoqa/job.py`
- Test: `tests/unit/test_job.py`

**Interfaces:**
- Produces: `Job(video: Path, jobs_root: Path)` con `.video`, `.name` (stem), `.dir`, `.path(rel) -> Path`, `.run_stage(name: str, output_rel: str, fn: Callable[[Job], dict]) -> dict`, `.reset()`, `.state() -> dict`.

- [ ] **Step 1: Tests**

`tests/unit/test_job.py`:
```python
import json
import pytest
from videoqa.job import Job

def test_run_stage_writes_output_and_caches(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    calls = []
    def fn(j):
        calls.append(j.name)
        return {"ok": True}
    assert job.run_stage("probe", "probe.json", fn) == {"ok": True}
    assert job.run_stage("probe", "probe.json", fn) == {"ok": True}
    assert calls == ["promo"]
    assert json.loads(job.path("probe.json").read_text()) == {"ok": True}
    assert job.state()["stages"]["probe"]["status"] == "done"

def test_failed_stage_records_state_and_reraises(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    def boom(j):
        raise RuntimeError("ffmpeg murió")
    with pytest.raises(RuntimeError):
        job.run_stage("probe", "probe.json", boom)
    assert job.state()["stages"]["probe"]["status"] == "failed"
    assert not job.path("probe.json").exists()

def test_reset_clears_dir(tmp_path):
    video = tmp_path / "promo.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    job.run_stage("probe", "probe.json", lambda j: {})
    job.reset()
    assert job.dir.exists() and not job.path("probe.json").exists()
```

- [ ] **Step 2: Correr para ver fallo**

Run: `uv run pytest tests/unit/test_job.py -q` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/job.py`**

```python
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

log = logging.getLogger("videoqa")


class Job:
    """Directorio de trabajo de un video con etapas cacheadas en JSON."""

    def __init__(self, video: Path, jobs_root: Path):
        self.video = Path(video)
        self.name = self.video.stem
        self.dir = Path(jobs_root) / self.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"

    def path(self, rel: str) -> Path:
        return self.dir / rel

    def state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"video": str(self.video), "stages": {}}

    def _mark(self, stage: str, status: str, error: str | None = None) -> None:
        st = self.state()
        st["stages"][stage] = {"status": status, "at": datetime.now().isoformat(timespec="seconds")}
        if error:
            st["stages"][stage]["error"] = error
        self.state_path.write_text(json.dumps(st, ensure_ascii=False, indent=2))

    def run_stage(self, name: str, output_rel: str, fn: Callable[["Job"], dict]) -> dict:
        out = self.path(output_rel)
        if out.exists():
            log.info("[%s] etapa %s: cacheada", self.name, name)
            return json.loads(out.read_text())
        log.info("[%s] etapa %s: ejecutando", self.name, name)
        try:
            result = fn(self)
        except Exception as e:  # noqa: BLE001 — registramos y re-lanzamos
            self._mark(name, "failed", f"{type(e).__name__}: {e}")
            raise
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        self._mark(name, "done")
        return result

    def reset(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Correr tests** → `3 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Job directory with idempotent stages"
```

---

### Task 5: Etapa probe (ffprobe)

**Files:**
- Create: `videoqa/stages/probe.py`
- Test: `tests/unit/test_probe.py`

**Interfaces:**
- Produces: `probe(job: Job) -> dict` con `{"duration": float, "width": int, "height": int, "fps": float, "has_audio": bool}`; helper `run_ffprobe(video: Path) -> dict` (JSON crudo).

- [ ] **Step 1: Tests**

`tests/unit/test_probe.py`:
```python
from videoqa.job import Job
from videoqa.stages.probe import probe

def test_probe_reads_clean_fixture(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    p = probe(job)
    assert 11.5 <= p["duration"] <= 12.5
    assert (p["width"], p["height"]) == (1080, 1920)
    assert abs(p["fps"] - 30) < 0.01
    assert p["has_audio"] is True

def test_probe_detects_missing_audio(fixture_videos, tmp_path):
    assert probe(Job(fixture_videos["no_audio"], tmp_path))["has_audio"] is False
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/probe.py`**

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from videoqa.job import Job


def run_ffprobe(video: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(video)]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)


def _fps(stream: dict) -> float:
    num, _, den = stream.get("r_frame_rate", "0/1").partition("/")
    return float(num) / float(den) if float(den or 0) else 0.0


def probe(job: Job) -> dict:
    raw = run_ffprobe(job.video)
    video = next(s for s in raw["streams"] if s["codec_type"] == "video")
    audio = next((s for s in raw["streams"] if s["codec_type"] == "audio"), None)
    return {
        "duration": float(raw["format"]["duration"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": _fps(video),
        "has_audio": audio is not None,
    }
```

- [ ] **Step 4: Correr tests** → `2 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: ffprobe stage"
```

---

### Task 6: Etapa de análisis técnico (ffmpeg)

**Files:**
- Create: `videoqa/stages/technical.py`
- Test: `tests/unit/test_technical_stage.py`

**Interfaces:**
- Produces: `analyze(job: Job, has_audio: bool, scene_threshold: float) -> dict` con:
  ```json
  {"black": [{"start": 5.0, "end": 6.0}], "freeze": [{"start":..,"end":..}],
   "scene_cuts": [5.03], "silence": [{"start":..,"end":..}],
   "audio": {"peak_db": -1.2, "peak_count": 3} | null}
  ```
  Helpers puros: `parse_black(stderr)`, `parse_freeze(stderr)`, `parse_scene(stderr)`, `parse_silence(stderr)`, `parse_astats(stderr)`.

- [ ] **Step 1: Tests**

`tests/unit/test_technical_stage.py`:
```python
from videoqa.job import Job
from videoqa.stages.technical import (analyze, parse_astats, parse_black, parse_freeze,
                                       parse_scene, parse_silence)

BLACK = "[blackdetect @ 0x1] black_start:5 black_end:6.033 black_duration:1.033\n"
FREEZE = ("[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 5.0\n"
          "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 1.0\n"
          "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 6.0\n")
SCENE = "[Parsed_showinfo_1 @ 0x1] n:   0 pts:  151 pts_time:5.033   pos: 1 fmt:yuv420p\n"
SILENCE = ("[silencedetect @ 0x1] silence_start: 2.1\n"
           "[silencedetect @ 0x1] silence_end: 4.6 | silence_duration: 2.5\n")
ASTATS = ("[Parsed_astats_1 @ 0x1] Channel: 1\n[Parsed_astats_1 @ 0x1] Peak level dB: -3.0\n"
          "[Parsed_astats_1 @ 0x1] Overall\n[Parsed_astats_1 @ 0x1] Peak level dB: -0.05\n"
          "[Parsed_astats_1 @ 0x1] Peak count: 250\n")

def test_parsers():
    assert parse_black(BLACK) == [{"start": 5.0, "end": 6.033}]
    assert parse_freeze(FREEZE) == [{"start": 5.0, "end": 6.0}]
    assert parse_scene(SCENE) == [5.033]
    assert parse_silence(SILENCE) == [{"start": 2.1, "end": 4.6}]
    assert parse_astats(ASTATS) == {"peak_db": -0.05, "peak_count": 250}

def test_analyze_black_screen_fixture(fixture_videos, tmp_path):
    t = analyze(Job(fixture_videos["black_screen"], tmp_path), has_audio=True, scene_threshold=0.3)
    assert any(4.8 <= b["start"] <= 5.2 and 5.8 <= b["end"] <= 6.2 for b in t["black"])
    assert t["audio"] is not None and "peak_db" in t["audio"]
    assert any(4.8 <= c <= 6.2 for c in t["scene_cuts"])

def test_analyze_no_audio_fixture(fixture_videos, tmp_path):
    t = analyze(Job(fixture_videos["no_audio"], tmp_path), has_audio=False, scene_threshold=0.3)
    assert t["audio"] is None and t["silence"] == []
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/technical.py`**

```python
from __future__ import annotations

import re
import subprocess

from videoqa.job import Job

_BLACK = re.compile(r"black_start:([\d.]+)\s+black_end:([\d.]+)")
_FREEZE_START = re.compile(r"freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"freeze_end:\s*([\d.]+)")
_SCENE = re.compile(r"pts_time:([\d.]+)")
_SIL_START = re.compile(r"silence_start:\s*([\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")
_PEAK_DB = re.compile(r"Peak level dB:\s*(-?[\d.]+|-inf)")
_PEAK_COUNT = re.compile(r"Peak count:\s*(\d+)")


def _ffmpeg(args: list[str]) -> str:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr[-1000:]}")
    return proc.stderr


def parse_black(stderr: str) -> list[dict]:
    return [{"start": float(a), "end": float(b)} for a, b in _BLACK.findall(stderr)]


def parse_freeze(stderr: str) -> list[dict]:
    starts = [float(x) for x in _FREEZE_START.findall(stderr)]
    ends = [float(x) for x in _FREEZE_END.findall(stderr)]
    return [{"start": s, "end": e} for s, e in zip(starts, ends)]


def parse_scene(stderr: str) -> list[float]:
    return [float(x) for x in _SCENE.findall(stderr)]


def parse_silence(stderr: str) -> list[dict]:
    starts = [float(x) for x in _SIL_START.findall(stderr)]
    ends = [float(x) for x in _SIL_END.findall(stderr)]
    return [{"start": s, "end": e} for s, e in zip(starts, ends)]


def parse_astats(stderr: str) -> dict | None:
    overall = stderr.rsplit("Overall", 1)
    if len(overall) < 2:
        return None
    tail = overall[1]
    db = _PEAK_DB.search(tail)
    cnt = _PEAK_COUNT.search(tail)
    if not db:
        return None
    peak = float("-inf") if db.group(1) == "-inf" else float(db.group(1))
    return {"peak_db": peak, "peak_count": int(cnt.group(1)) if cnt else 0}


def analyze(job: Job, has_audio: bool, scene_threshold: float) -> dict:
    video = str(job.video)
    vid_err = _ffmpeg(["-i", video, "-vf", "blackdetect=d=0.3:pix_th=0.10,freezedetect=n=-60dB:d=0.3", "-an"])
    scene_err = _ffmpeg(["-i", video, "-vf", f"select='gt(scene,{scene_threshold})',showinfo",
                         "-fps_mode", "vfr", "-an"])
    result = {
        "black": parse_black(vid_err),
        "freeze": parse_freeze(vid_err),
        "scene_cuts": parse_scene(scene_err),
        "silence": [],
        "audio": None,
    }
    if has_audio:
        aud_err = _ffmpeg(["-i", video, "-af", "silencedetect=n=-35dB:d=1.0,astats=metadata=0", "-vn"])
        result["silence"] = parse_silence(aud_err)
        result["audio"] = parse_astats(aud_err)
    return result
```

- [ ] **Step 4: Correr tests** → `3 passed`. Si `scene_cuts` sale vacío en el fixture de pantalla negra, bajar `scene_threshold` del test a `0.2` y ajustar el default en `reglas.yaml`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: ffmpeg technical analysis stage"
```

---

### Task 7: Etapa de frames

**Files:**
- Create: `videoqa/stages/frames.py`
- Test: `tests/unit/test_frames.py`

**Interfaces:**
- Produces: `extract_frames(job: Job, scene_cuts: list[float], fps: int) -> dict` → `{"fps": 2, "period": 0.5, "frames": [{"file": "frames/sec_0001.jpg", "t": 0.0, "kind": "second"|"scene"}, ...]}` ordenado por `t`.

- [ ] **Step 1: Tests**

`tests/unit/test_frames.py`:
```python
from PIL import Image
from videoqa.job import Job
from videoqa.stages.frames import extract_frames

def test_extract_two_fps_plus_scene_frames(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[1.0, 10.0], fps=2)
    seconds = [f for f in fr["frames"] if f["kind"] == "second"]
    scenes = [f for f in fr["frames"] if f["kind"] == "scene"]
    assert 22 <= len(seconds) <= 26
    assert len(scenes) == 2 and scenes[0]["t"] == 1.1
    assert fr["period"] == 0.5
    assert seconds[0]["t"] == 0.0 and seconds[1]["t"] == 0.5
    assert [f["t"] for f in fr["frames"]] == sorted(f["t"] for f in fr["frames"])
    img = Image.open(job.path(scenes[0]["file"]))
    assert img.size == (1080, 1920)
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/frames.py`**

```python
from __future__ import annotations

import subprocess

from videoqa.job import Job


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def extract_frames(job: Job, scene_cuts: list[float], fps: int) -> dict:
    out = job.path("frames")
    out.mkdir(exist_ok=True)
    period = 1.0 / fps
    _run(["-i", str(job.video), "-vf", f"fps={fps}", "-q:v", "3", str(out / "sec_%04d.jpg")])
    frames = []
    for i, p in enumerate(sorted(out.glob("sec_*.jpg")), start=1):
        frames.append({"file": f"frames/{p.name}", "t": round((i - 1) * period, 3), "kind": "second"})
    for k, t in enumerate(scene_cuts, start=1):
        name = f"scene_{k:03d}.jpg"
        ts = round(t + 0.1, 3)
        _run(["-ss", f"{ts:.3f}", "-i", str(job.video), "-frames:v", "1", "-q:v", "3", str(out / name)])
        if (out / name).exists():
            frames.append({"file": f"frames/{name}", "t": ts, "kind": "scene"})
    frames.sort(key=lambda f: f["t"])
    return {"fps": fps, "period": period, "frames": frames}
```

- [ ] **Step 4: Correr tests** → `1 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: frame extraction stage"
```

---

### Task 8: Etapa de transcripción (Whisper)

**Files:**
- Create: `videoqa/stages/transcribe.py`
- Test: `tests/unit/test_transcribe.py`

**Interfaces:**
- Produces: `transcribe(job: Job, has_audio: bool, model: str) -> dict` → `{"language": "es", "text": str, "segments": [{"start": float, "end": float, "text": str}]}`; `normalize(raw: dict) -> dict` puro; `extract_audio(video: Path, wav: Path) -> None`.

- [ ] **Step 1: Tests**

`tests/unit/test_transcribe.py`:
```python
import pytest
from videoqa.job import Job
from videoqa.stages.transcribe import normalize, transcribe

def test_normalize_strips_and_drops_empty():
    raw = {"language": "es", "segments": [
        {"start": 0.0, "end": 1.234, "text": "  Hola  "},
        {"start": 1.3, "end": 2.0, "text": "   "},
        {"start": 2.0, "end": 3.0, "text": "mundo"}]}
    out = normalize(raw)
    assert out["segments"] == [{"start": 0.0, "end": 1.23, "text": "Hola"},
                               {"start": 2.0, "end": 3.0, "text": "mundo"}]
    assert out["text"] == "Hola mundo" and out["language"] == "es"

def test_transcribe_without_audio_returns_empty(fixture_videos, tmp_path):
    out = transcribe(Job(fixture_videos["no_audio"], tmp_path), has_audio=False, model="x")
    assert out == {"language": "es", "text": "", "segments": []}

@pytest.mark.slow
def test_transcribe_real_fixture(fixture_videos, tmp_path):
    out = transcribe(Job(fixture_videos["clean"], tmp_path), has_audio=True,
                     model="mlx-community/whisper-large-v3-turbo")
    assert "oferta" in out["text"].lower()
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/transcribe.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from videoqa.job import Job

EMPTY = {"language": "es", "text": "", "segments": []}


def extract_audio(video: Path, wav: Path) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)


def normalize(raw: dict) -> dict:
    segments = []
    for s in raw.get("segments", []):
        text = str(s.get("text", "")).strip()
        if text:
            segments.append({"start": round(float(s["start"]), 2), "end": round(float(s["end"]), 2), "text": text})
    return {"language": raw.get("language", "es"), "text": " ".join(s["text"] for s in segments), "segments": segments}


def transcribe(job: Job, has_audio: bool, model: str) -> dict:
    if not has_audio:
        return dict(EMPTY)
    wav = job.path("audio.wav")
    extract_audio(job.video, wav)
    import mlx_whisper  # import tardío: carga MLX solo cuando hace falta

    raw = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language="es")
    return normalize(raw)
```

- [ ] **Step 4: Correr tests** → `2 passed, 1 skipped`. Luego una vez con modelo real (descarga ~1.5 GB la primera vez):

```bash
VIDEOQA_SLOW=1 uv run pytest tests/unit/test_transcribe.py -q
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: whisper transcription stage"
```

---

### Task 9: Etapa OCR (Apple Vision) y deduplicado

**Files:**
- Create: `videoqa/stages/ocr.py`
- Test: `tests/unit/test_ocr.py`

**Interfaces:**
- Produces:
  - `ocr_frame(path: Path) -> list[dict]` → `[{"text", "conf", "bbox": [x, y, w, h]}]` (origen arriba-izquierda).
  - `dedupe(raw: list[dict], period: float, gap: float = 1.5, iou_min: float = 0.3) -> list[dict]` → apariciones `[{"text", "bbox", "t_start", "t_end", "frame", "frames": [...]}]`.
  - `ocr_frames(job: Job, frames: list[dict], period: float) -> dict` → `{"raw": [{"file","t","items"}], "appearances": [...]}`.
  - `norm_text(s) -> str`, `iou(a, b) -> float`.

- [ ] **Step 1: Tests**

`tests/unit/test_ocr.py`:
```python
from videoqa.job import Job
from videoqa.stages.frames import extract_frames
from videoqa.stages.ocr import dedupe, iou, norm_text, ocr_frame, ocr_frames

def item(text, t, bbox=(0.2, 0.45, 0.6, 0.1), conf=0.9):
    return {"file": f"frames/{t}.jpg", "t": t, "items": [{"text": text, "conf": conf, "bbox": list(bbox)}]}

def test_iou_and_norm():
    assert iou([0, 0, 1, 1], [0, 0, 1, 1]) == 1.0
    assert iou([0, 0, 1, 1], [2, 2, 1, 1]) == 0.0
    assert norm_text("  Hola   MUNDO ") == "hola mundo"

def test_dedupe_merges_consecutive_frames_same_text():
    raw = [item("Oferta", 1.0), item("Oferta", 1.5), item("Oferta", 2.0), item("Otra", 3.0)]
    apps = dedupe(raw, period=0.5)
    assert len(apps) == 2
    assert apps[0]["text"] == "Oferta" and apps[0]["t_start"] == 1.0 and apps[0]["t_end"] == 2.5
    assert apps[0]["frame"] == "frames/1.0.jpg" and len(apps[0]["frames"]) == 3
    assert apps[1]["t_start"] == 3.0 and apps[1]["t_end"] == 3.5

def test_dedupe_splits_after_gap():
    raw = [item("Oferta", 1.0), item("Oferta", 5.0)]
    assert len(dedupe(raw, period=0.5)) == 2

def test_dedupe_keeps_highest_confidence_text():
    raw = [item("0ferta", 1.0, conf=0.5), item("Oferta", 1.5, conf=0.95)]
    assert dedupe(raw, period=0.5)[0]["text"] == "Oferta"

def test_ocr_frame_reads_fixture_text(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[], fps=2)
    frame_at_5s = next(f for f in fr["frames"] if f["t"] == 5.0)
    items = ocr_frame(job.path(frame_at_5s["file"]))
    texts = " ".join(norm_text(i["text"]) for i in items)
    assert "oferta de verano" in texts
    x, y, w, h = items[0]["bbox"]
    assert 0.3 < y < 0.6 and 0 < w <= 1 and 0 < h < 0.2  # centrado verticalmente, origen arriba

def test_ocr_frames_builds_appearances(fixture_videos, tmp_path):
    job = Job(fixture_videos["clean"], tmp_path)
    fr = extract_frames(job, scene_cuts=[], fps=2)
    out = ocr_frames(job, fr["frames"], period=fr["period"])
    apps = [a for a in out["appearances"] if "oferta" in norm_text(a["text"])]
    assert len(apps) == 1
    assert 0.5 <= apps[0]["t_start"] <= 1.5 and 9.5 <= apps[0]["t_end"] <= 10.5
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/ocr.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

from videoqa.job import Job

_WS = re.compile(r"\s+")


def norm_text(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


def iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def ocr_frame(path: Path) -> list[dict]:
    from ocrmac import ocrmac  # import tardío: pyobjc/Vision

    results = ocrmac.OCR(str(path), language_preference=["es-ES"], recognition_level="accurate").recognize()
    items = []
    for text, conf, (x, y, w, h) in results:  # Vision: normalizado, origen abajo-izquierda
        items.append({"text": text, "conf": float(conf), "bbox": [float(x), float(1 - y - h), float(w), float(h)]})
    return items


def dedupe(raw: list[dict], period: float, gap: float = 1.5, iou_min: float = 0.3) -> list[dict]:
    """Agrupa detecciones del mismo texto en frames consecutivos en 'apariciones'."""
    apps: list[dict] = []
    for frame in sorted(raw, key=lambda f: f["t"]):
        for it in frame["items"]:
            key = norm_text(it["text"])
            match = None
            for a in apps:
                if a["_key"] == key and frame["t"] - a["_last_t"] <= gap and iou(a["bbox"], it["bbox"]) >= iou_min:
                    match = a
                    break
            if match is None:
                apps.append({"text": it["text"], "_key": key, "_conf": it["conf"], "bbox": it["bbox"],
                             "t_start": frame["t"], "_last_t": frame["t"], "frame": frame["file"],
                             "frames": [frame["file"]]})
            else:
                match["_last_t"] = frame["t"]
                match["frames"].append(frame["file"])
                if it["conf"] > match["_conf"]:
                    match["text"], match["_conf"] = it["text"], it["conf"]
    out = []
    for a in apps:
        out.append({"text": a["text"], "bbox": a["bbox"], "t_start": a["t_start"],
                    "t_end": round(a["_last_t"] + period, 3), "frame": a["frame"], "frames": a["frames"]})
    return out


def ocr_frames(job: Job, frames: list[dict], period: float) -> dict:
    raw = [{"file": f["file"], "t": f["t"], "items": ocr_frame(job.path(f["file"]))} for f in frames]
    return {"raw": raw, "appearances": dedupe(raw, period=period)}
```

- [ ] **Step 4: Correr tests** → `6 passed` (los dos últimos usan Vision real; tardan unos segundos)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Apple Vision OCR stage with appearance dedupe"
```

---

### Task 10: Etapa de color de texto

**Files:**
- Create: `videoqa/stages/color.py`
- Test: `tests/unit/test_color_stage.py`

**Interfaces:**
- Produces: `dominant_text_color(img: PIL.Image, bbox: list[float]) -> str | None` (hex `#RRGGBB` mayúsculas) y `add_colors(job: Job, ocr: dict) -> dict` (mismo dict `ocr` con `color_hex` en cada aparición).

- [ ] **Step 1: Tests**

`tests/unit/test_color_stage.py`:
```python
from PIL import Image, ImageDraw
from videoqa.stages.color import dominant_text_color, add_colors

def synthetic(bg, fg):
    img = Image.new("RGB", (400, 200), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([120, 80, 280, 120], fill=fg)  # "texto" = barra central
    return img

def test_white_on_black():
    assert dominant_text_color(synthetic((0, 0, 0), (255, 255, 255)), [0.25, 0.35, 0.5, 0.3]) == "#FFFFFF"

def test_red_on_dark():
    assert dominant_text_color(synthetic((26, 26, 26), (255, 59, 48)), [0.25, 0.35, 0.5, 0.3]) == "#FF3B30"

def test_uniform_box_returns_none():
    assert dominant_text_color(Image.new("RGB", (100, 100), (10, 10, 10)), [0, 0, 1, 1]) is None

def test_add_colors_annotates_appearances(tmp_path):
    from videoqa.job import Job
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    synthetic((0, 0, 0), (245, 197, 24)).save(job.path("frames/a.jpg"), quality=95)
    ocr = {"raw": [], "appearances": [{"text": "x", "bbox": [0.25, 0.35, 0.5, 0.3], "t_start": 0, "t_end": 1,
                                        "frame": "frames/a.jpg", "frames": ["frames/a.jpg"]}]}
    out = add_colors(job, ocr)
    assert out["appearances"][0]["color_hex"].startswith("#F")
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/stages/color.py`**

```python
from __future__ import annotations

import numpy as np
from PIL import Image

from videoqa.job import Job

FG_DISTANCE = 60.0  # distancia RGB mínima al fondo para contar como trazo
MIN_FG_PIXELS = 10


def dominant_text_color(img: Image.Image, bbox: list[float]) -> str | None:
    W, H = img.size
    x, y, w, h = bbox
    box = (int(x * W), int(y * H), max(int(x * W) + 2, int((x + w) * W)), max(int(y * H) + 2, int((y + h) * H)))
    a = np.asarray(img.crop(box).convert("RGB")).astype(float)
    if a.size == 0:
        return None
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    px = a.reshape(-1, 3)
    fg = px[np.linalg.norm(px - bg, axis=1) > FG_DISTANCE]
    if len(fg) < MIN_FG_PIXELS:
        return None
    r, g, b = np.median(fg, axis=0).round().astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def add_colors(job: Job, ocr: dict) -> dict:
    cache: dict[str, Image.Image] = {}
    for app in ocr["appearances"]:
        img = cache.get(app["frame"])
        if img is None:
            img = cache[app["frame"]] = Image.open(job.path(app["frame"])).convert("RGB")
        app["color_hex"] = dominant_text_color(img, app["bbox"])
    return ocr
```

- [ ] **Step 4: Correr tests** → `4 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: dominant text color stage"
```

---

### Task 11: ΔE2000 y check de color de marca

**Files:**
- Create: `videoqa/checks/colors.py`, `videoqa/checks/brand_color.py`
- Test: `tests/unit/test_colors.py`, `tests/unit/test_brand_color.py`

**Interfaces:**
- Produces: `hex_to_rgb(hex) -> tuple[int,int,int]`, `rgb_to_lab(rgb) -> tuple[float,float,float]`, `delta_e2000(lab1, lab2) -> float`, `hex_delta_e(h1, h2) -> float`; `check_brand_colors(appearances: list[dict], brand: dict, rules: dict) -> list[Finding]`.

- [ ] **Step 1: Tests de color**

`tests/unit/test_colors.py`:
```python
from videoqa.checks.colors import delta_e2000, hex_delta_e, hex_to_rgb, rgb_to_lab

def test_hex_to_rgb():
    assert hex_to_rgb("#FF3B30") == (255, 59, 48)
    assert hex_to_rgb("ff3b30") == (255, 59, 48)

def test_rgb_to_lab_white_and_black():
    L, a, b = rgb_to_lab((255, 255, 255))
    assert abs(L - 100) < 0.01 and abs(a) < 0.01 and abs(b) < 0.01
    assert abs(rgb_to_lab((0, 0, 0))[0]) < 0.01

def test_delta_e2000_sharma_pair():
    # Par 1 de los datos de prueba de Sharma et al. (2005)
    assert abs(delta_e2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)) - 2.0425) < 0.001

def test_identical_is_zero_and_far_is_large():
    assert hex_delta_e("#FFFFFF", "#FFFFFF") == 0.0
    assert hex_delta_e("#FF3B30", "#FFFFFF") > 30
    assert hex_delta_e("#F5C518", "#F4C41A") < 3
```

- [ ] **Step 2: Implementar `videoqa/checks/colors.py`**

```python
from __future__ import annotations

import math


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e2000(lab1, lab2) -> float:
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hp(a, b):
        if a == 0 and b == 0:
            return 0.0
        h = math.degrees(math.atan2(b, a))
        return h + 360 if h < 0 else h

    h1p, h2p = hp(a1p, b1), hp(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))
    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    if C1p * C2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hbp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hbp = (h1p + h2p + 360) / 2
    else:
        hbp = (h1p + h2p - 360) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbp - 30)) + 0.24 * math.cos(math.radians(2 * hbp))
         + 0.32 * math.cos(math.radians(3 * hbp + 6)) - 0.20 * math.cos(math.radians(4 * hbp - 63)))
    dtheta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    RC = 2 * math.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    SL = 1 + (0.015 * (Lbp - 50) ** 2) / math.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -math.sin(math.radians(2 * dtheta)) * RC
    return math.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


def hex_delta_e(h1: str, h2: str) -> float:
    return delta_e2000(rgb_to_lab(hex_to_rgb(h1)), rgb_to_lab(hex_to_rgb(h2)))
```

- [ ] **Step 3: Correr `uv run pytest tests/unit/test_colors.py -q`** → `4 passed`

- [ ] **Step 4: Tests del check de marca**

`tests/unit/test_brand_color.py`:
```python
from videoqa.checks.brand_color import check_brand_colors
from videoqa.config import load_rules

BRAND = {"palette": [{"name": "Negro", "hex": "#1A1A1A"}, {"name": "Blanco", "hex": "#FFFFFF"},
                     {"name": "Amarillo", "hex": "#F5C518"}]}

def app(text, color, t=2.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + 3,
            "frame": "frames/sec_0005.jpg", "frames": [], "color_hex": color}

def test_off_palette_color_is_blocker():
    fs = check_brand_colors([app("Aprobecha", "#FF3B30")], BRAND, load_rules())
    assert len(fs) == 1
    f = fs[0]
    assert f.severity == "blocker" and f.type == "marca" and f.check == "brand_color"
    assert "#FF3B30" in f.title and "#F5C518" in f.detail
    assert f.frame == "frames/sec_0005.jpg" and f.bbox == [0.1, 0.4, 0.8, 0.1] and f.t_start == 2.0

def test_near_palette_color_passes():
    assert check_brand_colors([app("Oferta", "#F4C41A")], BRAND, load_rules()) == []

def test_missing_color_or_palette_is_skipped():
    assert check_brand_colors([app("x", None)], BRAND, load_rules()) == []
    assert check_brand_colors([app("x", "#FF0000")], {"palette": []}, load_rules()) == []
```

- [ ] **Step 5: Implementar `videoqa/checks/brand_color.py`**

```python
from __future__ import annotations

from videoqa.checks.colors import hex_delta_e
from videoqa.findings import Finding


def check_brand_colors(appearances: list[dict], brand: dict, rules: dict) -> list[Finding]:
    palette = [p["hex"].upper() for p in brand.get("palette", []) if p.get("hex")]
    if not palette:
        return []
    tol = float(rules["thresholds"]["color_delta_e"])
    sev = rules["severities"]["brand_color"]
    out = []
    for i, a in enumerate(appearances):
        color = a.get("color_hex")
        if not color:
            continue
        nearest = min(palette, key=lambda p: hex_delta_e(color, p))
        de = hex_delta_e(color, nearest)
        if de <= tol:
            continue
        out.append(Finding(
            id=f"color-{i}", type="marca", severity=sev, t_start=a["t_start"], t_end=a["t_end"],
            title=f"Color de texto fuera de marca: {color}",
            detail=(f'El texto "{a["text"]}" usa {color}. Paleta permitida: {", ".join(palette)} '
                    f"(ΔE mínimo {de:.1f} respecto a {nearest})."),
            suggestion=f"Cambiar a {nearest} o a otro color de la paleta.",
            frame=a.get("frame"), bbox=a.get("bbox"), source="code", check="brand_color"))
    return out
```

- [ ] **Step 6: Correr `uv run pytest -q`** → todo verde

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: CIEDE2000 and brand color check"
```

---

### Task 12: Check de ortografía y puntuación

**Files:**
- Create: `videoqa/checks/spelling.py`
- Test: `tests/unit/test_spelling.py`

**Interfaces:**
- Produces: `load_glossary(path: Path) -> set[str]` (minúsculas; archivo inexistente → set vacío), `unknown_words(text: str, checker, glossary: set[str]) -> list[str]`, `check_spelling(appearances, glossary, rules, checker=None) -> list[Finding]`.

- [ ] **Step 1: Tests**

`tests/unit/test_spelling.py`:
```python
from spellchecker import SpellChecker
from videoqa.checks.spelling import check_spelling, load_glossary, unknown_words
from videoqa.config import load_rules

CHECKER = SpellChecker(language="es")

def app(text, t=1.0):
    return {"text": text, "bbox": [0.1, 0.4, 0.8, 0.1], "t_start": t, "t_end": t + 2,
            "frame": "frames/sec_0003.jpg", "frames": []}

def test_load_glossary_missing_file(tmp_path):
    assert load_glossary(tmp_path / "no.txt") == set()

def test_load_glossary_lowercases(tmp_path):
    p = tmp_path / "g.txt"; p.write_text("VideoQA\n# comentario\n\nTikTok\n")
    assert load_glossary(p) == {"videoqa", "tiktok"}

def test_unknown_words_respects_glossary_caps_and_short():
    assert unknown_words("Aprobecha la oferta en TikTok", CHECKER, {"tiktok"}) == ["Aprobecha"]
    assert unknown_words("IVA de 21", CHECKER, set()) == []          # siglas y números
    assert unknown_words("Aprovecha la oferta", CHECKER, set()) == []

def test_check_spelling_blocker_with_suggestion():
    fs = check_spelling([app("Aprobecha la oferta")], set(), load_rules(), checker=CHECKER)
    assert len(fs) == 1 and fs[0].severity == "blocker" and fs[0].type == "ortografia"
    assert "Aprobecha" in fs[0].title and "aprovecha" in fs[0].suggestion.lower()
    assert fs[0].check == "spelling_unknown_word"

def test_punctuation_warnings():
    fs = check_spelling([app("Quieres ahorrar?"), app("Hola  mundo")], set(), load_rules(), checker=CHECKER)
    checks = sorted(f.check for f in fs)
    assert checks == ["spelling_punctuation", "spelling_punctuation"]
    assert all(f.severity == "warning" for f in fs)
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/checks/spelling.py`**

```python
from __future__ import annotations

import re
from pathlib import Path

from videoqa.findings import Finding

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


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
    out = []
    for w in WORD_RE.findall(text):
        if len(w) < 3 or w.isupper() or w.lower() in glossary:
            continue
        if checker.unknown([w.lower()]):
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
    return issues


def check_spelling(appearances: list[dict], glossary: set[str], rules: dict, checker=None) -> list[Finding]:
    if checker is None:
        from spellchecker import SpellChecker

        checker = SpellChecker(language="es")
    sev = rules["severities"]
    out = []
    for i, a in enumerate(appearances):
        text = a["text"]
        bad = unknown_words(text, checker, glossary)
        if bad:
            fixes = ", ".join(f"{w} → {checker.correction(w.lower()) or '?'}" for w in bad)
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
```

- [ ] **Step 4: Correr tests** → `5 passed`. Si `pyspellchecker` marca "Aprovecha" como desconocida, añadirla a un `tests/fixtures/glosario.txt` NO es la solución: revisar que el idioma sea `"es"` y la versión ≥ 0.8.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: spelling and punctuation check"
```

---

### Task 13: Checks de tiempo (texto corto, zona tapada, desincronía)

**Files:**
- Create: `videoqa/checks/timing.py`
- Test: `tests/unit/test_timing.py`

**Interfaces:**
- Produces: `check_visible_short(appearances, rules)`, `check_occluded(appearances, rules)`, `check_desync(appearances, segments: list[dict], rules)`, `check_timing(appearances, segments, rules) -> list[Finding]` (los tres juntos), `best_segment(text, segments) -> tuple[dict | None, float]`.

- [ ] **Step 1: Tests**

`tests/unit/test_timing.py`:
```python
from videoqa.checks.timing import best_segment, check_desync, check_occluded, check_timing, check_visible_short
from videoqa.config import load_rules

R = load_rules()

def app(text="Oferta de verano", t0=1.0, t1=3.0, bbox=(0.1, 0.4, 0.8, 0.1)):
    return {"text": text, "bbox": list(bbox), "t_start": t0, "t_end": t1, "frame": "frames/a.jpg", "frames": []}

def test_visible_short():
    fs = check_visible_short([app(t0=1.0, t1=1.5), app(t0=2.0, t1=3.0)], R)
    assert len(fs) == 1 and fs[0].check == "text_visible_short" and fs[0].severity == "warning"

def test_occluded_bottom_and_right():
    fs = check_occluded([app(bbox=(0.1, 0.85, 0.5, 0.1)), app(bbox=(0.8, 0.4, 0.15, 0.1)), app()], R)
    assert len(fs) == 2 and all(f.check == "text_occluded" for f in fs)

def test_best_segment_jaccard():
    segs = [{"start": 0.0, "end": 2.0, "text": "Hola a todos"}, {"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    seg, score = best_segment("Oferta de verano", segs)
    assert seg is segs[1] and score >= 0.5
    assert best_segment("xyz", segs)[1] == 0.0

def test_desync_flags_only_matching_late_text():
    segs = [{"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    fs = check_desync([app(t0=4.0), app(text="Precio", t0=9.0)], segs, R)
    assert len(fs) == 1 and fs[0].check == "subtitle_desync" and "2.0" in fs[0].detail

def test_check_timing_combines():
    segs = [{"start": 2.0, "end": 5.0, "text": "aprovecha la oferta de verano"}]
    fs = check_timing([app(t0=4.0, t1=4.5, bbox=(0.1, 0.9, 0.5, 0.1))], segs, R)
    assert sorted(f.check for f in fs) == ["subtitle_desync", "text_occluded", "text_visible_short"]
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/checks/timing.py`**

```python
from __future__ import annotations

import re

from videoqa.findings import Finding

_TOKEN = re.compile(r"[a-záéíóúüñ0-9]+")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(s.lower()))


def best_segment(text: str, segments: list[dict]) -> tuple[dict | None, float]:
    t = _tokens(text)
    best, score = None, 0.0
    for seg in segments:
        s = _tokens(seg["text"])
        if not t or not s:
            continue
        j = len(t & s) / len(t | s)
        if j > score:
            best, score = seg, j
    return best, score


def _base(i: str, a: dict, typ: str, sev: str, title: str, detail: str, suggestion: str, check: str) -> Finding:
    return Finding(id=i, type=typ, severity=sev, t_start=a["t_start"], t_end=a["t_end"], title=title,
                   detail=detail, suggestion=suggestion, frame=a.get("frame"), bbox=a.get("bbox"),
                   source="code", check=check)


def check_visible_short(appearances: list[dict], rules: dict) -> list[Finding]:
    min_s = float(rules["thresholds"]["min_text_visible_s"])
    sev = rules["severities"]["text_visible_short"]
    out = []
    for i, a in enumerate(appearances):
        dur = a["t_end"] - a["t_start"]
        if dur < min_s:
            out.append(_base(f"short-{i}", a, "tecnico", sev, f"Texto visible solo {dur:.1f} s",
                             f'"{a["text"]}" aparece menos de {min_s:.1f} s; puede ser ilegible.',
                             "Mantener el texto en pantalla al menos 1 s.", "text_visible_short"))
    return out


def check_occluded(appearances: list[dict], rules: dict) -> list[Finding]:
    th = rules["thresholds"]
    sev = rules["severities"]["text_occluded"]
    out = []
    for i, a in enumerate(appearances):
        x, y, w, h = a["bbox"]
        reasons = []
        if y + h > float(th["occluded_bottom"]):
            reasons.append("banda inferior (caption/botones)")
        if x + w > float(th["occluded_right"]):
            reasons.append("franja derecha (iconos de like/comentar)")
        if reasons:
            out.append(_base(f"occl-{i}", a, "tecnico", sev, "Texto en zona tapada por la UI de TikTok/Reels",
                             f'"{a["text"]}" cae en: {"; ".join(reasons)}.',
                             "Mover el texto hacia el centro/zona segura.", "text_occluded"))
    return out


def check_desync(appearances: list[dict], segments: list[dict], rules: dict) -> list[Finding]:
    max_s = float(rules["thresholds"]["desync_s"])
    sev = rules["severities"]["subtitle_desync"]
    out = []
    for i, a in enumerate(appearances):
        seg, score = best_segment(a["text"], segments)
        if seg is None or score < 0.5:
            continue
        diff = a["t_start"] - seg["start"]
        if abs(diff) > max_s:
            out.append(_base(f"desync-{i}", a, "inconsistencia", sev, f"Subtítulo desincronizado {abs(diff):.1f} s",
                             f'"{a["text"]}" aparece en {a["t_start"]:.1f} s pero se dice en {seg["start"]:.1f} s '
                             f'("{seg["text"]}").', "Alinear el texto con el audio.", "subtitle_desync"))
    return out


def check_timing(appearances: list[dict], segments: list[dict], rules: dict) -> list[Finding]:
    return check_visible_short(appearances, rules) + check_occluded(appearances, rules) + check_desync(appearances, segments, rules)
```

- [ ] **Step 4: Correr tests** → `5 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: timing checks (short text, occluded zone, desync)"
```

---

### Task 14: Checks técnicos (negro, congelado, silencio, clipping, aspecto, sin audio)

**Files:**
- Create: `videoqa/checks/technical.py`
- Test: `tests/unit/test_technical_check.py`

**Interfaces:**
- Produces: `check_technical(probe: dict, technical: dict, rules: dict) -> list[Finding]`.

- [ ] **Step 1: Tests**

`tests/unit/test_technical_check.py`:
```python
from videoqa.checks.technical import check_technical
from videoqa.config import load_rules

R = load_rules()
PROBE = {"duration": 12.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}
EMPTY = {"black": [], "freeze": [], "scene_cuts": [], "silence": [], "audio": {"peak_db": -3.0, "peak_count": 0}}

def test_clean_has_no_findings():
    assert check_technical(PROBE, EMPTY, R) == []

def test_black_in_middle_is_blocker_but_edges_ignored():
    t = dict(EMPTY, black=[{"start": 5.0, "end": 6.0}, {"start": 0.0, "end": 0.3}, {"start": 11.7, "end": 12.0}])
    fs = check_technical(PROBE, t, R)
    assert [f.check for f in fs] == ["black_frame"] and fs[0].severity == "blocker" and fs[0].t_start == 5.0

def test_freeze_overlapping_black_is_deduped():
    t = dict(EMPTY, black=[{"start": 5.0, "end": 6.0}], freeze=[{"start": 5.0, "end": 6.0}, {"start": 8.0, "end": 9.0}])
    assert sorted(f.check for f in check_technical(PROBE, t, R)) == ["black_frame", "frozen_frame"]

def test_silence_clipping_aspect_no_audio():
    t = dict(EMPTY, silence=[{"start": 3.0, "end": 6.0}], audio={"peak_db": 0.0, "peak_count": 500})
    p = dict(PROBE, width=1920, height=1080, has_audio=False)
    checks = sorted(f.check for f in check_technical(p, t, R))
    assert checks == ["aspect_ratio", "audio_clipping", "no_audio", "silence"]
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/checks/technical.py`**

```python
from __future__ import annotations

from videoqa.findings import Finding


def _overlaps(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def _inside(iv: dict, duration: float, margin: float) -> bool:
    return iv["start"] >= margin and iv["end"] <= duration - margin


def check_technical(probe: dict, technical: dict, rules: dict) -> list[Finding]:
    th, sev = rules["thresholds"], rules["severities"]
    dur, margin = float(probe["duration"]), float(th["edge_margin_s"])
    out: list[Finding] = []

    blacks = [b for b in technical.get("black", []) if b["end"] - b["start"] >= float(th["black_min_s"]) and _inside(b, dur, margin)]
    for i, b in enumerate(blacks):
        out.append(Finding(id=f"black-{i}", type="tecnico", severity=sev["black_frame"], t_start=b["start"], t_end=b["end"],
                           title=f"Pantalla negra de {b['end'] - b['start']:.1f} s", detail="El video queda en negro en medio del contenido.",
                           suggestion="Revisar el corte o la transición en ese punto.", source="code", check="black_frame"))

    for i, f in enumerate(technical.get("freeze", [])):
        if f["end"] - f["start"] < float(th["freeze_min_s"]) or not _inside(f, dur, margin):
            continue
        if any(_overlaps(f, b) for b in blacks):
            continue
        out.append(Finding(id=f"freeze-{i}", type="tecnico", severity=sev["frozen_frame"], t_start=f["start"], t_end=f["end"],
                           title=f"Imagen congelada {f['end'] - f['start']:.1f} s", detail="No hay cambio de imagen durante ese intervalo.",
                           suggestion="Verificar si es un frame duplicado o un clip mal exportado.", source="code", check="frozen_frame"))

    for i, s in enumerate(technical.get("silence", [])):
        if s["end"] - s["start"] >= float(th["silence_min_s"]) and _inside(s, dur, margin):
            out.append(Finding(id=f"silence-{i}", type="tecnico", severity=sev["silence"], t_start=s["start"], t_end=s["end"],
                               title=f"Silencio de {s['end'] - s['start']:.1f} s", detail="Hueco de audio en medio del video.",
                               suggestion="Recortar el hueco o añadir música/ambiente.", source="code", check="silence"))

    audio = technical.get("audio")
    if audio and audio["peak_db"] >= float(th["clipping_peak_db"]) and audio["peak_count"] > int(th["clipping_min_count"]):
        out.append(Finding(id="clip-0", type="tecnico", severity=sev["audio_clipping"], t_start=0.0, t_end=dur,
                           title="Audio saturado (clipping)", detail=f"Pico {audio['peak_db']:.2f} dB con {audio['peak_count']} muestras al límite.",
                           suggestion="Bajar la ganancia de la voz/música.", source="code", check="audio_clipping"))

    if probe["height"] and abs(probe["width"] / probe["height"] - 9 / 16) > float(th["aspect_tolerance"]):
        out.append(Finding(id="aspect-0", type="tecnico", severity=sev["aspect_ratio"], t_start=0.0, t_end=dur,
                           title=f"Relación de aspecto {probe['width']}×{probe['height']} no es 9:16",
                           detail="Reels/TikTok esperan vertical 9:16.", suggestion="Exportar en 1080×1920.", source="code", check="aspect_ratio"))

    if not probe["has_audio"]:
        out.append(Finding(id="noaudio-0", type="tecnico", severity=sev["no_audio"], t_start=0.0, t_end=dur,
                           title="El video no tiene pista de audio", detail="No se pudo transcribir; los checks de guion no aplican.",
                           suggestion="Confirmar si es intencional.", source="code", check="no_audio"))
    return out
```

- [ ] **Step 4: Correr tests** → `4 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: technical checks"
```

---

### Task 15: Runner de Claude Code

**Files:**
- Create: `videoqa/claude_runner.py`
- Test: `tests/unit/test_claude_runner.py`

**Interfaces:**
- Produces: `class ClaudeError(Exception)`, `run_claude(prompt: str, cwd: Path, claude_bin: str = "claude", timeout: int = 600, allowed_tools: tuple[str, ...] = ("Read",)) -> str` (devuelve el campo `result` del JSON de `claude -p --output-format json`), `extract_json(text: str) -> dict` (tolera fences ```json y texto alrededor).
- Tipo `Runner = Callable[[str, Path], str]` — el resto del código recibe un runner para poder inyectar stubs en tests.

- [ ] **Step 1: Tests**

`tests/unit/test_claude_runner.py`:
```python
import json
import subprocess
from pathlib import Path
import pytest
from videoqa.claude_runner import ClaudeError, extract_json, run_claude

def test_extract_json_plain_and_fenced():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Aquí va:\n```json\n{"a": [1, 2]}\n```\ngracias') == {"a": [1, 2]}

def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        extract_json("sin json")

def test_run_claude_parses_result(monkeypatch, tmp_path):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"], captured["input"], captured["cwd"] = cmd, kw["input"], kw["cwd"]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"is_error": False, "result": "hola"}), stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_claude("prompt", cwd=tmp_path, claude_bin="claude-x") == "hola"
    assert captured["cmd"][:4] == ["claude-x", "-p", "--output-format", "json"]
    assert "--allowedTools" in captured["cmd"] and captured["input"] == "prompt" and captured["cwd"] == tmp_path

def test_run_claude_nonzero_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom"))
    with pytest.raises(ClaudeError):
        run_claude("p", cwd=tmp_path)

def test_run_claude_is_error_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, stdout=json.dumps({"is_error": True, "result": "rate limit"}), stderr=""))
    with pytest.raises(ClaudeError):
        run_claude("p", cwd=tmp_path)
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/claude_runner.py`**

```python
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

Runner = Callable[[str, Path], str]

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class ClaudeError(Exception):
    """claude -p falló o devolvió error."""


def run_claude(prompt: str, cwd: Path, claude_bin: str = "claude", timeout: int = 600,
               allowed_tools: tuple[str, ...] = ("Read",)) -> str:
    cmd = [claude_bin, "-p", "--output-format", "json", "--allowedTools", ",".join(allowed_tools)]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"claude -p superó {timeout}s") from e
    if proc.returncode != 0:
        raise ClaudeError(f"claude -p salió con {proc.returncode}: {proc.stderr[-2000:]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"salida no JSON: {proc.stdout[:500]}") from e
    if data.get("is_error"):
        raise ClaudeError(str(data.get("result")))
    return str(data.get("result", ""))


def extract_json(text: str) -> dict:
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    if not candidate:
        raise ValueError("no se encontró JSON en la respuesta")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}") from e
```

- [ ] **Step 4: Correr tests** → `5 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: claude -p runner with JSON extraction"
```

---

### Task 16: `brand.json` desde la guía de marca PDF

**Files:**
- Create: `videoqa/brand.py`
- Test: `tests/unit/test_brand.py`

**Interfaces:**
- Produces: `EMPTY_BRAND` dict, `brand_is_stale(config_dir: Path) -> bool`, `build_brand(config_dir: Path, runner: Runner) -> dict`, `load_brand(config_dir: Path, runner: Runner) -> dict`. Archivos: `config_dir/guia_de_marca.pdf` (entrada), `config_dir/brand.json` (salida).
- Regla de regeneración: se regenera si no existe `brand.json`, o si `source_pdf_sha256` ≠ sha del PDF **y** el mtime del PDF es más reciente que el de `brand.json` (así una edición manual posterior no se pisa).

- [ ] **Step 1: Tests**

`tests/unit/test_brand.py`:
```python
import json, os, time
from pathlib import Path
from videoqa.brand import EMPTY_BRAND, brand_is_stale, build_brand, load_brand

RESP = '```json\n{"palette":[{"name":"Rojo","hex":"#ff0000"}],"fonts":["Inter"],"rules":["x"],"logo_required":true}\n```'

def runner_ok(prompt, cwd):
    assert "guia_de_marca.pdf" in prompt
    return RESP

def test_load_brand_without_pdf_returns_empty(tmp_path):
    assert load_brand(tmp_path, runner_ok) == EMPTY_BRAND

def test_build_brand_writes_json_with_sha_and_upper_hex(tmp_path):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    b = build_brand(tmp_path, runner_ok)
    assert b["palette"][0]["hex"] == "#FF0000" and b["logo_required"] is True
    saved = json.loads((tmp_path / "brand.json").read_text())
    assert len(saved["source_pdf_sha256"]) == 64

def test_load_brand_uses_cache_when_fresh(tmp_path):
    (tmp_path / "guia_de_marca.pdf").write_bytes(b"%PDF fake")
    build_brand(tmp_path, runner_ok)
    calls = []
    def runner_count(prompt, cwd):
        calls.append(1); return RESP
    load_brand(tmp_path, runner_count)
    assert calls == []
    assert brand_is_stale(tmp_path) is False

def test_manual_edit_after_pdf_change_is_kept(tmp_path):
    pdf = tmp_path / "guia_de_marca.pdf"; pdf.write_bytes(b"%PDF v1")
    build_brand(tmp_path, runner_ok)
    pdf.write_bytes(b"%PDF v2")
    old = time.time() - 100
    os.utime(pdf, (old, old))            # el PDF cambió pero brand.json es más reciente
    assert brand_is_stale(tmp_path) is False

def test_pdf_newer_than_brand_triggers_rebuild(tmp_path):
    pdf = tmp_path / "guia_de_marca.pdf"; pdf.write_bytes(b"%PDF v1")
    build_brand(tmp_path, runner_ok)
    old = time.time() - 100
    os.utime(tmp_path / "brand.json", (old, old))
    pdf.write_bytes(b"%PDF v2")
    assert brand_is_stale(tmp_path) is True
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/brand.py`**

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from videoqa.claude_runner import Runner, extract_json

PDF_NAME = "guia_de_marca.pdf"
BRAND_NAME = "brand.json"

EMPTY_BRAND = {"palette": [], "fonts": [], "rules": [], "logo_required": False, "source_pdf_sha256": ""}

BRAND_PROMPT = f"""Eres un diseñador de marca. Lee el archivo `{PDF_NAME}` que está en este directorio
(usa la herramienta Read) y extrae la identidad visual para revisión de videos.

Responde ÚNICAMENTE con un JSON válido con este esquema exacto, sin texto adicional:
{{
  "palette": [{{"name": "<nombre>", "hex": "#RRGGBB"}}],
  "fonts": ["<nombre de fuente>"],
  "rules": ["<regla escrita de uso, una frase cada una, en español>"],
  "logo_required": true | false
}}

Instrucciones:
- Incluye en "palette" TODOS los colores que la guía permita para texto o fondos, en hex de 6 dígitos.
- En "rules" copia reglas explícitas sobre color de texto, tipografía, tamaños, posición del logo,
  palabras prohibidas o tono. Si la guía no dice nada, deja la lista vacía.
- "logo_required" es true solo si la guía exige el logo en cada pieza de video.
"""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def brand_is_stale(config_dir: Path) -> bool:
    pdf, brand = config_dir / PDF_NAME, config_dir / BRAND_NAME
    if not pdf.exists():
        return False
    if not brand.exists():
        return True
    try:
        saved = json.loads(brand.read_text()).get("source_pdf_sha256", "")
    except json.JSONDecodeError:
        return True
    if saved == _sha(pdf):
        return False
    return pdf.stat().st_mtime > brand.stat().st_mtime


def build_brand(config_dir: Path, runner: Runner) -> dict:
    pdf = config_dir / PDF_NAME
    data = extract_json(runner(BRAND_PROMPT, config_dir))
    brand = dict(EMPTY_BRAND)
    brand["palette"] = [{"name": str(p.get("name", "")), "hex": str(p["hex"]).upper()} for p in data.get("palette", []) if p.get("hex")]
    brand["fonts"] = [str(f) for f in data.get("fonts", [])]
    brand["rules"] = [str(r) for r in data.get("rules", [])]
    brand["logo_required"] = bool(data.get("logo_required", False))
    brand["source_pdf_sha256"] = _sha(pdf)
    (config_dir / BRAND_NAME).write_text(json.dumps(brand, ensure_ascii=False, indent=2))
    return brand


def load_brand(config_dir: Path, runner: Runner) -> dict:
    pdf, brand = config_dir / PDF_NAME, config_dir / BRAND_NAME
    if brand_is_stale(config_dir):
        return build_brand(config_dir, runner)
    if brand.exists():
        return json.loads(brand.read_text())
    return dict(EMPTY_BRAND)
```

- [ ] **Step 4: Correr tests** → `5 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: brand.json extraction from PDF via claude"
```

---

### Task 17: Skill del revisor y juez

**Files:**
- Create: `.claude/skills/revisor-video/SKILL.md`, `videoqa/judge.py`
- Test: `tests/unit/test_judge.py`

**Interfaces:**
- Produces:
  - `class JudgeError(Exception)`.
  - `select_frames(frames: list[dict], appearances: list[dict], code_findings: list[Finding], max_frames: int) -> list[str]` (rutas relativas, orden por tiempo).
  - `prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules) -> dict` — escribe `judge_input/*.json`, `judge_input/glosario.txt`, `claude_frames/NN_<t>.jpg` (redimensionados a `claude.frame_height`), devuelve manifest `{"frames": [...], "inputs": [...]}`.
  - `build_prompt(skill_text: str, manifest: dict, duration: float) -> str`.
  - `parse_verdict(text: str) -> dict` — valida `findings` (lista; cada uno con `type` ∈ TYPES, `severity` ∈ SEVERITIES, `t_start`, `t_end` numéricos, `title`, `detail`), `confirmed_code_findings` (lista de ids), `dismissed_code_findings` (lista de `{id, reason}`), `guion_real_md` (str). Lanza `ValueError`.
  - `run_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules, runner: Runner, skill_path: Path = SKILL_PATH) -> dict` → `{"findings": [Finding(source="claude")], "dismissed": [{"id","reason"}], "guion_real_md": str}`; 2 intentos; escribe `findings_claude.json` y `guion_real.md` en el job dir.

- [ ] **Step 1: Escribir `.claude/skills/revisor-video/SKILL.md`**

```markdown
---
name: revisor-video
description: Revisor de calidad pre-publicación para reels/TikToks. Detecta ortografía, marca, inconsistencias guion↔pantalla y bloopers a partir de transcripción, OCR y frames. Devuelve JSON.
---

# Rol

Eres la revisora senior de un equipo de video para redes sociales (Meta, TikTok). Tu trabajo es
encontrar TODO lo que impediría publicar un video, con la precisión de un pipeline de CI: cada
hallazgo debe ser concreto, ubicado en el tiempo y accionable para un editor junior.

Trabajas en español. Sé exigente pero justa: no inventes errores. Si dudas, usa `warning` y
explica por qué.

# Entradas (en el directorio actual)

- `judge_input/brand.json` — paleta (hex), fuentes y reglas escritas de la marca.
- `judge_input/glosario.txt` — palabras válidas aunque no estén en el diccionario.
- `judge_input/transcript.json` — lo que DICE el talento, con `segments[{start,end,text}]`.
- `judge_input/ocr.json` — textos EN PANTALLA: `appearances[{text,bbox,t_start,t_end,color_hex,frame}]`.
- `judge_input/technical.json` — negros, congelados, cortes de escena, silencios, audio.
- `judge_input/findings_code.json` — hallazgos ya detectados por código. Debes CONFIRMAR o
  DESCARTAR cada uno por su `id` (descarta solo con razón clara: nombre propio, jerga válida,
  falso positivo del OCR, etc.).
- `claude_frames/*.jpg` — frames clave; el nombre incluye el segundo (`03_0012.5s.jpg` = 12.5 s).
  Míralos TODOS con Read.

# Qué revisar

1. **Ortografía y tildes en pantalla** (usa contexto: "esta"/"está", "mas"/"más", "si"/"sí").
   Un nombre propio escrito de dos formas distintas en el mismo video es blocker.
2. **Marca**: violaciones a `rules`; logo ausente si `logo_required`; fuente visiblemente distinta.
   El color exacto ya lo revisa el código — no repitas hallazgos de `findings_code.json`, confírmalos.
3. **Inconsistencias guion ↔ pantalla**: cifras, precios, fechas, nombres, porcentajes que
   difieren entre lo dicho y lo escrito → blocker. Subtítulo que cambia palabras (no solo
   resume) → blocker. Un resumen fiel NO es error.
4. **Bloopers en el audio**: "otra vez", "corte", "espera", risas fuera de guion, frase repetida
   idéntica dos veces seguidas, tartamudeo largo, silencio incómodo con "eh…" → blocker.
5. **Bloopers visuales en frames**: marca de agua de stock, cursor, ventana del editor, barra de
   progreso, pantalla del teléfono con notificaciones, texto cortado por el borde → blocker.
6. **Tono/claridad**: si el mensaje principal no se entiende → warning con explicación.

# Guion real

Genera `guion_real_md`: la transcripción limpia (sin muletillas "eh", "este", repeticiones),
puntuada y con tildes, dividida por escena usando `technical.scene_cuts`, cada bloque con su
timestamp `[m:ss]`. Debe reflejar lo que el talento realmente dijo, no el guion original.

# Salida

Responde ÚNICAMENTE con un JSON válido (sin texto antes ni después):

```json
{
  "findings": [
    {
      "type": "ortografia | marca | inconsistencia | blooper | tecnico",
      "severity": "blocker | warning | info",
      "t_start": 12.0,
      "t_end": 12.8,
      "title": "Frase corta y concreta",
      "detail": "Qué está mal y cómo lo sabes (cita el texto o lo dicho).",
      "suggestion": "Qué debe hacer el editor.",
      "frame": "claude_frames/03_0012.5s.jpg"
    }
  ],
  "confirmed_code_findings": ["spell-0", "color-2"],
  "dismissed_code_findings": [{"id": "spell-3", "reason": "Es el nombre de la marca del cliente"}],
  "guion_real_md": "## Escena 1 [0:00]\n..."
}
```

Reglas del JSON: `t_start`/`t_end` en segundos (float); `frame` solo si un frame lo evidencia,
si no `null`; no repitas hallazgos que ya están en `findings_code.json`.

# Ejemplos de buenos hallazgos

- `{"type":"inconsistencia","severity":"blocker","t_start":41.0,"t_end":43.5,"title":"Descuento distinto en pantalla y audio","detail":"En pantalla dice \"20% de descuento\" (ocr t=41.0) pero el talento dice \"veinticinco por ciento\" (transcript 41.2–43.1).","suggestion":"Corregir el rótulo a 25% o regrabar la frase.","frame":"claude_frames/09_0041.0s.jpg"}`
- `{"type":"blooper","severity":"blocker","t_start":18.4,"t_end":21.0,"title":"Toma fallida sin cortar","detail":"El talento dice \"…y por eso— no, otra vez\" y repite la frase.","suggestion":"Cortar de 18.4 a 21.0.","frame":null}`
```

- [ ] **Step 2: Tests del juez**

`tests/unit/test_judge.py`:
```python
import json
from pathlib import Path
import pytest
from PIL import Image
from videoqa.claude_runner import ClaudeError
from videoqa.config import load_rules
from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.judge import JudgeError, build_prompt, parse_verdict, prepare_inputs, run_judge, select_frames

R = load_rules()
SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "revisor-video" / "SKILL.md"

GOOD = json.dumps({
    "findings": [{"type": "blooper", "severity": "blocker", "t_start": 3.0, "t_end": 4.0,
                  "title": "Toma fallida", "detail": "dice otra vez", "suggestion": "cortar", "frame": None}],
    "confirmed_code_findings": ["spell-0"],
    "dismissed_code_findings": [{"id": "spell-1", "reason": "nombre propio"}],
    "guion_real_md": "## Escena 1 [0:00]\nHola",
})

def frames_list(n=24, period=0.5):
    fr = [{"file": f"frames/sec_{i+1:04d}.jpg", "t": i * period, "kind": "second"} for i in range(n)]
    fr.append({"file": "frames/scene_001.jpg", "t": 5.1, "kind": "scene"})
    return sorted(fr, key=lambda f: f["t"])

def make_job(tmp_path, n=24):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    for f in frames_list(n):
        Image.new("RGB", (108, 192), (20, 20, 20)).save(job.path(f["file"]))
    return job

def test_select_frames_prioritizes_scene_text_and_findings():
    frames = frames_list()
    apps = [{"text": "x", "frame": "frames/sec_0003.jpg", "bbox": [0, 0, 1, 1], "t_start": 1.0, "t_end": 2.0, "frames": []}]
    fnd = [Finding(id="a", type="marca", severity="blocker", t_start=8, t_end=9, title="t", detail="d", frame="frames/sec_0017.jpg")]
    sel = select_frames(frames, apps, fnd, max_frames=6)
    assert len(sel) == 6
    assert {"frames/scene_001.jpg", "frames/sec_0003.jpg", "frames/sec_0017.jpg"} <= set(sel)
    ts = [next(f["t"] for f in frames if f["file"] == s) for s in sel]
    assert ts == sorted(ts)

def test_select_frames_respects_cap_and_dedupes():
    frames = frames_list()
    assert len(select_frames(frames, [], [], max_frames=3)) == 3
    assert len(set(select_frames(frames, [], [], max_frames=100))) == len(frames)

def test_prepare_inputs_writes_files_and_resizes(tmp_path):
    job = make_job(tmp_path)
    m = prepare_inputs(job, {"palette": []}, "TikTok\n", {"segments": []}, {"appearances": []},
                       {"scene_cuts": []}, [], frames_list(), R)
    assert (job.dir / "judge_input" / "brand.json").exists()
    assert (job.dir / "judge_input" / "glosario.txt").read_text() == "TikTok\n"
    assert len(m["frames"]) <= R["claude"]["max_frames"]
    img = Image.open(job.path(m["frames"][0]["file"]))
    assert img.size[1] <= R["claude"]["frame_height"]
    assert m["frames"][0]["file"].startswith("claude_frames/") and "s.jpg" in m["frames"][0]["file"]

def test_build_prompt_includes_skill_and_manifest():
    p = build_prompt("# Rol\nrevisor", {"frames": [{"file": "claude_frames/00_0000.0s.jpg", "t": 0.0}], "inputs": ["judge_input/brand.json"]}, 12.0)
    assert "# Rol" in p and "claude_frames/00_0000.0s.jpg" in p and "12.0" in p

def test_parse_verdict_valid():
    v = parse_verdict(GOOD)
    assert v["findings"][0]["severity"] == "blocker" and v["dismissed_code_findings"][0]["id"] == "spell-1"

@pytest.mark.parametrize("bad", [
    '{"findings": "no"}',
    '{"findings": [{"type": "x", "severity": "blocker", "t_start": 0, "t_end": 1, "title": "t", "detail": "d"}], "guion_real_md": ""}',
    '{"findings": [{"type": "marca", "severity": "grave", "t_start": 0, "t_end": 1, "title": "t", "detail": "d"}], "guion_real_md": ""}',
    '{"findings": [], "guion_real_md": 5}',
])
def test_parse_verdict_invalid(bad):
    with pytest.raises(ValueError):
        parse_verdict(bad)

def test_run_judge_happy_path(tmp_path):
    job = make_job(tmp_path)
    calls = []
    def runner(prompt, cwd):
        calls.append(cwd); return GOOD
    out = run_judge(job, {"palette": []}, "", {"segments": []}, {"appearances": []}, {"scene_cuts": []},
                    [], frames_list(), R, runner=runner, skill_path=SKILL)
    assert calls == [job.dir]
    assert out["findings"][0].source == "claude" and out["findings"][0].id == "claude-0"
    assert out["dismissed"] == [{"id": "spell-1", "reason": "nombre propio"}]
    assert job.path("guion_real.md").read_text().startswith("## Escena 1")
    assert job.path("findings_claude.json").exists()

def test_run_judge_retries_then_succeeds(tmp_path):
    job = make_job(tmp_path)
    answers = iter(["esto no es json", GOOD])
    out = run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R,
                    runner=lambda p, c: next(answers), skill_path=SKILL)
    assert len(out["findings"]) == 1

def test_run_judge_fails_after_two_attempts(tmp_path):
    job = make_job(tmp_path)
    def runner(p, c):
        raise ClaudeError("rate limit")
    with pytest.raises(JudgeError):
        run_judge(job, {}, "", {"segments": []}, {"appearances": []}, {}, [], frames_list(), R, runner=runner, skill_path=SKILL)
```

- [ ] **Step 3: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 4: Implementar `videoqa/judge.py`**

```python
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from PIL import Image

from videoqa.claude_runner import ClaudeError, Runner, extract_json
from videoqa.config import SKILL_PATH
from videoqa.findings import SEVERITIES, TYPES, Finding
from videoqa.job import Job

log = logging.getLogger("videoqa")


class JudgeError(Exception):
    """El juez (claude -p) no produjo un veredicto válido tras los reintentos."""


def select_frames(frames: list[dict], appearances: list[dict], code_findings: list[Finding], max_frames: int) -> list[str]:
    by_file = {f["file"]: f["t"] for f in frames}
    chosen: list[str] = []

    def add(file: str | None) -> None:
        if file and file in by_file and file not in chosen and len(chosen) < max_frames:
            chosen.append(file)

    for f in frames:
        if f["kind"] == "scene":
            add(f["file"])
    for a in appearances:
        add(a.get("frame"))
    for fnd in code_findings:
        add(fnd.frame)
    seconds = [f["file"] for f in frames if f["kind"] == "second" and f["file"] not in chosen]
    remaining = max_frames - len(chosen)
    if remaining > 0 and seconds:
        step = max(1, len(seconds) // remaining)
        for file in seconds[::step]:
            add(file)
    return sorted(chosen, key=lambda f: by_file[f])


def prepare_inputs(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
                   code_findings: list[Finding], frames: list[dict], rules: dict) -> dict:
    inp = job.path("judge_input")
    shutil.rmtree(inp, ignore_errors=True)
    inp.mkdir()
    files = {
        "brand.json": brand,
        "transcript.json": transcript,
        "ocr.json": {"appearances": ocr.get("appearances", [])},
        "technical.json": technical,
        "findings_code.json": [f.to_dict() for f in code_findings],
    }
    for name, data in files.items():
        (inp / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    (inp / "glosario.txt").write_text(glossary_text)

    out = job.path("claude_frames")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    height = int(rules["claude"]["frame_height"])
    by_file = {f["file"]: f["t"] for f in frames}
    selected = select_frames(frames, ocr.get("appearances", []), code_findings, int(rules["claude"]["max_frames"]))
    manifest_frames = []
    for i, rel in enumerate(selected):
        t = by_file[rel]
        img = Image.open(job.path(rel)).convert("RGB")
        if img.height > height:
            img = img.resize((round(img.width * height / img.height), height))
        name = f"claude_frames/{i:02d}_{t:06.1f}s.jpg"
        img.save(job.path(name), quality=85)
        manifest_frames.append({"file": name, "t": t})
    return {"frames": manifest_frames, "inputs": [f"judge_input/{n}" for n in [*files, "glosario.txt"]]}


def build_prompt(skill_text: str, manifest: dict, duration: float) -> str:
    frame_lines = "\n".join(f"- {f['file']}  (t = {f['t']:.1f} s)" for f in manifest["frames"])
    input_lines = "\n".join(f"- {p}" for p in manifest["inputs"])
    return (f"{skill_text}\n\n---\n\n# Trabajo actual\n\nDuración del video: {duration:.1f} s.\n\n"
            f"Archivos de entrada (léelos todos con Read):\n{input_lines}\n\n"
            f"Frames clave (léelos todos con Read):\n{frame_lines}\n\n"
            "Responde solo con el JSON del veredicto.")


def parse_verdict(text: str) -> dict:
    data = extract_json(text)
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("'findings' debe ser una lista")
    for f in findings:
        if not isinstance(f, dict):
            raise ValueError("cada finding debe ser objeto")
        if f.get("type") not in TYPES:
            raise ValueError(f"type inválido: {f.get('type')}")
        if f.get("severity") not in SEVERITIES:
            raise ValueError(f"severity inválida: {f.get('severity')}")
        for k in ("t_start", "t_end"):
            if not isinstance(f.get(k), (int, float)):
                raise ValueError(f"{k} debe ser numérico")
        for k in ("title", "detail"):
            if not isinstance(f.get(k), str) or not f[k]:
                raise ValueError(f"{k} requerido")
    if not isinstance(data.get("guion_real_md", ""), str):
        raise ValueError("'guion_real_md' debe ser texto")
    data.setdefault("guion_real_md", "")
    data["confirmed_code_findings"] = [str(x) for x in data.get("confirmed_code_findings", []) or []]
    dismissed = []
    for d in data.get("dismissed_code_findings", []) or []:
        if isinstance(d, dict) and d.get("id"):
            dismissed.append({"id": str(d["id"]), "reason": str(d.get("reason", ""))})
    data["dismissed_code_findings"] = dismissed
    return data


def run_judge(job: Job, brand: dict, glossary_text: str, transcript: dict, ocr: dict, technical: dict,
              code_findings: list[Finding], frames: list[dict], rules: dict, runner: Runner,
              skill_path: Path = SKILL_PATH) -> dict:
    manifest = prepare_inputs(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames, rules)
    duration = max([f["t"] for f in frames], default=0.0)
    prompt = build_prompt(skill_path.read_text(encoding="utf-8"), manifest, duration)
    last: Exception | None = None
    verdict = None
    for attempt in (1, 2):
        try:
            verdict = parse_verdict(runner(prompt, job.dir))
            break
        except (ClaudeError, ValueError) as e:
            last = e
            log.warning("[%s] juez intento %d falló: %s", job.name, attempt, e)
    if verdict is None:
        raise JudgeError(f"juez falló tras 2 intentos: {last}")
    findings = []
    for i, f in enumerate(verdict["findings"]):
        findings.append(Finding(id=f"claude-{i}", type=f["type"], severity=f["severity"], t_start=float(f["t_start"]),
                                t_end=float(f["t_end"]), title=f["title"], detail=f["detail"],
                                suggestion=str(f.get("suggestion", "")), frame=f.get("frame") or None,
                                bbox=None, source="claude", check=f["type"]))
    job.path("findings_claude.json").write_text(json.dumps([f.to_dict() for f in findings], ensure_ascii=False, indent=2))
    job.path("guion_real.md").write_text(verdict["guion_real_md"], encoding="utf-8")
    return {"findings": findings, "dismissed": verdict["dismissed_code_findings"], "guion_real_md": verdict["guion_real_md"]}
```

- [ ] **Step 5: Correr tests** → `12 passed`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: reviewer skill and claude judge"
```

---

### Task 18: Reporte y evidencia

**Files:**
- Create: `videoqa/report.py`
- Test: `tests/unit/test_report.py`

**Interfaces:**
- Produces: `fmt_t(sec: float) -> str` ("m:ss"), `CHECK_LABELS: dict[str, str]`, `write_evidence(job: Job, findings: list[Finding]) -> dict[str, str]` (id → ruta relativa `evidencia/NN_MmSSs.jpg`), `render_report(video_name, probe, findings, status, evidence, when) -> str`, `build_report(job, probe, findings, status, when=None) -> Path` (escribe `reporte.md` en el job dir y devuelve su ruta). `status` ∈ `{"approved", "rejected", "error"}`.

- [ ] **Step 1: Tests**

`tests/unit/test_report.py`:
```python
from datetime import datetime
from PIL import Image
from videoqa.findings import Finding
from videoqa.job import Job
from videoqa.report import build_report, fmt_t, render_report, write_evidence

PROBE = {"duration": 58.0, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True}

def fnd(id, sev, t, check="brand_color", frame=None, bbox=None, typ="marca"):
    return Finding(id=id, type=typ, severity=sev, t_start=t, t_end=t + 1, title=f"T{id}", detail=f"D{id}",
                   suggestion="S", frame=frame, bbox=bbox, check=check)

def test_fmt_t():
    assert fmt_t(0) == "0:00" and fmt_t(72.4) == "1:12" and fmt_t(605) == "10:05"

def test_render_rejected_report_structure():
    fs = [fnd("w", "warning", 3, check="silence"), fnd("b", "blocker", 12)]
    md = render_report("promo.mp4", PROBE, fs, "rejected", {"b": "evidencia/01_0m12s.jpg"}, datetime(2026, 9, 11, 14, 32))
    assert md.startswith("# 🔴 promo.mp4 — NO APROBADO")
    assert "0:58" in md and "1080×1920" in md and "1 bloqueante" in md and "1 advertencia" in md
    assert md.index("## 🔴 Bloqueantes") < md.index("[0:12]") < md.index("## ⚠️ Advertencias") < md.index("[0:03]")
    assert "evidencia/01_0m12s.jpg" in md
    assert "## ✅ Checks pasados" in md and "Pantalla negra" in md and "Color de marca" not in md.split("## ✅ Checks pasados")[1]

def test_render_approved_report():
    md = render_report("ok.mp4", PROBE, [], "approved", {}, datetime(2026, 9, 11))
    assert md.startswith("# 🟢 ok.mp4 — APROBADO") and "## 🔴" not in md

def test_render_error_report():
    md = render_report("x.mp4", PROBE, [fnd("j", "warning", 0, check="judge_unavailable")], "error", {}, datetime(2026, 9, 11))
    assert md.startswith("# ❌ x.mp4 — ERROR")

def test_write_evidence_crops_with_bbox(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    (job.dir / "frames").mkdir()
    Image.new("RGB", (108, 192), (0, 0, 0)).save(job.path("frames/sec_0025.jpg"))
    fs = [fnd("b", "blocker", 12, frame="frames/sec_0025.jpg", bbox=[0.1, 0.4, 0.8, 0.1]), fnd("n", "warning", 3)]
    ev = write_evidence(job, fs)
    assert ev == {"b": "evidencia/01_0m12s.jpg"}
    assert job.path(ev["b"]).exists()

def test_build_report_writes_file(tmp_path):
    video = tmp_path / "v.mp4"; video.write_bytes(b"x")
    job = Job(video, tmp_path / "jobs")
    p = build_report(job, PROBE, [], "approved")
    assert p == job.path("reporte.md") and "APROBADO" in p.read_text()
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/report.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from videoqa.findings import Finding, count_by_severity, sort_findings
from videoqa.job import Job

CHECK_LABELS = {
    "spelling_unknown_word": "Ortografía", "spelling_punctuation": "Puntuación", "brand_color": "Color de marca",
    "text_visible_short": "Texto legible ≥ 1 s", "subtitle_desync": "Sincronía subtítulos", "text_occluded": "Zona segura UI",
    "black_frame": "Pantalla negra", "frozen_frame": "Frames congelados", "silence": "Silencios", "audio_clipping": "Clipping de audio",
    "aspect_ratio": "Relación de aspecto 9:16", "no_audio": "Pista de audio",
    "ortografia": "Ortografía (criterio)", "marca": "Reglas de marca (criterio)", "inconsistencia": "Guion ↔ pantalla",
    "blooper": "Bloopers", "tecnico": "Elementos extraños en frame",
}
STATUS = {"approved": ("🟢", "APROBADO"), "rejected": ("🔴", "NO APROBADO"), "error": ("❌", "ERROR")}


def fmt_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def _slug_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}m{sec % 60:02d}s"


def write_evidence(job: Job, findings: list[Finding]) -> dict[str, str]:
    out = job.path("evidencia")
    out.mkdir(exist_ok=True)
    evidence: dict[str, str] = {}
    n = 0
    for f in sort_findings(findings):
        if not f.frame or not job.path(f.frame).exists():
            continue
        n += 1
        img = Image.open(job.path(f.frame)).convert("RGB")
        if f.bbox:
            W, H = img.size
            x, y, w, h = f.bbox
            ImageDraw.Draw(img).rectangle([x * W, y * H, (x + w) * W, (y + h) * H], outline=(255, 0, 0), width=max(2, W // 200))
        rel = f"evidencia/{n:02d}_{_slug_t(f.t_start)}.jpg"
        img.save(job.path(rel), quality=85)
        evidence[f.id] = rel
    return evidence


def _plural(n: int, s: str, p: str) -> str:
    return f"{n} {s if n == 1 else p}"


def render_report(video_name: str, probe: dict, findings: list[Finding], status: str, evidence: dict[str, str], when: datetime) -> str:
    icon, label = STATUS[status]
    counts = count_by_severity(findings)
    lines = [f"# {icon} {video_name} — {label}",
             f"Revisado: {when:%Y-%m-%d %H:%M} · Duración {fmt_t(probe['duration'])} · {probe['width']}×{probe['height']} · "
             f"{_plural(counts['blocker'], 'bloqueante', 'bloqueantes')} · {_plural(counts['warning'], 'advertencia', 'advertencias')}", ""]
    n = 0

    def section(title: str, sev: str) -> None:
        nonlocal n
        items = [f for f in sort_findings(findings) if f.severity == sev]
        if not items:
            return
        lines.append(title)
        for f in items:
            n += 1
            span = f"[{fmt_t(f.t_start)}]" if f.t_end - f.t_start <= 1.0 else f"[{fmt_t(f.t_start)}–{fmt_t(f.t_end)}]"
            lines.append(f"{n}. **{span} {f.title}**")
            lines.append(f"   {f.detail}")
            if f.suggestion:
                lines.append(f"   Sugerencia: {f.suggestion}")
            if f.id in evidence:
                lines.append(f"   Evidencia: {evidence[f.id]}")
        lines.append("")

    section("## 🔴 Bloqueantes", "blocker")
    section("## ⚠️ Advertencias", "warning")
    section("## ℹ️ Información", "info")
    failed = {f.check for f in findings}
    passed = [label for key, label in CHECK_LABELS.items() if key not in failed]
    lines.append("## ✅ Checks pasados")
    lines.append(" · ".join(passed) if passed else "—")
    lines.append("")
    return "\n".join(lines)


def build_report(job: Job, probe: dict, findings: list[Finding], status: str, when: datetime | None = None) -> Path:
    evidence = write_evidence(job, findings)
    md = render_report(job.video.name, probe, findings, status, evidence, when or datetime.now())
    out = job.path("reporte.md")
    out.write_text(md, encoding="utf-8")
    return out
```

- [ ] **Step 4: Correr tests** → `6 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: markdown report with evidence crops"
```

---

### Task 19: Gate (decisión y entrega a Drive)

**Files:**
- Create: `videoqa/gate.py`
- Test: `tests/unit/test_gate.py`

**Interfaces:**
- Produces: `decide(findings: list[Finding]) -> str` (`"approved"` si no hay blocker, si no `"rejected"`), `deliver(job: Job, settings: Settings, status: str) -> Path` — mueve el video y copia `reporte.md`, `guion_real.md` (si existe) y `evidencia/` a `<aprobado|con_errores>/<job.name>/`; `status="error"` va a `con_errores`. Si el destino ya existe, se borra antes (sin versionado).

- [ ] **Step 1: Tests**

`tests/unit/test_gate.py`:
```python
from videoqa.config import Settings
from videoqa.findings import Finding
from videoqa.gate import decide, deliver
from videoqa.job import Job

def f(sev):
    return Finding(id="x", type="marca", severity=sev, t_start=0, t_end=1, title="t", detail="d")

def test_decide():
    assert decide([]) == "approved"
    assert decide([f("warning"), f("info")]) == "approved"
    assert decide([f("warning"), f("blocker")]) == "rejected"

def setup(tmp_path):
    drive = tmp_path / "drive"
    s = Settings(drive_root=drive, jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    video = s.entrada / "promo.mp4"; video.write_bytes(b"video")
    job = Job(video, s.jobs_dir)
    job.path("reporte.md").write_text("# r")
    job.path("guion_real.md").write_text("g")
    (job.dir / "evidencia").mkdir(); job.path("evidencia/01_0m01s.jpg").write_bytes(b"jpg")
    return s, job, video

def test_deliver_approved_moves_video_and_artifacts(tmp_path):
    s, job, video = setup(tmp_path)
    dest = deliver(job, s, "approved")
    assert dest == s.aprobado / "promo"
    assert not video.exists() and (dest / "promo.mp4").read_bytes() == b"video"
    assert (dest / "reporte.md").exists() and (dest / "guion_real.md").exists() and (dest / "evidencia" / "01_0m01s.jpg").exists()

def test_deliver_rejected_and_error_go_to_con_errores(tmp_path):
    s, job, _ = setup(tmp_path)
    assert deliver(job, s, "rejected").parent == s.con_errores
    s2, job2, _ = setup(tmp_path / "b")
    assert deliver(job2, s2, "error").parent == s2.con_errores

def test_deliver_overwrites_existing_destination(tmp_path):
    s, job, _ = setup(tmp_path)
    old = s.aprobado / "promo"; old.mkdir(parents=True); (old / "viejo.txt").write_text("x")
    deliver(job, s, "approved")
    assert not (old / "viejo.txt").exists() and (old / "promo.mp4").exists()
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/gate.py`**

```python
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
```

- [ ] **Step 4: Correr tests** → `4 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: approval gate and Drive delivery"
```

---

### Task 20: Google Sheet (upsert + cola de pendientes)

**Files:**
- Create: `videoqa/sheet.py`
- Test: `tests/unit/test_sheet.py`

**Interfaces:**
- Produces:
  - `HEADERS = ["Video", "Fecha", "Estado", "Bloqueantes", "Advertencias", "Reporte", "Video (ruta)", "Duración"]`.
  - `STATUS_LABEL = {"processing": "⏳", "approved": "🟢", "rejected": "🔴", "error": "❌ Error"}`.
  - `row_for(video_name, status, findings, report_path: str, video_path: str, duration: float, when: datetime, note: str = "") -> list[str]`.
  - `class SheetClient(worksheet)` con `ensure_headers()` y `upsert(row: list[str])`; `SheetClient.connect(sheet_id, service_account_json) -> SheetClient` (gspread). El worksheet necesita `get_all_values()`, `update(range_name, values)`, `append_row(values)`.
  - `class SheetWriter(client_factory: Callable[[], SheetClient] | None, pending_path: Path)` con `write(row)` — intenta `flush()` de pendientes + upsert; en fallo guarda en `pending_path` (JSON). Si `client_factory` es `None` (sin Sheet configurado) no hace nada.

- [ ] **Step 1: Tests**

`tests/unit/test_sheet.py`:
```python
import json
from datetime import datetime
from videoqa.findings import Finding
from videoqa.sheet import HEADERS, SheetClient, SheetWriter, row_for

class FakeWS:
    def __init__(self, rows=None): self.rows = rows or []
    def get_all_values(self): return [list(r) for r in self.rows]
    def update(self, range_name, values):
        r = int(range_name.split("!")[-1].lstrip("A").split(":")[0]) if "!" in range_name else int(range_name.lstrip("A").split(":")[0])
        self.rows[r - 1] = list(values[0])
    def append_row(self, values): self.rows.append(list(values))

def fnd(sev):
    return Finding(id="x", type="marca", severity=sev, t_start=0, t_end=1, title="t", detail="d")

def test_row_for():
    row = row_for("promo.mp4", "rejected", [fnd("blocker"), fnd("warning")], "02_Con_errores/promo/reporte.md",
                  "02_Con_errores/promo/promo.mp4", 58.0, datetime(2026, 9, 11, 14, 32))
    assert row == ["promo.mp4", "2026-09-11 14:32", "🔴", "1", "1", "02_Con_errores/promo/reporte.md", "02_Con_errores/promo/promo.mp4", "0:58"]

def test_row_for_error_note_goes_in_report_column():
    row = row_for("x.mp4", "error", [], "", "", 0, datetime(2026, 1, 1), note="ffprobe falló")
    assert row[2] == "❌ Error" and row[5] == "ffprobe falló"

def test_upsert_appends_then_updates():
    ws = FakeWS()
    c = SheetClient(ws)
    c.ensure_headers()
    assert ws.rows[0] == HEADERS
    c.upsert(["a.mp4", "f", "⏳", "", "", "", "", ""])
    c.upsert(["b.mp4", "f", "⏳", "", "", "", "", ""])
    c.upsert(["a.mp4", "f2", "🟢", "0", "0", "r", "v", "0:10"])
    assert len(ws.rows) == 3 and ws.rows[1][2] == "🟢" and ws.rows[2][0] == "b.mp4"

def test_writer_queues_on_failure_and_flushes_later(tmp_path):
    pending = tmp_path / "pending.json"
    class Boom:
        def upsert(self, row): raise ConnectionError("sin red")
    w = SheetWriter(lambda: Boom(), pending)
    w.write(["a.mp4", "f", "⏳", "", "", "", "", ""])
    assert json.loads(pending.read_text()) == [["a.mp4", "f", "⏳", "", "", "", "", ""]]
    ws = FakeWS([HEADERS])
    w2 = SheetWriter(lambda: SheetClient(ws), pending)
    w2.write(["b.mp4", "f", "🟢", "0", "0", "", "", ""])
    assert [r[0] for r in ws.rows[1:]] == ["a.mp4", "b.mp4"] and not pending.exists()

def test_writer_without_factory_is_noop(tmp_path):
    SheetWriter(None, tmp_path / "p.json").write(["a"])
    assert not (tmp_path / "p.json").exists()
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/sheet.py`**

```python
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from videoqa.findings import Finding, count_by_severity

log = logging.getLogger("videoqa")

HEADERS = ["Video", "Fecha", "Estado", "Bloqueantes", "Advertencias", "Reporte", "Video (ruta)", "Duración"]
STATUS_LABEL = {"processing": "⏳", "approved": "🟢", "rejected": "🔴", "error": "❌ Error"}


def _fmt_t(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60}:{sec % 60:02d}"


def row_for(video_name: str, status: str, findings: list[Finding], report_path: str, video_path: str,
            duration: float, when: datetime, note: str = "") -> list[str]:
    c = count_by_severity(findings)
    return [video_name, f"{when:%Y-%m-%d %H:%M}", STATUS_LABEL[status], str(c["blocker"]) if status != "processing" else "",
            str(c["warning"]) if status != "processing" else "", note or report_path, video_path, _fmt_t(duration) if duration else ""]


class SheetClient:
    def __init__(self, worksheet):
        self.ws = worksheet

    @classmethod
    def connect(cls, sheet_id: str, service_account_json: Path) -> "SheetClient":
        import gspread

        gc = gspread.service_account(filename=str(service_account_json))
        return cls(gc.open_by_key(sheet_id).sheet1)

    def ensure_headers(self) -> None:
        rows = self.ws.get_all_values()
        if not rows:
            self.ws.append_row(HEADERS)
        elif rows[0] != HEADERS:
            self.ws.update("A1:H1", [HEADERS])

    def upsert(self, row: list[str]) -> None:
        self.ensure_headers()
        rows = self.ws.get_all_values()
        for idx, existing in enumerate(rows[1:], start=2):
            if existing and existing[0] == row[0]:
                self.ws.update(f"A{idx}:H{idx}", [row])
                return
        self.ws.append_row(row)


class SheetWriter:
    def __init__(self, client_factory: Callable[[], SheetClient] | None, pending_path: Path):
        self.factory = client_factory
        self.pending_path = pending_path

    def _pending(self) -> list[list[str]]:
        return json.loads(self.pending_path.read_text()) if self.pending_path.exists() else []

    def _save_pending(self, rows: list[list[str]]) -> None:
        if rows:
            self.pending_path.parent.mkdir(parents=True, exist_ok=True)
            self.pending_path.write_text(json.dumps(rows, ensure_ascii=False))
        elif self.pending_path.exists():
            self.pending_path.unlink()

    def write(self, row: list[str]) -> None:
        if self.factory is None:
            return
        queue = self._pending() + [row]
        try:
            client = self.factory()
            while queue:
                client.upsert(queue[0])
                queue.pop(0)
        except Exception as e:  # noqa: BLE001 — red/credenciales; se reintenta después
            log.warning("Sheet no disponible (%s); %d fila(s) en cola", e, len(queue))
        self._save_pending(queue)
```

- [ ] **Step 4: Correr tests** → `5 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Google Sheet upsert with offline queue"
```

---

### Task 21: Pipeline completo + test de integración

**Files:**
- Create: `videoqa/pipeline.py`
- Test: `tests/integration/test_pipeline.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `@dataclass Result(status: str, findings: list[Finding], dest: Path | None, error: str | None)`, `process_video(video: Path, settings: Settings, rules: dict, runner: Runner, sheet: SheetWriter | None = None) -> Result`.
- Flujo:
  1. `Job.reset()` (siempre fresco; sin versionado). Sheet `⏳`.
  2. Etapas cacheadas: probe → transcribe → technical → frames → ocr → color.
  3. `brand = load_brand(config_dir, runner)`, `glossary = load_glossary(config_dir/"glosario.txt")`.
  4. `code_findings = spelling + brand_color + timing + technical` → `findings_code.json`.
  5. `run_judge(...)`; quitar de `code_findings` los ids en `dismissed`; `findings = code + claude`.
  6. Si `JudgeError`: `findings = code_findings + Finding(check="judge_unavailable")`, `status="error"`.
  7. Si no: `status = decide(findings)`.
  8. `build_report`, `deliver`, Sheet con estado final.
  9. Cualquier otra excepción (ffprobe, ffmpeg, OCR): el video se queda en Entrada; Sheet `❌ Error` con `note`; `Result(status="error", error=...)`.

- [ ] **Step 1: Test de integración**

`tests/integration/test_pipeline.py`:
```python
import json
import shutil
from pathlib import Path
import pytest
from videoqa.config import Settings, load_rules
from videoqa.pipeline import process_video
from videoqa.sheet import HEADERS, SheetClient, SheetWriter

FIX = Path(__file__).resolve().parents[1] / "fixtures"

GOOD_VERDICT = json.dumps({"findings": [], "confirmed_code_findings": [], "dismissed_code_findings": [],
                           "guion_real_md": "## Escena 1 [0:00]\nAprovecha la oferta de verano."})

class FakeWS:
    def __init__(self): self.rows = []
    def get_all_values(self): return [list(r) for r in self.rows]
    def update(self, rng, values):
        r = int(rng.split(":")[0].lstrip("A")); self.rows[r - 1] = list(values[0])
    def append_row(self, v): self.rows.append(list(v))

def make_env(tmp_path, fixture_videos, name):
    drive = tmp_path / "drive"
    s = Settings(drive_root=drive, jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True); s.config_dir.mkdir()
    shutil.copy(FIX / "brand.json", s.config_dir / "brand.json")
    shutil.copy(FIX / "glosario.txt", s.config_dir / "glosario.txt")
    video = s.entrada / f"{name}.mp4"
    shutil.copy(fixture_videos[name], video)
    return s, video

def stub_transcript(monkeypatch):
    """Evita Whisper real: transcripción fija coherente con el audio de los fixtures."""
    import videoqa.pipeline as pl
    monkeypatch.setattr(pl, "transcribe", lambda job, has_audio, model: {
        "language": "es", "text": "Aprovecha la oferta de verano solo por esta semana" if has_audio else "",
        "segments": [{"start": 0.5, "end": 4.0, "text": "Aprovecha la oferta de verano solo por esta semana"}] if has_audio else []})

def test_spelling_color_fixture_is_rejected(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "spelling_color")
    ws = FakeWS()
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "pending.json"))
    assert res.status == "rejected"
    checks = {f.check for f in res.findings}
    assert {"spelling_unknown_word", "brand_color"} <= checks
    assert res.dest == s.con_errores / "spelling_color"
    assert not video.exists() and (res.dest / "spelling_color.mp4").exists()
    report = (res.dest / "reporte.md").read_text()
    assert report.startswith("# 🔴") and "Aprobecha" in report and "#FF3B30" in report.upper()
    assert (res.dest / "guion_real.md").read_text().startswith("## Escena 1")
    assert any(p.suffix == ".jpg" for p in (res.dest / "evidencia").iterdir())
    assert ws.rows[0] == HEADERS and ws.rows[1][0] == "spelling_color.mp4" and ws.rows[1][2] == "🔴"

def test_clean_fixture_is_approved(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT)
    assert res.status == "approved", [f.title for f in res.findings]
    assert (s.aprobado / "clean" / "clean.mp4").exists()

def test_black_screen_fixture_is_rejected_by_technical_check(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "black_screen")
    res = process_video(video, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT)
    assert res.status == "rejected" and "black_frame" in {f.check for f in res.findings}

def test_judge_dismissal_removes_code_finding(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "spelling_color")
    def runner(prompt, cwd):
        code = json.loads((cwd / "judge_input" / "findings_code.json").read_text())
        spell_ids = [f["id"] for f in code if f["check"] == "spelling_unknown_word"]
        return json.dumps({"findings": [], "confirmed_code_findings": [], "guion_real_md": "",
                           "dismissed_code_findings": [{"id": i, "reason": "marca del cliente"} for i in spell_ids]})
    res = process_video(video, s, load_rules(), runner=runner)
    assert "spelling_unknown_word" not in {f.check for f in res.findings}
    assert "brand_color" in {f.check for f in res.findings}

def test_judge_failure_yields_error_status_in_con_errores(tmp_path, fixture_videos, monkeypatch):
    stub_transcript(monkeypatch)
    s, video = make_env(tmp_path, fixture_videos, "clean")
    ws = FakeWS()
    def runner(p, cwd):
        raise RuntimeError("no debería llegar aquí sin ClaudeError")  # pragma: no cover
    from videoqa.claude_runner import ClaudeError
    def failing(p, cwd):
        raise ClaudeError("rate limit")
    res = process_video(video, s, load_rules(), runner=failing, sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error" and "judge_unavailable" in {f.check for f in res.findings}
    assert (s.con_errores / "clean" / "reporte.md").read_text().startswith("# ❌")
    assert ws.rows[1][2] == "❌ Error"

def test_corrupt_video_stays_in_entrada(tmp_path, fixture_videos, monkeypatch):
    s, _ = make_env(tmp_path, fixture_videos, "clean")
    bad = s.entrada / "roto.mp4"; bad.write_bytes(b"no es un video")
    ws = FakeWS()
    res = process_video(bad, s, load_rules(), runner=lambda p, cwd: GOOD_VERDICT,
                        sheet=SheetWriter(lambda: SheetClient(ws), tmp_path / "p.json"))
    assert res.status == "error" and res.error and bad.exists()
    assert ws.rows[-1][2] == "❌ Error" and ws.rows[-1][5]
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError: videoqa.pipeline`

- [ ] **Step 3: Implementar `videoqa/pipeline.py`**

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from videoqa.brand import load_brand
from videoqa.checks.brand_color import check_brand_colors
from videoqa.checks.spelling import check_spelling, load_glossary
from videoqa.checks.technical import check_technical
from videoqa.checks.timing import check_timing
from videoqa.claude_runner import Runner
from videoqa.config import Settings
from videoqa.findings import Finding, save_findings
from videoqa.gate import decide, deliver
from videoqa.job import Job
from videoqa.judge import JudgeError, run_judge
from videoqa.report import build_report
from videoqa.sheet import SheetWriter, row_for
from videoqa.stages.color import add_colors
from videoqa.stages.frames import extract_frames
from videoqa.stages.ocr import ocr_frames
from videoqa.stages.probe import probe
from videoqa.stages.technical import analyze
from videoqa.stages.transcribe import transcribe

log = logging.getLogger("videoqa")


@dataclass
class Result:
    status: str                 # approved | rejected | error
    findings: list[Finding]
    dest: Path | None
    error: str | None = None


def _rel(settings: Settings, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(settings.drive_root))
    except ValueError:
        return str(path)


def process_video(video: Path, settings: Settings, rules: dict, runner: Runner, sheet: SheetWriter | None = None) -> Result:
    sheet = sheet or SheetWriter(None, settings.jobs_dir / "sheet_pending.json")
    job = Job(video, settings.jobs_dir)
    job.reset()
    started = datetime.now()
    log.info("[%s] inicio", job.name)
    sheet.write(row_for(video.name, "processing", [], "", _rel(settings, video), 0, started))

    try:
        p = job.run_stage("probe", "probe.json", probe)
        transcript = job.run_stage("transcribe", "transcript.json", lambda j: transcribe(j, p["has_audio"], settings.whisper_model))
        technical = job.run_stage("technical", "technical.json", lambda j: analyze(j, p["has_audio"], float(rules["frames"]["scene_threshold"])))
        frames = job.run_stage("frames", "frames.json", lambda j: extract_frames(j, technical["scene_cuts"], int(rules["frames"]["fps"])))
        ocr = job.run_stage("ocr", "ocr.json", lambda j: ocr_frames(j, frames["frames"], frames["period"]))
        ocr = job.run_stage("color", "ocr_color.json", lambda j: add_colors(j, ocr))

        brand = load_brand(settings.config_dir, runner)
        glossary_path = settings.config_dir / "glosario.txt"
        glossary = load_glossary(glossary_path)
        apps = ocr["appearances"]
        code_findings = (check_spelling(apps, glossary, rules) + check_brand_colors(apps, brand, rules)
                         + check_timing(apps, transcript["segments"], rules) + check_technical(p, technical, rules))
        save_findings(job.path("findings_code.json"), code_findings)
    except Exception as e:  # noqa: BLE001 — fallo de extracción: el video se queda en Entrada
        msg = f"{type(e).__name__}: {e}"
        log.exception("[%s] fallo de procesamiento", job.name)
        sheet.write(row_for(video.name, "error", [], "", _rel(settings, video), 0, datetime.now(), note=msg))
        return Result("error", [], None, msg)

    glossary_text = glossary_path.read_text(encoding="utf-8") if glossary_path.exists() else ""
    try:
        verdict = run_judge(job, brand, glossary_text, transcript, ocr, technical, code_findings, frames["frames"], rules, runner)
        dismissed = {d["id"] for d in verdict["dismissed"]}
        findings = [f for f in code_findings if f.id not in dismissed] + verdict["findings"]
        status = decide(findings)
    except JudgeError as e:
        log.error("[%s] %s", job.name, e)
        findings = code_findings + [Finding(
            id="judge-0", type="tecnico", severity=rules["severities"]["judge_unavailable"], t_start=0.0, t_end=float(p["duration"]),
            title="Revisión de criterio pendiente", detail=f"Claude no pudo revisar este video ({e}). Solo se aplicaron los checks automáticos.",
            suggestion="Reintentar más tarde o revisar manualmente.", source="code", check="judge_unavailable")]
        status = "error"

    build_report(job, p, findings, status)
    dest = deliver(job, settings, status)
    sheet.write(row_for(video.name, status, findings, _rel(settings, dest / "reporte.md"), _rel(settings, dest / video.name),
                        float(p["duration"]), datetime.now()))
    log.info("[%s] %s → %s", job.name, status, dest)
    return Result(status, findings, dest)
```

- [ ] **Step 4: Correr integración**

Run: `uv run pytest tests/integration -q -x`
Expected: `6 passed`. Notas de depuración probables:
- Si `clean` sale `rejected` por `subtitle_desync`: el texto aparece en t=1.0 y la transcripción stub empieza en 0.5 → diferencia 0.5 < 1.0, OK. Si el OCR devuelve el texto partido en dos apariciones, ajustar `iou_min` no; revisar `norm_text`.
- Si `spelling_color` no marca `brand_color`: imprimir `ocr_color.json` y verificar que `color_hex` ≈ `#FF3B30` (la compresión puede dar `#FE3A2F`; ΔE < 8 con la paleta roja no existe, así que sigue fallando correctamente).
- Si `text_occluded` aparece en fixtures (texto centrado no debería): verificar conversión de origen en `ocr_frame`.

- [ ] **Step 5: Correr toda la suite** → `uv run pytest -q` verde

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: end-to-end pipeline with integration tests"
```

---

### Task 22: Watcher de `01_Entrada/`

**Files:**
- Create: `videoqa/watcher.py`
- Test: `tests/unit/test_watcher.py`

**Interfaces:**
- Produces: `VIDEO_EXT = {".mp4", ".mov", ".m4v"}`, `list_videos(entrada: Path) -> list[Path]` (ordenados por mtime, ignora ocultos y `.partial`), `is_stable(path, wait_s=30, poll_s=5, sleep=time.sleep) -> bool`, `watch(settings, rules, runner, sheet=None, poll_s=10, once=False, process=process_video, sleep=time.sleep) -> None` con reintento de fallidos cada `retry_after_s=600`.

- [ ] **Step 1: Tests**

`tests/unit/test_watcher.py`:
```python
from pathlib import Path
from videoqa.config import Settings
from videoqa.pipeline import Result
from videoqa.watcher import is_stable, list_videos, watch

def test_list_videos_filters_and_orders(tmp_path):
    (tmp_path / "b.mp4").write_bytes(b"1"); (tmp_path / "a.MOV").write_bytes(b"1")
    (tmp_path / ".oculto.mp4").write_bytes(b"1"); (tmp_path / "x.txt").write_bytes(b"1"); (tmp_path / "c.mp4.partial").write_bytes(b"1")
    import os, time
    os.utime(tmp_path / "b.mp4", (time.time() - 50, time.time() - 50))
    assert [p.name for p in list_videos(tmp_path)] == ["b.mp4", "a.MOV"]

def test_is_stable_true_when_size_constant(tmp_path):
    p = tmp_path / "v.mp4"; p.write_bytes(b"1234")
    assert is_stable(p, wait_s=2, poll_s=1, sleep=lambda s: None) is True

def test_is_stable_false_when_growing(tmp_path):
    p = tmp_path / "v.mp4"; p.write_bytes(b"1")
    def grow(s): p.write_bytes(p.read_bytes() + b"1")
    assert is_stable(p, wait_s=2, poll_s=1, sleep=grow) is False

def test_watch_once_processes_stable_videos_and_skips_failed(tmp_path):
    s = Settings(drive_root=tmp_path / "drive", jobs_dir=tmp_path / "jobs")
    s.entrada.mkdir(parents=True)
    (s.entrada / "a.mp4").write_bytes(b"1"); (s.entrada / "b.mp4").write_bytes(b"1")
    seen = []
    def fake_process(video, settings, rules, runner, sheet=None):
        seen.append(video.name)
        return Result("error", [], None, "roto") if video.name == "b.mp4" else Result("approved", [], None)
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert sorted(seen) == ["a.mp4", "b.mp4"]
    watch(s, {}, runner=lambda p, c: "", once=True, process=fake_process, sleep=lambda x: None, stable_wait_s=0)
    assert sorted(seen) == ["a.mp4", "b.mp4"]  # b falló hace < retry_after_s: no se reintenta aún
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/watcher.py`**

```python
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from videoqa.claude_runner import Runner
from videoqa.config import Settings
from videoqa.pipeline import process_video
from videoqa.sheet import SheetWriter

log = logging.getLogger("videoqa")
VIDEO_EXT = {".mp4", ".mov", ".m4v"}


def list_videos(entrada: Path) -> list[Path]:
    if not entrada.exists():
        return []
    vids = [p for p in entrada.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in VIDEO_EXT]
    return sorted(vids, key=lambda p: p.stat().st_mtime)


def is_stable(path: Path, wait_s: float = 30, poll_s: float = 5, sleep: Callable[[float], None] = time.sleep) -> bool:
    """True si el tamaño no cambia durante wait_s (Drive termina de escribir)."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return False
    elapsed = 0.0
    while elapsed < wait_s:
        sleep(poll_s)
        elapsed += poll_s
        try:
            now = path.stat().st_size
        except FileNotFoundError:
            return False
        if now != size:
            return False
    return size > 0


def watch(settings: Settings, rules: dict, runner: Runner, sheet: SheetWriter | None = None, poll_s: float = 10,
          once: bool = False, process=process_video, sleep: Callable[[float], None] = time.sleep,
          stable_wait_s: float = 30, retry_after_s: float = 600) -> None:
    failed: dict[str, float] = {}
    log.info("vigilando %s", settings.entrada)
    while True:
        for video in list_videos(settings.entrada):
            key = str(video)
            if key in failed and time.time() - failed[key] < retry_after_s:
                continue
            if stable_wait_s and not is_stable(video, wait_s=stable_wait_s, sleep=sleep):
                log.info("%s aún sincronizando; se reintenta en el próximo ciclo", video.name)
                continue
            result = process(video, settings, rules, runner, sheet=sheet)
            if result.status == "error" and result.dest is None:
                failed[key] = time.time()
            else:
                failed.pop(key, None)
        if once:
            return
        sleep(poll_s)
```

- [ ] **Step 4: Correr tests** → `4 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: polling watcher for 01_Entrada"
```

---

### Task 23: CLI, launchd y documentación de instalación

**Files:**
- Create: `videoqa/cli.py`, `launchd/com.videoqa.watcher.plist`, `docs/SETUP.md`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: comando `videoqa` con subcomandos:
  - `init --drive-root <ruta> [--sheet-id ID --service-account ruta.json]` → escribe `~/.videoqa/config.yaml` y crea `_config/`, `01_Entrada/`, `02_Con_errores/`, `03_Aprobado/`.
  - `brand` → regenera `brand.json` desde el PDF (fuerza rebuild).
  - `run <video>` → procesa un video y imprime estado + ruta del reporte.
  - `watch [--once]` → watcher.
  - `main(argv=None) -> int`.
- `make_runner(settings, rules) -> Runner` = `run_claude` con `claude_bin` y `timeout_s` de config/reglas.
- `make_sheet(settings) -> SheetWriter`.

- [ ] **Step 1: Tests**

`tests/unit/test_cli.py`:
```python
import yaml
from videoqa.cli import main

def test_init_writes_config_and_folders(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "Revision_Videos"
    assert main(["init", "--drive-root", str(drive), "--sheet-id", "abc"]) == 0
    data = yaml.safe_load(cfg.read_text())
    assert data["drive_root"] == str(drive) and data["sheet_id"] == "abc"
    for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
        assert (drive / d).is_dir()

def test_run_uses_injected_process(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    drive = tmp_path / "drive"
    main(["init", "--drive-root", str(drive)])
    video = drive / "01_Entrada" / "v.mp4"; video.write_bytes(b"x")
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("approved", [], drive / "03_Aprobado" / "v"))
    assert main(["run", str(video)]) == 0

def test_run_returns_1_on_error(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setenv("VIDEOQA_CONFIG", str(cfg))
    main(["init", "--drive-root", str(tmp_path / "drive")])
    import videoqa.cli as cli
    from videoqa.pipeline import Result
    monkeypatch.setattr(cli, "process_video", lambda v, s, r, runner, sheet=None: Result("error", [], None, "boom"))
    assert main(["run", str(tmp_path / "x.mp4")]) == 1
```

- [ ] **Step 2: Correr para ver fallo** → `ModuleNotFoundError`

- [ ] **Step 3: Implementar `videoqa/cli.py`**

```python
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import yaml

from videoqa.brand import build_brand
from videoqa.claude_runner import Runner, run_claude
from videoqa.config import DEFAULT_CONFIG, Settings, load_rules, load_settings
from videoqa.pipeline import process_video
from videoqa.sheet import SheetClient, SheetWriter
from videoqa.watcher import watch

LOG_DIR = Path.home() / ".videoqa"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    root = logging.getLogger("videoqa")
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(LOG_DIR / "videoqa.log", maxBytes=5_000_000, backupCount=3)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.handlers = [fh, sh]


def make_runner(settings: Settings, rules: dict) -> Runner:
    timeout = int(rules["claude"]["timeout_s"])
    return lambda prompt, cwd: run_claude(prompt, cwd, claude_bin=settings.claude_bin, timeout=timeout)


def make_sheet(settings: Settings) -> SheetWriter:
    factory = None
    if settings.sheet_id and settings.service_account_json:
        factory = lambda: SheetClient.connect(settings.sheet_id, settings.service_account_json)  # noqa: E731
    return SheetWriter(factory, settings.jobs_dir / "sheet_pending.json")


def cmd_init(args) -> int:
    cfg_path = Path(os.environ.get("VIDEOQA_CONFIG", DEFAULT_CONFIG))
    drive = Path(args.drive_root).expanduser()
    data = {"drive_root": str(drive)}
    if args.sheet_id:
        data["sheet_id"] = args.sheet_id
    if args.service_account:
        data["service_account_json"] = str(Path(args.service_account).expanduser())
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True))
    for d in ("_config", "01_Entrada", "02_Con_errores", "03_Aprobado"):
        (drive / d).mkdir(parents=True, exist_ok=True)
    print(f"Config escrita en {cfg_path}\nCarpetas creadas en {drive}")
    return 0


def cmd_brand(args) -> int:
    settings, rules = load_settings(), load_rules()
    brand = build_brand(settings.config_dir, make_runner(settings, rules))
    print(f"brand.json actualizado: {len(brand['palette'])} colores, {len(brand['rules'])} reglas")
    return 0


def cmd_run(args) -> int:
    settings, rules = load_settings(), load_rules()
    res = process_video(Path(args.video).expanduser(), settings, rules, make_runner(settings, rules), sheet=make_sheet(settings))
    if res.dest:
        print(f"{res.status.upper()} → {res.dest / 'reporte.md'}")
    else:
        print(f"ERROR: {res.error}")
    return 0 if res.status in ("approved", "rejected") else 1


def cmd_watch(args) -> int:
    settings, rules = load_settings(), load_rules()
    watch(settings, rules, make_runner(settings, rules), sheet=make_sheet(settings), once=args.once)
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    ap = argparse.ArgumentParser(prog="videoqa", description="Revisión automática de videos pre-publicación")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="crear config y carpetas de Drive")
    p.add_argument("--drive-root", required=True)
    p.add_argument("--sheet-id")
    p.add_argument("--service-account")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("brand", help="regenerar brand.json desde guia_de_marca.pdf")
    p.set_defaults(fn=cmd_brand)
    p = sub.add_parser("run", help="procesar un video")
    p.add_argument("video")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("watch", help="vigilar 01_Entrada/")
    p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr tests** → `3 passed`; y `uv run videoqa --help` muestra los 4 subcomandos.

- [ ] **Step 5: Crear `launchd/com.videoqa.watcher.plist`**

Sustituir `__HOME__` y `__PROJECT__` en la instalación (ver SETUP.md):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.videoqa.watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>__HOME__/.local/bin/uv</string>
    <string>run</string>
    <string>--project</string>
    <string>__PROJECT__</string>
    <string>videoqa</string>
    <string>watch</string>
  </array>
  <key>WorkingDirectory</key><string>__PROJECT__</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:__HOME__/.local/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>__HOME__/.videoqa/launchd.out.log</string>
  <key>StandardErrorPath</key><string>__HOME__/.videoqa/launchd.err.log</string>
</dict>
</plist>
```

- [ ] **Step 6: Escribir `docs/SETUP.md`**

```markdown
# VideoQA — Instalación y operación

## Requisitos
- Mac con Apple Silicon, macOS 14+.
- Google Drive para escritorio con la carpeta del equipo sincronizada (modo "Stream" o "Mirror").
- Claude Code instalado y con sesión iniciada (`claude` en la terminal, plan Pro/Max).
- Homebrew.

## 1. Instalar
```bash
brew install uv ffmpeg
cd ~/videoeditorpipeline
uv sync
```

## 2. Configurar
Localiza la carpeta sincronizada, por ejemplo
`~/Library/CloudStorage/GoogleDrive-<cuenta>/Shared drives/<Equipo>/Revision_Videos`.

```bash
uv run videoqa init --drive-root "<ruta a Revision_Videos>"
```
Esto crea `_config/`, `01_Entrada/`, `02_Con_errores/`, `03_Aprobado/` y `~/.videoqa/config.yaml`.

Copia la guía de marca a `_config/guia_de_marca.pdf` (Canva → Descargar → PDF) y, opcionalmente,
crea `_config/glosario.txt` con una palabra por línea (nombres propios, marcas, jerga válida).

Genera la paleta y reglas (usa Claude una sola vez; revisa el resultado a mano si quieres):
```bash
uv run videoqa brand
cat "<ruta a Revision_Videos>/_config/brand.json"
```

## 3. Google Sheet (opcional)
1. En Google Cloud Console: crear proyecto → habilitar **Google Sheets API** → crear **cuenta de
   servicio** → generar clave JSON → guardarla en `~/.videoqa/service_account.json`.
2. Crear un Sheet llamado `Tablero Revision` y compartirlo (Editor) con el email de la cuenta de servicio.
3. Copiar el ID del Sheet (parte de la URL entre `/d/` y `/edit`) y re-ejecutar:
```bash
uv run videoqa init --drive-root "<ruta>" --sheet-id <ID> --service-account ~/.videoqa/service_account.json
```

## 4. Probar con un video
```bash
uv run videoqa run "<ruta a Revision_Videos>/01_Entrada/mi_video.mp4"
```
La primera vez descarga el modelo de Whisper (~1.5 GB). El resultado queda en `02_Con_errores/` o
`03_Aprobado/` con `reporte.md`, `guion_real.md` y `evidencia/`.

## 5. Dejarlo corriendo solo (launchd)
```bash
sed -e "s|__HOME__|$HOME|g" -e "s|__PROJECT__|$HOME/videoeditorpipeline|g" \
  launchd/com.videoqa.watcher.plist > ~/Library/LaunchAgents/com.videoqa.watcher.plist
launchctl load ~/Library/LaunchAgents/com.videoqa.watcher.plist
```
Ver estado / logs:
```bash
launchctl list | grep videoqa
tail -f ~/.videoqa/videoqa.log
```
Detener:
```bash
launchctl unload ~/Library/LaunchAgents/com.videoqa.watcher.plist
```

## Regla del equipo
Solo se publica lo que está en `03_Aprobado/`. Si un video cae en `02_Con_errores/`, el editor
corrige, vuelve a subir el archivo a `01_Entrada/` con el mismo nombre y espera el nuevo reporte.

## Ajustar severidades
Edita `reglas.yaml` (por ejemplo, `silence: blocker`) y reinicia el watcher. Para cambiar el criterio
de Claude, edita `.claude/skills/revisor-video/SKILL.md`.

## Problemas comunes
- **El video no se procesa**: ¿está la Mac encendida y Drive terminó de sincronizar? Mira `videoqa.log`.
- **`❌ Error` en el Sheet**: la columna Reporte tiene el motivo. Si es Claude (límite de uso), el
  video queda en `02_Con_errores/` con reporte parcial; resúbelo más tarde.
- **Falsos positivos de ortografía**: añade la palabra a `_config/glosario.txt`.
```

- [ ] **Step 7: Prueba manual de extremo a extremo con Claude real**

```bash
VIDEOQA_CONFIG=/tmp/videoqa-test.yaml uv run videoqa init --drive-root /tmp/videoqa-drive
cp tests/fixtures/brand.json /tmp/videoqa-drive/_config/
cp tests/fixtures/out/spelling_color.mp4 /tmp/videoqa-drive/01_Entrada/
VIDEOQA_CONFIG=/tmp/videoqa-test.yaml uv run videoqa run /tmp/videoqa-drive/01_Entrada/spelling_color.mp4
cat /tmp/videoqa-drive/02_Con_errores/spelling_color/reporte.md
cat /tmp/videoqa-drive/02_Con_errores/spelling_color/guion_real.md
```
Expected: estado `REJECTED`, reporte con "Aprobecha" y color `#FF3B30`, `guion_real.md` con la frase
"Aprovecha la oferta de verano…". Si Claude responde texto en vez de JSON, endurecer la última línea
de `build_prompt`.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: CLI, launchd agent and setup docs"
```

---

## Auto-revisión del plan

**Cobertura del spec:**
- §3.1 carpetas → Task 23 `init`; §3.2 disparo → Task 22 + plist; §3.3 etapas 1–9 → Tasks 5–10, 21; §3.4 brand.json → Task 16; §3.5 juez → Tasks 15, 17; §4 checks → Tasks 11–14 (código) + SKILL.md (criterio); §5.1 reporte → Task 18; §5.2 Sheet → Task 20 (links como rutas relativas a Drive — sin API de Drive, YAGNI); §5.3 gate → Task 19; §6 errores → Tasks 20, 21, 22; §7 stack → Task 1; §8 pruebas → Tasks 3, 21, 23 paso 7.
- Diferencia respecto al spec: el watcher usa **polling** (10 s) en vez de `watchdog`, porque los eventos FS de Drive para escritorio en modo Stream no son fiables; funcionalmente equivalente y más simple.

**Consistencia de tipos:** `Runner = Callable[[str, Path], str]` en todos los consumidores (`brand`, `judge`, `pipeline`, `cli`); `Finding` con `check` como clave de `reglas.yaml`; `frames["period"]` producido en Task 7 y consumido en Task 9/21; `ocr["appearances"]` con `color_hex` desde Task 10 hacia Tasks 11–13, 17.
