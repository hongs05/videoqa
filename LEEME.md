# VideoQA — revisión de videos antes de publicar

Esto revisa cada video antes de que salga: ortografía en pantalla, colores de la marca, que lo
que se dice coincida con lo que se escribe, silencios, pantallas en negro y tomas fallidas.

Tarda unos minutos por video y te deja un informe con **qué corregir y en qué segundo**.

## Las tres carpetas de Drive

| Carpeta | Qué es |
| --- | --- |
| **01_Entrada** | Aquí subes los videos. Es lo único que tocas para pedir una revisión. |
| **02_Con_errores** 🔴 | El video tiene algo que hay que corregir antes de publicar. |
| **03_Aprobado** 🟢 | El video está listo. Solo de aquí se publica. |

El video se mueve solo: sale de `01_Entrada` y aparece en una de las otras dos, dentro de una
carpeta con su nombre.

## Qué hay dentro de la carpeta de cada video

- **`reporte.md`** — el informe. Empieza con el semáforo (🟢 o 🔴) y un resumen. Luego:
  - **🔴 Bloqueantes** — hay que corregirlo sí o sí. Cada punto trae el minuto (`[0:12]`), qué
    está mal y una sugerencia de qué hacer.
  - **⚠️ Advertencias** — míralo, pero no bloquea.
  - **✅ Checks pasados** — todo lo que salió bien.
- **`evidencia/`** — fotos del momento exacto del problema, con un recuadro rojo encima. El
  nombre lleva el minuto: `01_0m12s.jpg` es el segundo 12. Ábrelas, se entiende en dos segundos.
- **`guion_real.md`** — lo que de verdad se dice en el video, transcrito, limpio y por escenas.
  Sirve para copys, subtítulos y descripciones.
- El video original, tal cual.

## Las 3 reglas del equipo

1. **Todo video se sube a `01_Entrada`.** No se revisa nada que esté en otro sitio.
2. **Si cae en `02_Con_errores`: corrige y vuelve a subir a `01_Entrada` con el mismo nombre.**
   El mismo nombre es importante — así se sabe que es una nueva versión del mismo video.
3. **Solo se publica lo que está en `03_Aprobado`.** Sin excepciones, aunque corra prisa.

## Cómo hablar con Claude

Abre Claude (la aplicación, pestaña Code) y escríbele. Hay seis comandos:

| Comando | Para qué |
| --- | --- |
| `/aura:instalar` | Configurarlo todo la primera vez. |
| `/aura:revisar` | Revisar los videos pendientes. |
| `/aura:estado` | Ver qué hay pendiente y cómo va todo. |
| `/aura:ajustar` | Cambiar qué se marca como error. |
| `/aura:activar-automatico` | Que revise solo, sin pedírselo. |
| `/aura:actualizar` | Ponerlo al día cuando haya versión nueva. |

No hace falta usar los comandos: puedes escribirle normal, como a una persona. Por ejemplo:

- «revisa los videos nuevos»
- «¿por qué está en rojo el de la promo?»
- «no marques la palabra Kasa»
- «¿cómo va la cola?»
- «activa la revisión automática»

Si algo no funciona, pregúntale directamente: «no me está revisando nada, ¿qué pasa?».

## Dos cosas que conviene saber

- **La primera revisión tarda bastante más** (descarga un modelo de voz de ~1,5 GB). Solo pasa
  una vez.
- **Con la revisión automática encendida, la Mac tiene que quedar encendida y con la sesión
  abierta.** La pantalla bloqueada vale; cerrar sesión o apagarla, no.

## Instalación (una sola vez, ~15 min)

1. Descomprime `VideoQA-demo.zip` y haz **clic derecho → Abrir** sobre `Instalar VideoQA.command`
   (la primera vez macOS avisa que "procede de un desarrollador no identificado"; con clic
   derecho → Abrir se puede continuar). Te pedirá la contraseña de la Mac para instalar
   herramientas.
2. Cuando termine, abre Claude (la aplicación, pestaña Code) o escribe `claude` en la Terminal, y
   escribe `/aura:instalar`. Claude te guiará: elegir la carpeta de videos, cargar la guía de
   marca y hacer una prueba.

Cuando haya una versión nueva, escribe `/aura:actualizar` y se pone al día solo.
