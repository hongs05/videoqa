---
description: Revisa los videos pendientes y explica en español sencillo qué corregir y en qué segundo. Úsalo cuando la persona diga "revisa los videos nuevos", "revisa el de la promo" o "¿cómo quedó este video?".
allowed-tools: Bash(uv run --project ~/videoqa videoqa:*) Bash(open:*) Bash(ls:*) Read Write
---

# Revisar videos

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin comandos a la vista.

El motor vive en `~/videoqa` y todo se lanza como `uv run --project ~/videoqa videoqa …`.
Antes de nada, comprueba que la carpeta `~/videoqa` existe (`ls ~/videoqa`). Si no está, dile
"Todavía no está instalado: escribe `/aura:instalar` y lo dejamos listo" y termina.

**Carpetas de cliente.** Los videos pueden ir sueltos en `01_Entrada/` o dentro de la carpeta de
un cliente, `01_Entrada/<Cliente>/` (se revisan con el perfil de ese cliente, ver
`/aura:cliente`). En ese caso todas las rutas de este documento llevan el cliente en medio:
`02_Con_errores/<Cliente>/<nombre>/`, `03_Aprobado/<Cliente>/<nombre>/`,
`04_Pruebas_respaldo/<Cliente>/<nombre>/`. `videoqa run` sobre un video ya revisado lo devuelve
solo a la carpeta de su cliente en `01_Entrada`, con su brief. Al explicar el resultado, di de
qué cliente es.

## Paso 1 — Decidir qué revisar

**Si nombró un video concreto** ("revisa el de la promo", "revisa promo_octubre.mp4"):

Busca el archivo en `01_Entrada/` dentro de la carpeta de Drive (`drive_root` está en
`~/.videoqa/config.yaml`):

```bash
ls "<drive_root>/01_Entrada" "<drive_root>/01_Entrada"/*/
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
serios) o `03_Aprobado/`. Ahí dentro está `reporte.html` (o `reporte.md` si prefieres texto). Léelo con Read.

## Paso 4 — Si un video vuelve ⏸️ PENDIENTE (sin criterio de Claude)

Eso significa que los checks automáticos pasaron pero el juez no pudo dar criterio. **No le digas
que el video "tiene errores"**: no se ha terminado de revisar. Haz tú de juez, sin pedir nada:

1. Vuelve a lanzar el video en modo "hasta el juez". El video ya está en `02_Con_errores/<nombre>/`;
   cópialo primero a `01_Entrada` (con `videoqa run` sobre esa ruta se copia solo):

```bash
uv run --project ~/videoqa videoqa run "<drive_root>/02_Con_errores/<nombre>/<archivo>" --hasta-juez
```

   La última línea es `JUEZ_PENDIENTE <carpeta>`.

2. Lee con Read `<carpeta>/judge_prompt.md` y síguelo al pie de la letra: los datos del video
   ya vienen dentro; solo te pide abrir las fotos de `<carpeta>/claude_frames/` (las rutas del
   prompt son relativas a `<carpeta>`; ábrelas todas a la vez) y responder solo con un JSON.

3. Escribe ese JSON, y nada más, con Write en `<carpeta>/veredicto.json`.

4. Reanuda:

```bash
uv run --project ~/videoqa videoqa run "<drive_root>/01_Entrada/<archivo>" --veredicto "<carpeta>/veredicto.json"
```

   Y explica el resultado como siempre (Paso 5). Si vuelve a salir pendiente, es que el JSON no
   era válido. El video ya está de vuelta en `02_Con_errores/<nombre>/` (la ruta de
   `01_Entrada/<archivo>` ya no existe), así que reinténtalo **una sola vez** desde el punto 1,
   lanzando otra vez el modo "hasta el juez" sobre el archivo dentro de `02_Con_errores/<nombre>/`,
   escribiendo un `veredicto.json` corregido y repitiendo este punto 4. Si falla una segunda vez,
   dile en una frase que no se pudo completar la revisión de criterio y que diga **"arregla la
   sesión"**.

5. Al final, avísale en una frase: "La sesión de Claude está caducada, por eso esta vez hice yo
   la revisión de criterio. Dime **"arregla la sesión"** cuando puedas y así lo automático vuelve
   a funcionar solo."

## Paso 4b — Si sale `EN_ESPERA` (Claude sin uso disponible)

Significa que la cuenta de Claude llegó a su límite de uso. **El video no tiene la culpa ni se
ha revisado a medias**: sigue en `01_Entrada` y no tiene reporte. No sigas el Paso 4. Díselo así:

> "Claude se quedó sin uso disponible hasta las **7:20 pm**. Los videos esperan en la carpeta de
> entrada; si la revisión automática está encendida se revisan solos a esa hora, y si no,
> pídemelo después."

Con `watch --once`, en la salida aparece "Claude sin uso disponible hasta las HH:MM": igual, los
que quedaban siguen esperando en `01_Entrada`.

Si ves `EN_ESPERA` y el respaldo no está encendido, añade: "Si quieres que en estos casos los
revise un modelo gratis en la Mac mientras vuelve Claude, dime «activa el respaldo»."

**Si el reporte dice «Revisado con el juez de respaldo»:** explica el resultado como siempre, pero
avisa en una frase: "Esta vez lo revisó el modelo de respaldo de la Mac porque Claude no tenía
uso; es menos preciso, así que mira con cuidado los avisos que dicen «el juez de respaldo cree
que no es error»."

## Probar el juez de respaldo con un video

Si pide "revisa X solo con el respaldo", "prueba el respaldo con X" o "compara el respaldo con
Claude en X": es una **prueba**, no la revisión oficial. No mueve el video ni toca el Sheet.

1. Busca el video donde esté: `01_Entrada/`, o ya revisado en `02_Con_errores/<nombre>/` o
   `03_Aprobado/<nombre>/`.
2. Avisa: "Lo reviso con el modelo de la Mac. En un M1 tarda unos minutos."
3. Lánzalo:

```bash
uv run --project ~/videoqa videoqa run "<ruta del video>" --solo-respaldo
```

   - `PRUEBA_RESPALDO <resultado> en X min Y s → <ruta>/reporte.md`: lee ese reporte (dentro de
     `04_Pruebas_respaldo/<nombre>/`).
   - `RESPALDO_ERROR`: casi siempre es que Ollama no está instalado o arrancado. Dile que escriba
     `/aura:respaldo` para dejarlo listo.
4. Explícalo como siempre, diciendo cuánto tardó. Si el video ya tenía la revisión de Claude
   (en `02_Con_errores/` o `03_Aprobado/`), **compáralos**: qué encontraron los dos, qué solo uno,
   y si el respaldo dejó avisos del tipo "cree que no es error". Termina con una frase de
   veredicto ("el respaldo se acercó bastante" / "se le escaparon cosas importantes").
5. Si aún no está encendido y la prueba salió bien, ofrece: "Si te convence, escribe
   `/aura:respaldo` y lo dejo encendido para cuando Claude se quede sin uso."

## Paso 5 — Explicarlo

Ver la sección "Cómo explicar el resultado". Al terminar, abre la carpeta:

```bash
open "<carpeta del video revisado>"
```

Si hay algo marcado que no es error (o se le pasó algo), invítale a decírtelo: "Si algo de esto
no es un error, dímelo (por ejemplo: «SUSHICD es el logo de la camiseta») y lo aprendo para los
próximos videos." Eso lo resuelve `/aura:corregir`.

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
- Si el reporte tiene la sección "Pendientes de revisión (Claude no disponible)", o su título
  empieza por ⏸️, **no digas "pídemelo más tarde"**: sigue el Paso 4 ("Si un video vuelve ⏸️
  PENDIENTE") y explica el resultado final una vez que hayas hecho tú de juez.
- **Nunca muestres un traceback ni un error en crudo.** Resume en una frase y propón el siguiente
  paso: "No pude leer el video, parece que Drive aún lo está sincronizando. Espera a que termine
  el icono de Drive y me dices."
