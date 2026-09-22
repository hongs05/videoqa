---
description: Enseña a la revisión con tus correcciones. Úsalo cuando la persona diga "eso no es error", "esto no se marca" o "se le pasó X" sobre un video ya revisado.
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Read Edit Write
---

# Corregir la revisión

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin comandos a la vista.

Sirve para que la revisión **aprenda del equipo**. Cada corrección se guarda con su motivo y, en
los videos siguientes, Claude la tiene en cuenta en casos parecidos. No es una regla fija:
"el logo de la camiseta no es un error" le sirve para cualquier camiseta.

El motor vive en `~/videoqa`. Si esa carpeta no existe, dile "Todavía no está instalado:
escribe `/aura:instalar`" y termina.

## Paso 1 — Entender qué corrige

Hay dos casos:

- **"Eso no es error"**: algo que se marcó y está bien ("SUSHICD es el logo de la camiseta",
  "corillo es jerga nuestra", "el subtítulo en la parte de abajo está bien así").
- **"Se le pasó"**: un error que la revisión no vio ("el precio del rótulo no coincide con lo que
  dice", "en el segundo 20 se ve la ventana del editor").

Necesitas **el video** y **el motivo**. Si falta el motivo, pregúntalo en una frase ("¿Por qué no
es un error? Así lo aprende bien"). El motivo es lo más importante: es lo que Claude va a
aplicar a otros casos.

## Paso 2 — Encontrar el hallazgo (solo para "eso no es error")

```bash
uv run --project ~/videoqa videoqa hallazgos "<nombre o trozo del nombre del video>"
```

Cada línea es `[id] segundo GRAVEDAD · título — detalle`. Elige el que describe la persona.

- Si responde `VARIOS`, muéstrale los nombres y pregunta cuál.
- Si responde `NO_ENCONTRADO`, dile que ese video no aparece entre los revisados en esta Mac.
- Si varios hallazgos encajan (el mismo error en distintos segundos), corrige todos.
- Si ninguno encaja, dile qué encontraste en ese video y pregunta a cuál se refiere.

## Paso 3 — Confirmar y guardar

Resúmelo en una frase y pregunta: "Voy a enseñarle que **el logo SUSHICD de la camiseta no es
una falta de ortografía**, para que no lo vuelva a marcar en casos así. ¿Lo guardo?"

Con el sí:

- "Eso no es error":

```bash
uv run --project ~/videoqa videoqa corregir "<video>" --hallazgo <id> --motivo "<motivo en palabras de la persona>"
```

- "Se le pasó":

```bash
uv run --project ~/videoqa videoqa corregir "<video>" --no-detectado --motivo "<qué debió marcar y por qué>" --segundo <segundo, si lo sabe>
```

Confirma: "Listo, aprendido. Lo tendrá en cuenta desde el próximo video."

## Paso 4 — Si sugiere el glosario

Si la respuesta incluye `SUGERIR_GLOSARIO: palabra1, palabra2`, esa palabra ya se corrigió varias
veces. Ofrécelo: "**SUSHICD** ya me lo has corregido más de una vez. ¿La añado a la lista de
palabras válidas? Así no la marca nunca, aunque Claude no esté disponible." Con el sí, añádela
(una por línea, sin duplicar) al final de `<drive_root>/_config/glosario.txt` (`drive_root` está
en `~/.videoqa/config.yaml`; crea el archivo si no existe).

## Reglas

- No cambies el veredicto del video ya revisado: la corrección vale para los próximos. Si quiere
  que ese mismo video se reevalúe, ofrécele revisarlo otra vez con `/aura:revisar`.
- Una corrección por cosa distinta. Si dice varias en un mensaje, guarda cada una con su motivo.
- Si pide ver lo aprendido, lee `<drive_root>/_config/aprendizaje.jsonl` y resúmelo como lista
  sencilla ("No marcar logos de ropa", "Marcar precios distintos entre rótulo y voz"…).
- Nunca muestres el JSON ni los ids a la persona.
