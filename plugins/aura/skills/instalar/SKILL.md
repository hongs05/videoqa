---
description: Deja VideoQA listo la primera vez - instala el motor, elige la carpeta de videos de Drive, carga la guía de marca y hace una prueba. Úsalo cuando la persona diga "instalar", "configurar" o "empezar".
disable-model-invocation: true
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Bash(uv sync:*) Bash(uv python:*) Bash(git clone:*) Bash(git -C:*) Bash(osascript:*) Bash(cp:*) Bash(mkdir:*) Bash(sysctl:*) Bash(command -v:*) Bash(open:*) Bash(cat:*) Read Edit Write
---

# Instalar VideoQA (primera vez)

Guía a la persona paso a paso. Es alguien **no técnica**: habla en español informal (tú), frases
cortas, sin jerga. No muestres comandos, ni rutas largas, ni errores en crudo. Di qué estás
haciendo en una línea y sigue.

El motor de VideoQA vive siempre en la carpeta `~/videoqa`. Todos los comandos se lanzan así:
`uv run --project ~/videoqa videoqa …`. No importa desde dónde esté abierto Claude.

## Paso 1 — Revisar la Mac

```bash
uname -m                 # tiene que decir arm64
sysctl -n hw.memsize     # memoria en bytes
df -h ~ | tail -1        # espacio libre
```

- Si `uname -m` no es `arm64`: dile que esta herramienta solo funciona en Macs con chip Apple
  (M1, M2, M3…) y detente ahí.
- Si quedan menos de 10 GB libres: avísale de que conviene liberar espacio antes de seguir
  (el modelo de voz ocupa alrededor de 1,5 GB) y pregunta si quiere continuar igual.

## Paso 2 — Revisar los programas necesarios

```bash
command -v brew; command -v uv; command -v ffmpeg; command -v claude
```

Si falta **cualquiera** de los cuatro, detente y dile exactamente esto:

> Falta instalar algunos programas base. Cierra esta ventana, busca el archivo
> **"Instalar VideoQA.command"** en la carpeta que te pasaron y haz doble clic. Cuando termine,
> vuelve aquí y escribe `/aura:instalar` otra vez.

No intentes instalarlos tú.

## Paso 3 — Traer el motor a `~/videoqa`

Si `~/videoqa` **no existe**, tráelo de internet:

```bash
git clone https://github.com/hongs05/videoqa ~/videoqa
```

Si ya existe, solo actualízalo (si falla, no es grave: sigue con lo que hay):

```bash
git -C ~/videoqa pull --ff-only
```

Si la persona te dice que tiene el motor en una carpeta suya (por ejemplo una copia que le
pasaron en un disco), pídele la ruta y cópiala con `rsync -a --exclude .venv --exclude .git
"<ruta>/" ~/videoqa/` en vez de clonar. Puede que te pida permiso una vez; es normal.

Luego prepara Python y las librerías. Avisa que esto tarda un par de minutos:

```bash
uv python install 3.12
uv sync --project ~/videoqa
```

## Paso 4 — Permisos para no estar preguntando todo el rato

Dile, en una sola frase: "Para no tener que pedirte permiso cada vez que reviso un video, voy a
dejar aprobados de antemano los comandos de VideoQA. ¿Lo hago?"

Con el sí, lee `~/.claude/settings.json` (si no existe, créalo) y **añade** a
`permissions.allow` estas cuatro entradas, sin borrar ni tocar nada de lo que ya hubiera, y sin
duplicar las que ya estén:

```
Bash(uv run --project ~/videoqa videoqa:*)
Bash(open:*)
Bash(ls:*)
Bash(launchctl:*)
```

Si dice que no, sigue igual: solo te va a pedir permiso más veces.

## Paso 5 — Elegir la carpeta de videos

Pregúntale: "Te voy a abrir una ventana para que elijas la carpeta de videos, la que está dentro
de Google Drive. ¿Listo?". Cuando diga que sí:

```bash
osascript -e 'POSIX path of (choose folder with prompt "Elige la carpeta de videos (la de Drive)")'
```

Si cancela la ventana, el comando falla: no muestres el error, solo pregúntale si quiere
intentarlo otra vez.

Con la ruta que devuelva:

```bash
uv run --project ~/videoqa videoqa init --drive-root "<ruta elegida>"
```

Dile en plano: "Listo. Dentro de esa carpeta creé tres subcarpetas: **01_Entrada** (ahí suben los
videos), **02_Con_errores** y **03_Aprobado**."

## Paso 6 — Ajustar el modelo de voz a la memoria de la Mac

Si `hw.memsize` es **8 GB o menos** (8589934592 bytes o menos), añade o cambia esta línea en
`~/.videoqa/config.yaml` (usa Read + Edit, no borres las demás líneas):

```yaml
whisper_model: mlx-community/whisper-small-mlx
```

Explícalo así: "Como tu Mac tiene 8 GB de memoria, dejé un modelo de voz más liviano. Va un poco
menos fino con el acento, pero no se traba."

Si tiene más memoria, no toques nada y no lo menciones.

## Paso 7 — Guía de marca

Pregunta: "¿Tienes la guía de marca en PDF? (colores, tipografías, reglas). Si no, no pasa nada,
seguimos con una de ejemplo y la cambias después."

**Si dice que sí:**

```bash
osascript -e 'POSIX path of (choose file with prompt "Elige la guía de marca en PDF")'
mkdir -p "<carpeta de videos>/_config"
cp "<ruta del pdf>" "<carpeta de videos>/_config/guia_de_marca.pdf"
uv run --project ~/videoqa videoqa brand
```

Esto tarda un par de minutos. Avísale antes. Al terminar, dile cuántos colores y cuántas reglas
quedaron cargados (el comando lo imprime).

**Si dice que no:**

```bash
mkdir -p "<carpeta de videos>/_config"
cp ~/videoqa/tests/fixtures/brand.json "<carpeta de videos>/_config/brand.json"
```

Y explícale: "Dejé una marca de ejemplo para que puedas probar. Cuando tengas el PDF de la guía,
dímelo y lo cargamos de verdad — mientras tanto, los avisos de color no van a servirte mucho."

## Paso 8 — Comprobar que Claude tiene sesión iniciada

La revisión de criterio necesita que Claude esté instalado y con la sesión abierta. Si estás
hablando con la persona dentro de Claude, la sesión ya está iniciada: basta con confirmar que el
programa está donde debe.

```bash
command -v claude
```

Si no aparece nada, dile: "Falta Claude Code. Haz doble clic en 'Instalar VideoQA.command' y
cuando termine, vuelve y escribe `/aura:instalar`." Y detente ahí.

Si más adelante algún video vuelve con "la revisión de criterio no se pudo hacer", es que la
sesión caducó: ábrele una Terminal con `open -a Terminal`, dile que escriba ahí `claude` y siga
los pasos en el navegador, y que luego vuelva.

## Paso 9 — Prueba

Si existe `~/videoqa/tests/fixtures/out/clean.mp4`:

```bash
uv run --project ~/videoqa videoqa run ~/videoqa/tests/fixtures/out/clean.mp4
```

Avisa antes: "Voy a revisar un video de prueba. La primera vez descarga el modelo de voz, así que
puede tardar varios minutos. Es solo esta vez."

Si el archivo no existe, salta este paso sin mencionarlo.

Cuando termine, abre la carpeta del resultado en Finder:

```bash
open "<carpeta del resultado>"
```

## Paso 10 — Cierre

Dile qué puede hacer a partir de ahora, con estas palabras:

> Ya está todo listo. A partir de ahora:
> - Sube los videos a **01_Entrada** dentro de la carpeta de Drive.
> - Escríbeme **"revisa los videos nuevos"** y te digo cómo quedaron.
> - Si quieres que lo haga solo, sin pedírmelo, dime **"activa la revisión automática"**.

## Cómo explicar el resultado

- Usa el semáforo: 🟢 aprobado / 🔴 no aprobado. Nunca digas "rejected" ni "blocker".
- Cada problema se explica en tres partes: **qué corregir**, **en qué segundo** y, si hay foto,
  "abre la foto de evidencia".
- **Nunca muestres un traceback, un error de Python ni una salida técnica en crudo.** Si algo
  falla, resume en una frase qué pasó y propón el siguiente paso concreto. Ejemplos:
  - Modelo de voz no descarga → "No pude descargar el modelo de voz, parece cosa de internet.
    ¿Lo intentamos de nuevo?"
  - Claude sin sesión → "Claude no tiene la sesión iniciada. Vamos a hacer el login otra vez."
  - Carpeta de Drive sin sincronizar → "Google Drive todavía está sincronizando esa carpeta.
    Espera a que termine y me dices."
- Para mostrar archivos, usa `open <carpeta>` y di "te lo abrí en Finder".
