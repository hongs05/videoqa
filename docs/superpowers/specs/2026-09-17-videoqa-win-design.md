# Diseño: VideoQA para Windows (`videoqa-win`)

Fecha: 2026-09-17
Estado: aprobado en conversación, pendiente de plan de implementación
Spec del motor: `docs/superpowers/specs/2026-09-11-video-qa-pipeline-design.md`

## 1. Objetivo

Que los editores del equipo puedan hacer un **pre-chequeo local** de sus videos en sus PCs con
Windows, sin cuenta de ninguna IA estadounidense y sin depender de la Mac de la revisora. El
gate oficial de publicación sigue siendo uno solo: la Mac.

## 2. Contexto y restricciones

- El equipo está en Venezuela. **Anthropic no soporta Venezuela** (verificado en
  anthropic.com/supported-countries: no aparece en la lista) y **OpenAI tampoco**
  (help.openai.com, países no soportados). No hay suscripción ni API posible, y rodear el
  bloqueo con VPN viola los términos: queda descartado.
- Hardware de referencia (Editor 1, "Ayrton"): AMD Ryzen 5 7535HS, 24 GB RAM, NVIDIA RTX 2050
  (4 GB VRAM), Windows 64-bit. Otros editores pueden no tener GPU dedicada.
- Internet inestable: el instalador descarga, pero debe reintentar y ser re-ejecutable.
- Los usuarios no son técnicos y pueden no tener permisos de administrador.
- El motor `videoqa` depende hoy de tres cosas exclusivas de macOS, y solo de tres:
  `videoqa/stages/ocr.py` (Apple Vision vía `ocrmac`), `videoqa/stages/transcribe.py`
  (`mlx_whisper`) y `videoqa/checks/spelling.py` (`NSSpellChecker` vía pyobjc). Todo lo demás
  (ffprobe/ffmpeg, color, checks, juez, reporte, gate, watcher, CLI) ya es multiplataforma.

## 3. Arquitectura

Dos proyectos, uno depende del otro:

```
hongs05/videoqa                        hongs05/videoqa-win
┌───────────────────────────┐          ┌──────────────────────────────┐
│ motor (paquete Python)    │◄─────────│ depende de videoqa (git)     │
│  stages, checks, judge,   │  pip     │  backends: RapidOCR,         │
│  report, gate, watcher    │          │   faster-whisper, spylls     │
│  backends/ (contratos)    │          │  interfaz Windows (.bat)     │
│  extra [macos]            │          │  reporte HTML                │
│ plugin aura (Claude Code) │          │  instalador + diagnóstico    │
└───────────────────────────┘          │  juez Ollama (opcional)      │
        Mac de la revisora             └──────────────────────────────┘
        = gate oficial                      PCs de los editores
                                            = pre-chequeo local
```

Las dos instalaciones **nunca** comparten carpeta: `videoqa-win` trabaja sobre una carpeta local
del editor; la Mac sobre la de Drive (§7 del spec del motor). No hay coordinación ni bloqueos
entre ellas.

## 4. Cambios en el motor (`videoqa`)

Mínimos y compatibles hacia atrás:

1. **Dependencias de Apple opcionales.** `mlx-whisper`, `ocrmac` y `pyobjc-framework-Cocoa`
   salen de `dependencies` y pasan a `[project.optional-dependencies] macos = [...]`. En la Mac
   se instala `videoqa[macos]`; en Windows, `videoqa`. Los tres módulos ya importan dentro de la
   función, así que en Windows no se ejecutan nunca. `instalar/install.sh` y la skill
   `/aura:instalar` pasan a usar el extra.
2. **Registro de backends.** Nuevo módulo `videoqa/backends.py` con tres huecos y su valor por
   defecto:
   ```python
   register_ocr(fn)        # fn(path: Path) -> list[dict]   {text, conf, bbox}
   register_transcriber(fn)# fn(job, has_audio, model) -> dict {language, text, segments}
   register_speller(fn)    # fn() -> objeto con is_known/unknown/correction
   ```
   `videoqa/stages/ocr.py`, `transcribe.py` y `checks/spelling.py` consultan el registro; si no
   hay nada registrado, usan la pila de Apple como hoy (comportamiento idéntico en la Mac).
3. **El prompt del juez viaja dentro del paquete.** Hoy `SKILL_PATH` apunta a
   `.claude/skills/revisor-video/SKILL.md`, fuera del paquete: al instalarse con pip no existe.
   Se copia a `videoqa/prompts/revisor-video.md` (incluido como *package data*) y `SKILL_PATH`
   pasa a resolverse ahí, con la ruta del repo como respaldo en desarrollo. El archivo de
   `.claude/skills/` se mantiene como el que lee Claude Code, generado desde el mismo origen
   para que no se desincronicen (un test compara los dos).
4. **Reporte HTML** (`videoqa/report_html.py`): genera `reporte.html` junto al `reporte.md`,
   con el semáforo, los hallazgos y **las fotos de evidencia incrustadas**. Sirve a las dos
   plataformas; en la Mac es opcional (`reporte_html: true` en `reglas.yaml`), en Windows va
   activado por defecto.

## 5. Backends de `videoqa-win`

Todas las piezas son *pip* puro, sin PyTorch y sin compilar nada:

| Contrato | Implementación | Notas |
|---|---|---|
| OCR | **RapidOCR** (`rapidocr-onnxruntime`) | Modelos ~15 MB. Devuelve caja de 4 puntos → se convierte a `[x, y, w, h]` normalizado, origen arriba-izquierda |
| Transcripción | **faster-whisper** (CTranslate2) | `small` int8 por defecto; `medium` si hay GPU NVIDIA. Sin PyTorch |
| Corrector | **spylls** + diccionario `es_ES` de LibreOffice | Hunspell en Python puro. `correction()` = sugerencias de spylls, primera opción |

Cada backend se valida contra el mismo material que la pila de Apple: los fixtures sintéticos y
el video real de la prueba (subtítulos blancos con contorno, "Aprobecha" mal escrito, marca de
agua). Los umbrales de `reglas.yaml` no cambian: si un backend necesita otro umbral, se ajusta
en el backend, no en las reglas, para que "revisar" signifique lo mismo en las dos máquinas.

Diferencias conocidas y aceptadas:
- La confianza de RapidOCR no es comparable numéricamente con la de Apple Vision. El umbral
  `ocr_min_conf` (0.5) se recalibra para RapidOCR en su backend y se documenta.
- `spylls` con el diccionario español acepta y rechaza palabras distintas que NSSpellChecker.
  Conviene mantener un `glosario.txt` propio en cada PC.

## 6. Interfaz en Windows

Carpeta de trabajo: `%USERPROFILE%\VideoQA\` con `01_Entrada`, `02_Con_errores`, `03_Aprobado` y
`_config` (misma estructura que en Drive, creada por el instalador).

Tres accesos directos en el Escritorio, todos `.bat`:

1. **`Revisar video.bat`** — arrastrar y soltar. Acepta uno o varios archivos como argumento;
   si se ejecuta sin argumentos, revisa lo pendiente en `01_Entrada`. Al terminar abre
   `reporte.html` en el navegador.
2. **`Activar automatico.bat`** — crea (o quita, si ya existe) un acceso directo al watcher en
   `shell:startup`, de modo que arranque al iniciar sesión. Sin permisos de administrador.
   Informa en qué estado quedó.
3. **`Diagnostico.bat`** — comprueba Python, ffmpeg, modelos, GPU, carpetas y permisos, corre el
   video de prueba y escribe `diagnostico.txt` en el Escritorio para que el editor lo mande por
   chat cuando algo falle.

Todos los mensajes en español, sin trazas de Python: los errores se resumen en una frase y se
registran en `%USERPROFILE%\VideoQA\registro.log`.

## 7. Instalador

`Instalar VideoQA.bat` (~50 KB, doble clic, re-ejecutable):

1. Comprueba Windows 10/11 de 64 bits.
2. Python 3.12 y ffmpeg: si faltan, los instala con `winget` (incluido en Windows 10 21H2+). Si
   `winget` no existe, indica en una frase qué descargar a mano y se detiene.
3. Crea el entorno en `%USERPROFILE%\VideoQA\.venv` e instala
   `videoqa @ git+https://github.com/hongs05/videoqa` más los backends.
4. Descarga los modelos (voz ~250 MB, OCR ~15 MB, diccionario ~5 MB) con reintentos; si la
   descarga se corta, se puede volver a ejecutar y continúa desde donde iba.
5. Detecta GPU NVIDIA (`nvidia-smi`): si la hay, instala el soporte CUDA de CTranslate2 y elige
   el modelo `medium`; si no, se queda en CPU con `small`.
6. Crea las carpetas, copia una guía de marca de ejemplo, crea los tres accesos directos y corre
   una revisión de prueba.

Actualizar: `Actualizar VideoQA.bat` (`pip install --upgrade` del paquete y de los backends).

## 8. Juez opcional (Ollama)

`juez: ninguno` por defecto en `config.yaml`. Con `juez: ollama`:
- Requiere Ollama instalado y el modelo `qwen2.5vl:3b` descargado (el instalador no lo hace:
  son ~3 GB y solo sirve a quien tenga GPU).
- Se implementa como un `Runner` (`(prompt, cwd) -> str`), que es la interfaz que el motor ya
  usa para Claude; el prompt es el mismo `revisor-video`, recortado a menos frames
  (`claude.max_frames: 6`) porque un 3B se pierde con quince imágenes.
- Documentado como experimental, con la advertencia de que el criterio es notablemente inferior
  al de Claude. Si el juez falla, el video queda en `02_Con_errores` con el aviso de
  "revisión de criterio pendiente", igual que en la Mac.

## 9. Manejo de errores

- Sin GPU o con CUDA roto: cae a CPU automáticamente y lo registra; nunca aborta.
- Modelo de voz ausente o corrupto: lo vuelve a descargar una vez; si falla, sigue con los
  checks visuales y añade el aviso "no se pudo transcribir".
- Video en uso por el editor de video (Windows bloquea el archivo): espera y reintenta, como ya
  hace el watcher con la sincronización de Drive.
- Rutas con espacios, acentos y ñ: todos los `.bat` citan las rutas y usan UTF-8 (`chcp 65001`).

## 10. Pruebas

- **Motor**: los 203 tests actuales siguen verdes en la Mac; se añaden los del registro de
  backends, el reporte HTML y la sincronía del prompt del juez.
- **`videoqa-win`**: unitarios por backend con datos fabricados (misma forma que los del motor),
  más integración sobre los fixtures sintéticos con el juez simulado.
- **Limitación explícita**: no hay Windows disponible en el entorno de desarrollo. Los backends
  se prueban en la Mac (RapidOCR, faster-whisper y spylls funcionan también en macOS), lo que
  valida la lógica; lo específico de Windows (los `.bat`, `winget`, el arranque automático) solo
  se verifica en la PC del editor. `Diagnostico.bat` es la herramienta para esa primera corrida.
- **Aceptación**: el video real de la prueba y los cuatro fixtures deben producir en Windows los
  mismos hallazgos que en la Mac (salvo las diferencias documentadas de §5).

## 11. Fuera de alcance

- Sustituir el gate oficial: sigue en la Mac.
- Google Sheet desde Windows (el pre-chequeo es personal, no necesita tablero).
- Notificaciones.
- Linux (el diseño lo permite, pero no se prueba ni se documenta).
- Empaquetado portable sin internet (se evaluó; se eligió instalador que descarga).
