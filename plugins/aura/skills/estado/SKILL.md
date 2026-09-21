---
description: Cuenta cómo va la cola de videos, cuántos hay pendientes, cómo quedaron los últimos y si lo automático está encendido. Úsalo cuando la persona diga "¿cómo va la cola?" o "estado".
allowed-tools: Bash(ls:*) Bash(tail:*) Bash(launchctl print:*) Bash(cat:*) Read
---

# Estado de la revisión

Habla en español informal (tú), sin jerga.

## Paso 1 — Saber dónde está todo

El motor vive en `~/videoqa`. Comprueba que existe (`ls ~/videoqa`); si no está, dile "Todavía no
está instalado: escribe `/aura:instalar`" y termina.

Lee `~/.videoqa/config.yaml` (con Read) y toma el valor de `drive_root`.

Si ese archivo no existe, dile: "Todavía no está configurado. Escribe `/aura:instalar` y lo
dejamos listo en unos minutos." Y termina ahí.

## Paso 2 — Recoger la información

```bash
ls -t "<drive_root>/01_Entrada"
ls -t "<drive_root>/02_Con_errores" | head -5
ls -t "<drive_root>/03_Aprobado" | head -5
```

Para cada una de las carpetas recientes de `02_Con_errores/` y `03_Aprobado/`, lee la **primera
línea** de su `reporte.md` (es el título con el semáforo y el resumen). Usa Read, no dumps.

Revisión automática encendida o no:

```bash
launchctl print gui/$UID/com.videoqa.watcher 2>/dev/null | grep -q 'state = running' && echo ENCENDIDA || echo APAGADA
```

Últimas líneas del registro:

```bash
tail -10 ~/.videoqa/videoqa.log
```

## Paso 3 — Contarlo

Formato, más o menos así:

> **Cómo va la cola**
>
> ⏳ **Pendientes en 01_Entrada:** 3 (promo_octubre.mp4, reel_kasa.mp4, tutorial_2.mp4)
>
> 🔴 **Últimos con errores:**
> - promo_sept — 2 cosas que corregir
> - reel_agosto — 1 cosa que corregir
>
> 🟢 **Últimos aprobados:**
> - tutorial_1 — sin problemas
> - reel_julio — sin problemas
>
> 🤖 **Revisión automática:** encendida (revisa sola cada video que subas).
>
> **Últimos movimientos:** terminó de revisar tutorial_1 hace 20 minutos; ahora mismo no está
> haciendo nada.

Reglas:

- **Resume el registro, no lo pegues.** De las 10 últimas líneas saca una o dos frases en
  castellano: qué se revisó, cuándo, y si hubo algún fallo repetido. Nunca muestres las líneas
  tal cual, ni rutas, ni nombres de módulos de Python.
- Si la revisión automática está apagada, dilo así: "**Revisión automática:** apagada — los videos
  se revisan solo cuando me lo pides. Si quieres que lo haga sola, dime 'activa la revisión
  automática'."
- Si hay pendientes y la automática está apagada, ofrécelo: "¿Los reviso ahora?"
- Si una carpeta está vacía, dilo en positivo ("No hay nada pendiente", "Todavía no hay
  aprobados").
- Si el registro muestra errores repetidos, resúmelos en una frase y propón el siguiente paso.
  Nunca muestres el traceback.
- Si te preguntan por un video en concreto, dile que le abres su carpeta en Finder y hazlo.

## Si hay más de una carpeta

Mira `carpetas_extra` en `~/.videoqa/config.yaml`. Si hay alguna, repite el recuento para cada
una y preséntalas por separado, con su nombre: "En la de Drive hay 2 esperando; en la tuya de
pruebas, ninguna." No las mezcles en un solo número.

## Comprobar que Claude puede dar criterio

La sesión de Claude caduca cada cierto tiempo y, cuando pasa, los videos vuelven con "revisión de
criterio pendiente". Compruébalo siempre:

```bash
claude auth status
```

Si `loggedIn` es `false`, díselo en una frase y dale la solución concreta:

> La sesión de Claude caducó, por eso los últimos videos no traen la parte de criterio. Se
> arregla en un minuto: te abro la Terminal, escribe ahí **claude setup-token** y autoriza en el
> navegador.

Y ábrele la Terminal con `open -a Terminal`.
