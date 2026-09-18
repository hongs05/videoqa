---
description: Pone VideoQA al día con la última versión y te cuenta en claro qué cambió. Úsalo cuando la persona diga "actualiza", "hay versión nueva", "ponlo al día" o "instala la última versión".
disable-model-invocation: true
allowed-tools: Bash(git -C:*) Bash(uv sync:*) Bash(launchctl kickstart:*) Bash(claude plugin update:*) Read
---

# Actualizar VideoQA

Habla en español informal (tú), sin jerga. Avisa al empezar: "Voy a ponerlo todo al día. Tarda un
par de minutos."

El motor vive en `~/videoqa`. Si esa carpeta no existe, dile "Todavía no está instalado: escribe
`/aura:instalar`" y termina.

## Paso 1 — Apuntar en qué versión estamos

```bash
git -C ~/videoqa rev-parse HEAD
```

Guarda ese valor: lo vas a necesitar al final para contar qué cambió. No se lo enseñes a la
persona.

## Paso 2 — Traer la versión nueva del motor

```bash
git -C ~/videoqa pull --ff-only
```

Si dice que ya está al día, díselo en una línea ("El motor ya estaba en la última versión") y
sigue igual con el paso 4.

Si falla porque hay cambios locales, no fuerces nada: dile "Alguien tocó los archivos del motor a
mano, así que prefiero no pisarlo. Avisa a quien te pasó la herramienta." Y termina.

## Paso 3 — Volver a preparar las librerías

```bash
uv sync --extra macos --project ~/videoqa
```

## Paso 4 — Actualizar los comandos de Aura

```bash
claude plugin update aura
```

Si responde que no está instalado como plugin, no pasa nada: sáltalo sin mencionarlo.

## Paso 5 — Reiniciar la revisión automática si estaba encendida

```bash
launchctl kickstart -k gui/$UID/com.videoqa.watcher
```

Si responde que no existe el servicio, es que la automática está apagada: no es un error, no lo
menciones. Si sí se reinició, dilo: "Reinicié la revisión automática para que use lo nuevo."

## Paso 6 — Contar qué cambió

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

Si no hubo cambios, una línea: "Ya estabas en la última versión, no había nada nuevo."

## Cómo explicar el resultado

- Nada de jerga: ni "commit", ni "repositorio", ni "dependencias", ni rutas.
- Si algo falla, resume la causa en una frase y propón el siguiente paso. Nada de tracebacks.
  Lo habitual es que sea internet: "No pude descargar la versión nueva, parece cosa de la
  conexión. ¿Lo intentamos otra vez?"
