---
description: Pone VideoQA al día con la última versión y te cuenta en claro qué cambió. Úsalo cuando la persona diga "actualiza", "hay versión nueva", "ponlo al día" o "instala la última versión".
disable-model-invocation: true
allowed-tools: Bash(git -C:*) Bash(bash:*) Bash(ls:*) Bash(uv sync:*) Bash(launchctl kickstart:*) Bash(claude plugin update:*) Read
---

# Actualizar VideoQA

Habla en español informal (tú), sin jerga. Avisa al empezar: "Voy a ponerlo todo al día. Tarda un
par de minutos."

El motor vive en `~/videoqa`. Si esa carpeta no existe, dile "Todavía no está instalado: escribe
`/aura:instalar`" y termina.

**Nunca des por perdida la actualización del motor.** Si la carpeta del motor no está enlazada con
internet, el paso 2 la enlaza. No le digas a la persona que no se puede.

## Paso 1 — Apuntar en qué versión estamos

```bash
git -C ~/videoqa rev-parse HEAD
```

Guarda ese valor: lo vas a necesitar al final para contar qué cambió. No se lo enseñes a la
persona. Si el comando falla, no pasa nada: sigue igual, solo que al final no podrás contar qué
cambió.

## Paso 2 — Asegurarte de que el motor puede recibir versiones nuevas

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/enlazar-motor.sh"
```

(Si esa ruta no existiera, localiza el archivo con
`ls -d ~/.claude/plugins/cache/videoqa/aura/*/scripts/enlazar-motor.sh | tail -1` y lánzalo.)

Ese script no pierde nada de lo que hubiera en la carpeta ni sube nada a ningún sitio. Mira la
**primera palabra** de la respuesta:

- `ya-enlazado` — todo normal. Sigue al paso 3.
- `enlazado` — la copia del motor no estaba enlazada con internet (se la pasaron como carpeta) y
  acaba de quedarse al día. Sáltate el paso 3 y dilo en una línea: "Tu copia del motor no estaba
  enlazada con internet, así que se había quedado atrás. Ya la enlacé y tiene la versión nueva."
- `enlazado-con-copia` — lo mismo, pero además la carpeta tenía cambios hechos a mano. Están
  guardados en esta Mac antes de poner la versión nueva. Sáltate el paso 3 y dilo así: "Esa copia
  tenía cambios propios. Los dejé guardados aquí en tu Mac por si hacen falta, y encima puse la
  versión nueva. Si esos cambios eran importantes, avisa a quien te pasó la herramienta."
- `sin-internet` — "No pude descargar la versión nueva, parece cosa de la conexión. ¿Lo intentamos
  otra vez?" Y termina.
- `no-instalado` — "Todavía no está instalado: escribe `/aura:instalar`." Y termina.
- `error` — resume en una frase que no se pudo preparar la carpeta del motor y que avise a quien le
  pasó la herramienta. Y termina.

## Paso 3 — Traer la versión nueva del motor

Solo si el paso 2 dijo `ya-enlazado`:

```bash
git -C ~/videoqa pull --ff-only
```

Si dice que ya está al día, díselo en una línea ("El motor ya estaba en la última versión") y
sigue igual con el paso 5.

## Paso 4 — Volver a preparar las librerías

```bash
uv sync --extra macos --project ~/videoqa
```

## Paso 5 — Actualizar los comandos de Aura

```bash
claude plugin update aura
```

Si responde que no está instalado como plugin, no pasa nada: sáltalo sin mencionarlo.

## Paso 6 — Reiniciar la revisión automática si estaba encendida

```bash
launchctl kickstart -k gui/$UID/com.videoqa.watcher
```

Si responde que no existe el servicio, es que la automática está apagada: no es un error, no lo
menciones. Si sí se reinició, dilo: "Reinicié la revisión automática para que use lo nuevo."

## Paso 7 — Contar qué cambió

Solo si el paso 1 te dio una versión de partida:

```bash
git -C ~/videoqa log --oneline <versión del paso 1>..HEAD
```

Traduce esa lista a dos o tres frases en castellano llano. Agrupa por tema (qué se arregló, qué
es nuevo) y quédate con lo que le cambia algo a quien revisa videos. **Nunca muestres los códigos
de commit, ni los prefijos tipo `fix:` o `feat:`, ni nombres de archivos.**

Ejemplo:

> ✅ Listo, ya estás en la última versión.
>
> Lo que cambia para ti:
> - Ahora detecta mejor el texto tapado por los iconos de TikTok.
> - Los silencios al final del video ya no se marcan como error.
>
> Reinicié la revisión automática para que use lo nuevo.

Si no hubo cambios, una línea: "Ya estabas en la última versión, no había nada nuevo." Si el
comando falla o no tenías versión de partida, no lo intentes otra vez: di solo que ya está en la
última versión.

## Cómo explicar el resultado

- Nada de jerga: ni "commit", ni "repositorio", ni "dependencias", ni rutas.
- Si algo falla, resume la causa en una frase y propón el siguiente paso. Nada de tracebacks.
  Lo habitual es que sea internet: "No pude descargar la versión nueva, parece cosa de la
  conexión. ¿Lo intentamos otra vez?"
