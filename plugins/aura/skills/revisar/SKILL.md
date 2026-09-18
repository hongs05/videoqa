---
description: Revisa los videos pendientes y explica en español sencillo qué corregir y en qué segundo. Úsalo cuando la persona diga "revisa los videos nuevos", "revisa el de la promo" o "¿cómo quedó este video?".
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Bash(open:*) Bash(ls:*) Read
---

# Revisar videos

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin comandos a la vista.

El motor vive en `~/videoqa` y todo se lanza como `uv run --project ~/videoqa videoqa …`.
Antes de nada, comprueba que la carpeta `~/videoqa` existe (`ls ~/videoqa`). Si no está, dile
"Todavía no está instalado: escribe `/aura:instalar` y lo dejamos listo" y termina.

## Paso 1 — Decidir qué revisar

**Si nombró un video concreto** ("revisa el de la promo", "revisa promo_octubre.mp4"):

Busca el archivo en `01_Entrada/` dentro de la carpeta de Drive (`drive_root` está en
`~/.videoqa/config.yaml`):

```bash
ls "<drive_root>/01_Entrada"
```

Si hay un solo candidato parecido, úsalo. Si hay varios, muéstrale la lista de nombres y pregunta
cuál. Luego:

```bash
uv run --project ~/videoqa videoqa run "<drive_root>/01_Entrada/<archivo>"
```

**Si no nombró ninguno** ("revisa los videos nuevos"):

```bash
uv run --project ~/videoqa videoqa watch --once
```

Esto revisa todo lo que haya pendiente en `01_Entrada/`, uno por uno.

## Paso 2 — Avisar de la espera

Antes de lanzarlo, di algo como: "Voy con eso. Cada video tarda unos minutos." Y **si es la
primera vez que se usa en esta Mac**, añade: "La primera vez además descarga el modelo de voz
(alrededor de 1,5 GB), así que esta vez va a tardar bastante más. Solo pasa una vez."

Si no hay nada en `01_Entrada/`, no lances nada: dile "No hay videos nuevos por revisar" y
ofrécele ver el estado general.

## Paso 3 — Leer el reporte

Cada video termina en una carpeta con su nombre, dentro de `02_Con_errores/` (si tiene problemas
serios) o `03_Aprobado/`. Ahí dentro está `reporte.md`. Léelo con Read.

## Paso 4 — Explicarlo

Ver la sección "Cómo explicar el resultado". Al terminar, abre la carpeta:

```bash
open "<carpeta del video revisado>"
```

Y menciona: "Dentro también está `guion_real.md`: es lo que de verdad se dice en el video,
transcrito y limpio, por si te sirve para el copy o los subtítulos."

## Cómo explicar el resultado

Un mensaje por video, con esta forma:

> **🔴 promo_octubre.mp4 — no aprobado** (2 cosas que corregir, 1 aviso)
>
> **Hay que corregir:**
> 1. **Segundo 0:12** — En pantalla dice "20% de descuento" pero la chica dice "veinticinco por
>    ciento". Cambia el rótulo a 25% o vuelve a grabar la frase. *Abre la foto de evidencia
>    (01_0m12s.jpg).*
> 2. **Segundo 0:41** — La palabra "desdcuento" está mal escrita. *Abre la foto de evidencia.*
>
> **Avisos (no bloquean, pero míralo):**
> - **Segundo 0:03** — Hay 3 segundos de silencio al principio.
>
> Te abrí la carpeta en Finder.

Reglas:

- Semáforo siempre: 🟢 aprobado / 🔴 no aprobado. Nunca digas "rejected", "blocker", "warning",
  "finding" ni nombres de checks en inglés.
- Separa en dos grupos: **"Hay que corregir"** (bloqueantes) y **"Avisos"** (advertencias).
  Si no hay bloqueantes, dilo: "No hay nada que bloquee la publicación."
- Cada punto lleva **el segundo** (`0:12`, no `12.4s`) y **qué hacer**, en imperativo.
- Si el reporte menciona una evidencia, di "abre la foto de evidencia" y nombra el archivo.
- Si son varios videos, empieza con un resumen de una línea ("Revisé 4: 2 aprobados, 2 con cosas
  que corregir") y luego el detalle de cada uno.
- Si el reporte tiene la sección "Pendientes de revisión (Claude no disponible)", explícalo así:
  "Los chequeos automáticos pasaron, pero la revisión de criterio no se pudo hacer esta vez.
  Vuelve a pedírmelo más tarde para tener el veredicto completo."
- **Nunca muestres un traceback ni un error en crudo.** Resume en una frase y propón el siguiente
  paso: "No pude leer el video, parece que Drive aún lo está sincronizando. Espera a que termine
  el icono de Drive y me dices."
