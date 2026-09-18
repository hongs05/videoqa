# VideoQA — Instalación y operación

## Instalación para no técnicos

Si quien instala no es técnico, no hace falta nada de lo que sigue ni pasar por la Terminal:

1. Instalar la app de **Claude** (claude.ai/download), iniciar sesión, pestaña **Code**.
2. `/plugin` → *Add marketplace* → `hongs05/videoqa` → instalar **aura**. (Equivalente por
   terminal: `claude plugin marketplace add hongs05/videoqa && claude plugin install aura@videoqa`.)
3. Escribir **`/aura:instalar`** — configuración guiada: instala Homebrew/`uv`/`ffmpeg`/CLI si
   faltan, clona el motor en `~/videoqa`, prepara Python, elige la carpeta de Drive, ajusta el
   modelo de voz según la RAM, carga la guía de marca y hace una prueba.

El paquete `VideoQA-demo.zip` (`bash scripts/build_demo_zip.sh`) con `Instalar VideoQA.command`
sigue existiendo como alternativa para Macs donde ni siquiera esté la app de Claude.

A partir de ahí se opera hablando: `/aura:revisar`, `/aura:estado`, `/aura:ajustar`,
`/aura:activar-automatico`, `/aura:actualizar` (ver `plugins/aura/README.md`). La guía para el
equipo está en `LEEME.md`.

**Convención de rutas:** el motor instalado vive siempre en `~/videoqa` y todo se ejecuta como
`uv run --project ~/videoqa videoqa …`. Este repositorio es ese mismo motor más el marketplace y
el plugin; en desarrollo se trabaja desde su raíz con `uv run videoqa …`.

El resto de este documento es la instalación manual, paso a paso.

## Requisitos
- Mac con Apple Silicon, macOS 14+.
- Google Drive para escritorio con la carpeta del equipo sincronizada (modo "Stream" o "Mirror").
- Claude Code instalado y con sesión iniciada (`claude` en la terminal, plan Pro/Max).
- Homebrew.
- El pipeline en sí funciona con el `ffmpeg` normal de Homebrew. Si además necesitas
  **regenerar los fixtures de prueba sintéticos** (`tests/fixtures/make_fixtures.py`), esos
  usan el filtro `drawtext`, que no viene en el build por defecto de `ffmpeg` de Homebrew en
  esta máquina — instala `brew install ffmpeg-full` para eso.

## 1. Instalar
```bash
brew install uv ffmpeg
git clone https://github.com/hongs05/videoqa ~/videoqa
uv sync --project ~/videoqa
```

## 2. Configurar
Localiza la carpeta sincronizada, por ejemplo
`~/Library/CloudStorage/GoogleDrive-<cuenta>/Shared drives/<Equipo>/Revision_Videos`.

```bash
uv run --project ~/videoqa videoqa init --drive-root "<ruta a Revision_Videos>"
```
Esto crea `_config/`, `01_Entrada/`, `02_Con_errores/`, `03_Aprobado/` y `~/.videoqa/config.yaml`.

Copia la guía de marca a `_config/guia_de_marca.pdf` (Canva → Descargar → PDF) y, opcionalmente,
crea `_config/glosario.txt` con una palabra por línea (nombres propios, marcas, jerga válida).

Genera la paleta y reglas (usa Claude una sola vez; revisa el resultado a mano si quieres):
```bash
uv run --project ~/videoqa videoqa brand
cat "<ruta a Revision_Videos>/_config/brand.json"
```
`_config/brand.json` es un archivo de texto plano: también puedes editarlo a mano (por ejemplo,
para ajustar un color de paleta o añadir una regla) sin volver a correr `videoqa brand`.

## 3. Google Sheet (opcional)
1. En Google Cloud Console: crear proyecto → habilitar **Google Sheets API** → crear **cuenta de
   servicio** → generar clave JSON → guardarla en `~/.videoqa/service_account.json`.
2. Crear un Sheet llamado `Tablero Revision` y compartirlo (Editor) con el email de la cuenta de servicio.
3. Copiar el ID del Sheet (parte de la URL entre `/d/` y `/edit`) y re-ejecutar:
```bash
uv run --project ~/videoqa videoqa init --drive-root "<ruta>" --sheet-id <ID> --service-account ~/.videoqa/service_account.json
```

## 4. Probar con un video
```bash
uv run --project ~/videoqa videoqa run "<ruta a Revision_Videos>/01_Entrada/mi_video.mp4"
```
La primera vez descarga el modelo de Whisper (~1.5 GB). El resultado queda en `02_Con_errores/` o
`03_Aprobado/` con `reporte.md`, `guion_real.md` y `evidencia/`.

## 5. Dejarlo corriendo solo (launchd)
Antes de instalarlo como agente, conviene probar el watcher a mano una vez:
```bash
uv run --project ~/videoqa videoqa watch --once
```
Luego instala el agente:
```bash
sed -e "s|__HOME__|$HOME|g" -e "s|__PROJECT__|$HOME/videoqa|g" -e "s|__UV__|$(command -v uv)|g" \
  ~/videoqa/launchd/com.videoqa.watcher.plist > ~/Library/LaunchAgents/com.videoqa.watcher.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.videoqa.watcher.plist
```
> **El agente tiene que correr en la sesión gráfica** (`gui/$UID`, que es lo que hace
> `bootstrap`), no como demonio de sistema: el OCR usa el framework **Vision** y la ortografía
> usa **NSSpellChecker**, y ambos necesitan una sesión de usuario con ventanas iniciada. Con
> `launchctl load` (obsoleto) o en un dominio sin GUI, el OCR devuelve vacío y el corrector da
> por buena cualquier palabra. Corolario: la Mac debe estar encendida y con la sesión abierta
> (basta con la pantalla bloqueada; no sirve cerrar sesión).

Ver estado / logs:
```bash
launchctl print gui/$UID/com.videoqa.watcher | head -20
tail -f ~/.videoqa/videoqa.log
```
Detener:
```bash
launchctl bootout gui/$UID/com.videoqa.watcher
```

## Regla del equipo
Solo se publica lo que está en `03_Aprobado/`. Si un video cae en `02_Con_errores/`, el editor
corrige, vuelve a subir el archivo a `01_Entrada/` con el mismo nombre y espera el nuevo reporte.

## Ajustar severidades
Edita `~/videoqa/reglas.yaml` (por ejemplo, `silence: blocker`) y reinicia el watcher. Para cambiar el criterio
de Claude, edita `~/videoqa/.claude/skills/revisor-video/SKILL.md`.

## Problemas comunes
- **El video no se procesa**: ¿está la Mac encendida y Drive terminó de sincronizar? Mira `videoqa.log`.
- **`❌ Error` en el Sheet**: la columna Reporte tiene el motivo. Si es Claude (límite de uso), el
  video queda en `02_Con_errores/` con reporte parcial; resúbelo más tarde.
- **Falsos positivos de ortografía**: añade la palabra a `_config/glosario.txt`.
