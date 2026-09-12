# Diseño: Pipeline de revisión automática de videos (VideoQA)

Fecha: 2026-09-11
Estado: aprobado en conversación, pendiente de plan de implementación

## 1. Objetivo

Automatizar la revisión previa a publicación de reels/TikToks que hace hoy una
revisora humana. Cada video subido a Drive pasa por un pipeline tipo CI/CD que
detecta errores de ortografía, marca (colores), inconsistencias guion↔pantalla y
bloopers, y solo lo deja en la carpeta `03_Aprobado/` cuando no hay errores
bloqueantes. Además genera el **guion real** del video a partir de lo que dice el
talento.

## 2. Contexto y restricciones

- Flujo humano: editora master sube → editores junior modifican → revisora
  aprueba → una persona publica manualmente en Meta/TikTok.
- Volumen: ~10 reels de 60 s por semana, ocasionalmente sketches largos (varios
  minutos).
- Recursos: suscripción de claude.ai (Claude Code), **sin** API de pago de
  Anthropic. Procesamiento en una MacBook Apple Silicon con Google Drive para
  escritorio sincronizando la carpeta del equipo.
- Claude no procesa audio ni video nativamente: audio → Whisper local; video →
  frames (imágenes).
- El gate de publicación es de proceso (carpetas), no técnico.
- **Sin versionado** en esta fase: resubir un video con el mismo nombre lo
  re-revisa y sobreescribe el reporte anterior.

## 3. Arquitectura

```
Drive (sincronizado local)                MacBook
┌──────────────────────┐    launchd    ┌────────────────────────────────────┐
│ 01_Entrada/  ───────────► watcher ──► cola ──► pipeline por video        │
│ 02_Con_errores/ ◄─────────┐            │  1 sonda (ffprobe)              │
│ 03_Aprobado/    ◄─────────┤            │  2 transcripción (mlx-whisper)  │
│ _config/                  │            │  3 técnico video (ffmpeg)       │
│   guia_de_marca.pdf       │            │  4 frames (ffmpeg)              │
│   brand.json  ◄───────────┤            │  5 OCR (Apple Vision)           │
│   glosario.txt            │            │  6 color de texto (numpy)       │
└──────────────────────┘    │            │  7 checks deterministas         │
                            │            │  8 juicio (claude -p + skill)   │
Google Sheet ◄──────────────┴────────────│  9 gate + reporte + sheet       │
                                         └────────────────────────────────────┘
```

Estado intermedio en `~/.videoqa/jobs/<video>/` (local, no en Drive).
Log en `~/.videoqa/videoqa.log`.

### 3.1 Estructura de carpetas en Drive

```
Revision_Videos/
├── _config/
│   ├── guia_de_marca.pdf     # provista por el equipo (Canva → PDF)
│   ├── brand.json            # derivado automáticamente del PDF (cacheado)
│   └── glosario.txt          # opcional: palabras válidas fuera de diccionario
├── 01_Entrada/               # subida de videos (.mp4 / .mov)
├── 02_Con_errores/<video>/   # video + reporte.md + guion_real.md + evidencia/
└── 03_Aprobado/<video>/      # única fuente para publicar
```

### 3.2 Disparo

- Servicio `launchd` (LaunchAgent, arranca al iniciar sesión) ejecuta el watcher.
- El watcher (`watchdog`) observa `01_Entrada/`. Un archivo se considera listo
  cuando su tamaño es estable durante 30 s (Drive escribe por partes). Si sigue
  cambiando tras 10 min, se registra y se reintenta en el siguiente ciclo.
- Al arrancar, procesa lo que ya esté pendiente en `01_Entrada/` (cola tras
  tener la Mac cerrada).
- Los videos se procesan de uno en uno (cola FIFO) para no saturar CPU/GPU.

### 3.3 Etapas del pipeline

| # | Etapa | Herramienta | Salida en job dir |
|---|---|---|---|
| 1 | Sonda | `ffprobe` | `probe.json`: duración, resolución, fps, tiene_audio |
| 2 | Transcripción | `mlx-whisper` (`large-v3-turbo`, es) | `transcript.json`: segmentos `{start,end,text}` |
| 3 | Técnico video | `ffmpeg` filtros `blackdetect`, `freezedetect`, `silencedetect`, `scdet`, `astats` | `technical.json`: intervalos de negro/congelado/silencio, cortes de escena, clipping |
| 4 | Frames | `ffmpeg` | `frames/`: 1 fps + 1 frame por corte de escena, JPG |
| 5 | OCR | `ocrmac` (Apple Vision, es) | `ocr.json`: por frame, textos con caja normalizada y confianza; deduplicado a "apariciones" `{text, bbox, t_start, t_end}` |
| 6 | Color de texto | numpy sobre cada caja OCR | añade `color_hex` a cada aparición (color dominante de píxeles de trazo, no fondo) |
| 7 | Checks deterministas | Python | `findings_code.json` |
| 8 | Juicio Claude | `claude -p --output-format json` con skill `revisor-video` | `findings_claude.json`, `guion_real.md` |
| 9 | Gate + salida | Python | `reporte.md`, `evidencia/*.jpg`, mueve carpeta, actualiza Sheet |

Cada etapa es idempotente y se salta si su salida ya existe; un fallo reintenta
solo esa etapa.

### 3.4 `brand.json`

Generado por Claude (`claude -p`) la primera vez o cuando cambia el hash del
PDF. Esquema:

```json
{
  "palette": [{"name": "Negro", "hex": "#1A1A1A"}, ...],
  "fonts": ["Montserrat"],
  "rules": ["Los títulos siempre en blanco", ...],
  "logo_required": true,
  "source_pdf_sha256": "..."
}
```

El equipo puede editarlo a mano; el pipeline solo lo regenera si cambia el PDF
y no hay edición manual más reciente (compara mtime).

### 3.5 Juicio con Claude

Se invoca Claude Code en modo no interactivo con un skill de proyecto
`.claude/skills/revisor-video/SKILL.md` que contiene: rol de revisor, reglas de
severidad, esquema JSON de salida y ejemplos. Entrada al prompt:

- `brand.json`, `glosario.txt`
- `transcript.json`
- `ocr.json` (apariciones deduplicadas con color)
- `technical.json`
- `findings_code.json` (para que confirme/descartre falsos positivos)
- 10–15 frames clave: uno por escena + los que tienen texto + los marcados
  sospechosos por etapas 3/7. Frames a 720 px de alto para ahorrar tokens.

Salida esperada (validada contra esquema; 1 reintento si es inválida):

```json
{
  "findings": [
    {"type": "ortografia|marca|inconsistencia|blooper|tecnico",
     "severity": "blocker|warning|info",
     "t_start": 12.0, "t_end": 12.8,
     "title": "...", "detail": "...", "suggestion": "...",
     "frame": "frames/00012.jpg"}
  ],
  "confirmed_code_findings": ["id", ...],
  "dismissed_code_findings": [{"id": "...", "reason": "..."}],
  "guion_real_md": "..."
}
```

Si Claude falla dos veces: el video sale solo con hallazgos de código, se añade
la advertencia "revisión de criterio pendiente" y el estado en Sheet es
`❌ Error`. Nunca se aprueba por defecto.

## 4. Checks

Severidades configurables en `reglas.yaml` (raíz del proyecto). Valores por
defecto:

### Ortografía y redacción (texto en pantalla)
| Check | Sev. | Quién |
|---|---|---|
| Palabra fuera de diccionario ES y de `glosario.txt` | blocker | código; Claude confirma/descarta |
| Tildes incorrectas según contexto | blocker | Claude |
| Puntuación: falta ¿¡, dobles espacios, minúscula tras punto | warning | código |
| Nombre propio/marca escrito de dos formas en el mismo video | blocker | Claude |

### Marca
| Check | Sev. | Quién |
|---|---|---|
| Color de texto fuera de paleta (tolerancia ΔE2000 ≤ 8) | blocker | código |
| Regla escrita de la guía violada | blocker | Claude |
| Logo ausente si `logo_required` | warning | Claude |
| Fuente distinta a la de marca (visual, aproximado) | warning | Claude |

### Inconsistencias guion ↔ pantalla
| Check | Sev. | Quién |
|---|---|---|
| Texto en pantalla contradice al talento (cifra, nombre, fecha, precio) | blocker | Claude |
| Subtítulo con palabras cambiadas respecto a lo dicho | blocker | Claude |
| Subtítulo desincronizado > 1 s | warning | código |
| Texto visible < 1 s | warning | código |

### Bloopers y técnica
| Check | Sev. | Quién |
|---|---|---|
| Toma fallida del talento ("otra vez", "corte", risa, frase repetida, tartamudeo) | blocker | Claude sobre transcript |
| Pantalla negra / frame congelado > 0.5 s fuera de los primeros/últimos 0.5 s | blocker | ffmpeg |
| Silencio > 2 s en medio del video | warning | ffmpeg |
| Clipping de audio | warning | ffmpeg |
| Texto en zona tapada por UI de TikTok/Reels (banda inferior 20 %, franja derecha 15 %) o cortado por el borde | warning | código |
| Elemento extraño en frame (watermark de stock, cursor, UI del editor) | blocker | Claude |
| Relación de aspecto ≠ 9:16 | warning | ffprobe |

### Entregable: `guion_real.md`
Transcripción limpia (sin muletillas), puntuada, dividida por escena con
timestamps.

## 5. Salidas

### 5.1 `reporte.md`

Encabezado con estado (🔴 NO APROBADO / 🟢 APROBADO), fecha, duración,
resolución, conteo de bloqueantes y advertencias. Secciones: Bloqueantes,
Advertencias, Checks pasados. Cada hallazgo: `[m:ss] Tipo — título`, detalle,
sugerencia y ruta a `evidencia/NN_MmSSs.jpg` (frame recortado con la caja
resaltada cuando aplica). Orden: severidad, luego timestamp.

### 5.2 Google Sheet `Tablero Revision`

Columnas: `Video | Fecha | Estado | Bloqueantes | Advertencias | Reporte | Video | Duración`.
Estados: `⏳` procesando, `🟢`, `🔴`, `❌ Error` (motivo en columna Reporte).
Una fila por nombre de video (upsert). Escritura vía `gspread` con cuenta de
servicio de Google Cloud con permiso de editor sobre el Sheet. Links a Drive:
se resuelven convirtiendo la ruta local a URL de Drive mediante la API de Drive
(misma cuenta de servicio, permiso de lectura sobre la carpeta); si no está
disponible, se escribe la ruta relativa.

### 5.3 Gate

- 0 bloqueantes → carpeta `03_Aprobado/<video>/`.
- ≥ 1 bloqueante → `02_Con_errores/<video>/`.
- Error de procesamiento → el video permanece en `01_Entrada/`, Sheet `❌ Error`.

## 6. Manejo de errores

- Sin audio: se omite Whisper, se agrega warning "video sin audio", siguen los
  checks visuales.
- Sheet inaccesible: se completan reporte y movimiento; la fila se reintenta en
  el siguiente ciclo (cola de pendientes en `~/.videoqa/sheet_pending.json`).
- Archivo corrupto / ffprobe falla: estado `❌ Error`, permanece en Entrada.
- Claude: ver 3.5.
- Todo se registra en `~/.videoqa/videoqa.log` con rotación.

## 7. Stack y estructura del proyecto

- Python 3.12, `uv`; `ffmpeg` (Homebrew); `mlx-whisper`; `ocrmac`; `numpy`,
  `pillow`; `pyspellchecker` + diccionario ES; `gspread`,
  `google-auth`; `watchdog`; `pyyaml`; `colormath` o implementación propia de
  ΔE2000.
- Claude Code CLI (`claude -p --output-format json`).

```
videoeditorpipeline/
├── videoqa/
│   ├── __init__.py
│   ├── cli.py            # `videoqa run <video>`, `videoqa watch`, `videoqa brand`
│   ├── config.py         # rutas, reglas.yaml, brand.json
│   ├── watcher.py        # watchdog + estabilidad de archivo + cola
│   ├── job.py            # job dir, estado por etapa, idempotencia
│   ├── stages/
│   │   ├── probe.py
│   │   ├── transcribe.py
│   │   ├── technical.py
│   │   ├── frames.py
│   │   ├── ocr.py
│   │   └── color.py
│   ├── checks/
│   │   ├── spelling.py
│   │   ├── brand_color.py
│   │   ├── timing.py     # visible <1 s, desync, zona tapada
│   │   └── technical.py  # negro/congelado/silencio/aspecto
│   ├── judge.py          # invoca claude -p, valida esquema
│   ├── brand.py          # PDF → brand.json vía claude
│   ├── report.py         # reporte.md + evidencia/
│   ├── gate.py           # mueve carpetas
│   └── sheet.py          # gspread upsert + cola pendiente
├── .claude/skills/revisor-video/SKILL.md
├── reglas.yaml
├── launchd/com.videoqa.watcher.plist
├── tests/
│   ├── unit/             # un archivo por check
│   ├── fixtures/         # videos sintéticos generados con ffmpeg
│   └── integration/      # pipeline completo contra fixtures
├── docs/
└── pyproject.toml
```

## 8. Estrategia de pruebas

- **Unitarias** por check con datos fabricados (OCR con "Aprobecha" → blocker;
  `#FF3B30` contra paleta → blocker; texto a 0.6 s → warning; caja en banda
  inferior → warning).
- **Fixtures sintéticos**: script `tests/fixtures/make_fixtures.py` genera con
  ffmpeg 3–4 videos de 10–15 s: (a) texto mal escrito en color prohibido,
  (b) pantalla negra de 1 s en el medio, (c) limpio, (d) sin audio. Audio de
  voz sintetizada con `say` de macOS para que Whisper tenga qué transcribir.
- **Integración**: pipeline completo contra fixtures con el juez Claude
  sustituido por un stub que devuelve JSON fijo; y una variante opcional con
  Claude real marcada `@slow`.
- **Aceptación**: 2–3 reels reales ya revisados por la revisora; se compara el
  reporte con sus anotaciones y se ajustan `reglas.yaml` y el skill.

## 9. Fuera de alcance (esta fase)

- Versionado v1/v2 y comparación de hallazgos entre versiones.
- Notificaciones (WhatsApp/Telegram/Slack).
- Publicación automática en Meta/TikTok.
- Ejecución en servidor/nube.
