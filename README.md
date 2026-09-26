# VideoQA

Revisión automática de videos verticales (reels, TikToks) **antes** de publicarlos: ortografía
del texto en pantalla, colores de la marca, coincidencia entre lo que se dice y lo que se
escribe, silencios, pantallas en negro, tomas fallidas y problemas técnicos. El resultado es un
informe con **qué corregir y en qué segundo**, con una foto del momento exacto.

Este repositorio contiene las dos mitades: el motor (`videoqa`, Python) y el plugin de Claude
Code con el que lo maneja una persona no técnica (`aura`).

## Arquitectura en cinco líneas

1. **Entrada** — los videos se suben a `01_Entrada` en una carpeta de Google Drive sincronizada.
2. **Extracción** — `ffmpeg` saca frames y audio; Whisper (MLX) transcribe; Vision hace el OCR.
3. **Chequeos de código** — ortografía (NSSpellChecker), color de marca, formato, silencios,
   pantallas en negro, congelados, subtítulos y texto tapado.
4. **Criterio** — Claude juzga los casos que el código no puede decidir (guion ↔ pantalla,
   bloopers) con el skill `.claude/skills/revisor-video/SKILL.md`.
5. **Salida** — el video se mueve a `02_Con_errores` o `03_Aprobado` con `reporte.md`,
   `guion_real.md` y `evidencia/`; opcionalmente se anota en un Google Sheet. Nunca se borra
   un video: si ya había una entrega con el mismo nombre, se aparta en `_anteriores/`.

## Por dónde empezar

| Si eres… | Lee |
| --- | --- |
| quien revisa los videos | [`LEEME.md`](LEEME.md) — cómo se usa, en castellano y sin tecnicismos |
| quien instala el plugin | [`plugins/aura/README.md`](plugins/aura/README.md) — comandos e instalación |
| quien mantiene el motor | [`docs/SETUP.md`](docs/SETUP.md) — instalación manual, launchd, Sheet |

## Estructura

```
videoqa/                 motor (pipeline, checks, CLI `videoqa`)
reglas.yaml              umbrales y gravedad de cada tipo de problema
.claude/skills/          revisor-video: el criterio con el que Claude juzga cada video
plugins/aura/            plugin de Claude Code (skills, hook, scripts)
.claude-plugin/          marketplace "videoqa", desde el que se instala aura
instalar/                instalador de doble clic para macOS
launchd/                 agente para la revisión automática
tests/                   unitarios e integración
```

## Desarrollo

```bash
uv sync
uv run pytest tests/unit -q
claude plugin validate plugins/aura
```

MIT. Ver [`LICENSE`](LICENSE).
