# Aura — revisa tus videos antes de publicarlos

Aura es la forma de hablar con **VideoQA**: le pides las cosas en castellano y ella revisa cada
video antes de que salga. Mira la ortografía del texto en pantalla, los colores de la marca, que
lo que se dice coincida con lo que se escribe, los silencios, las pantallas en negro y las tomas
fallidas. Te devuelve **qué corregir y en qué segundo**, con una foto del momento exacto.

No hace falta saber nada técnico. Aura instala y maneja el motor por ti.

## Instalación

**Sin terminal (recomendado).** Con la app de Claude abierta, en la pestaña *Code*:

1. Escribe `/plugin` y pulsa Enter. Se abre el gestor de plugins.
2. Elige **Add marketplace** y escribe `hongs05/videoqa`.
3. En la lista, elige **aura** e instálalo.
4. Escribe `/aura:instalar`.

**Con terminal**, si lo prefieres:

```bash
claude plugin marketplace add hongs05/videoqa
claude plugin install aura@videoqa
```

`/aura:instalar` es la configuración guiada: instala lo que falte (Homebrew, `uv`, `ffmpeg`),
trae el motor a `~/videoqa`, te pregunta cuál es la carpeta de videos de Google Drive, carga tu
guía de marca y hace una revisión de prueba. Tarda unos minutos y te va contando qué hace.

## Comandos

| Comando | Para qué sirve |
| --- | --- |
| `/aura:instalar` | Deja todo configurado la primera vez: motor, carpeta de Drive, guía de marca y prueba. |
| `/aura:revisar` | Revisa los videos pendientes (o el que le digas) y te explica qué corregir y en qué segundo. |
| `/aura:estado` | Te dice qué hay pendiente, cómo quedaron los últimos y si la revisión automática está encendida. |
| `/aura:ajustar` | Añade palabras que no debe marcar como error y cambia qué problemas bloquean la publicación. |
| `/aura:activar-automatico` | Enciende (o apaga) la revisión automática de todo lo que subas a `01_Entrada`. |
| `/aura:actualizar` | Pone el motor y los comandos al día, y te cuenta qué cambió. |

**No hace falta escribir los comandos.** Puedes pedirlo con tus propias palabras: «revisa los
videos nuevos», «¿cómo va la cola?», «no marques la palabra Kasa», «activa la revisión
automática». Aura entiende igual.

Al abrir cada sesión, Aura te saluda con una línea de estado: si el motor está instalado, cuántos
videos hay esperando y si la revisión automática está encendida.

## Las tres carpetas

Dentro de la carpeta de Drive que elijas:

- **01_Entrada** — aquí subes los videos. Es lo único que tocas.
- **02_Con_errores** 🔴 — hay algo que corregir antes de publicar.
- **03_Aprobado** 🟢 — listo. Solo de aquí se publica.

## Actualizar

Escribe `/aura:actualizar` y ya está: trae la última versión del motor, actualiza los comandos y
te resume en dos frases qué cambió.

## Requisitos

- Mac con chip Apple (M1, M2, M3…), macOS 14 o superior.
- Google Drive para escritorio, con la carpeta del equipo sincronizada.
- Claude Code con la sesión iniciada (plan Pro o Max).
- Homebrew, `uv` y `ffmpeg`: los instala `/aura:instalar` si faltan (te pedirá la contraseña de
  la Mac para Homebrew). A mano sería `brew install uv ffmpeg`.
- Unos 10 GB libres: la primera revisión descarga un modelo de voz de ~1,5 GB.

## Licencia y contacto

MIT. Código y novedades: https://github.com/hongs05/videoqa
