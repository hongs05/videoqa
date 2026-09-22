---
description: Arregla la sesión de Claude cuando caduca y los videos vuelven sin criterio. Úsalo cuando la persona diga "arregla la sesión", "sesión caducada" o "los videos salen pendientes".
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Bash(open:*) Bash(ls:*) Read
---

# Arreglar la sesión de Claude

Habla en español informal (tú), sin jerga: nunca digas "token", "OAuth" ni "login". Di "la sesión
de Claude". **Nunca leas ni muestres el contenido de `~/.videoqa/token`.**

El motor vive en `~/videoqa`; si no existe (`ls ~/videoqa`), dile "Todavía no está instalado:
escribe `/aura:instalar`" y termina.

Si cualquier comando `videoqa` responde con algo como "invalid choice", "unrecognized arguments"
o "error: argument", es que el motor instalado es más viejo que esta guía. Dile "Hay que poner
el motor al día: escribe `/aura:actualizar`" y termina ahí, sin seguir con el resto de pasos.

## Paso 1 — Comprobar

```bash
uv run --project ~/videoqa videoqa doctor
```

- Si empieza por `CRITERIO OK`: "La sesión está bien, no hay nada que arreglar." Si te lo
  pidieron porque un video salió pendiente, ofrécele revisarlo otra vez ahora.
- Si dice `no encuentro el programa claude`: "Falta el programa de Claude en esta Mac. Escribe
  `/aura:instalar` y lo dejo listo." Termina.
- Si dice `la sesión caducó o no está guardada`: sigue al Paso 2.

## Paso 2 — Guardar la sesión (lo hace la persona, en la Terminal)

Dile, tal cual:

> Te abro una ventana de la Terminal. Se abre el navegador: autoriza con tu cuenta de Claude y, si
> te pide pegar un código en la Terminal, pégalo y pulsa Enter. Cuando la ventana diga "Listo",
> vuelve aquí y me dices.

Antes de abrirla, comprueba que existe:

```bash
ls ~/videoqa/instalar/guardar-token.command
```

Si no está, es que el motor instalado es más viejo que esta guía: dile "Hay que poner el motor
al día: escribe `/aura:actualizar`" y termina. Si existe:

```bash
open ~/videoqa/instalar/guardar-token.command
```

Espera a que te diga que terminó. Luego vuelve al Paso 1. Si a la segunda sigue fallando, dile
"No consigo dejar la sesión guardada; avisa a quien te pasó la herramienta" y termina.

## Paso 3 — Rematar

Si hay videos en `02_Con_errores` cuyo `reporte.md` empieza por `⏸️` (pendientes de criterio),
dile: "Los que quedaron pendientes los vuelvo a revisar cuando quieras: dime «revisa los
pendientes»". Si lo pide, para cada uno lanza `videoqa run` sobre el archivo que está dentro de
`02_Con_errores/<nombre>/` (el motor lo copia solo a `01_Entrada`) y explica el resultado como en
`/aura:revisar`.
