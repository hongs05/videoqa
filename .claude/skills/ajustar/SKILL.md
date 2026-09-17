---
name: ajustar
description: Cambia el comportamiento de la revisión - añadir palabras que no se deben marcar como error (nombres de marca, jerga) y subir o bajar la gravedad de un tipo de problema. Úsalo cuando la persona diga "no marques la palabra X", "que el silencio sea bloqueante", "esto no debería ser un error", "qué reglas hay" o /ajustar.
---

# Ajustar la revisión

Trabaja desde la raíz del proyecto. Habla en español informal (tú), sin jerga.

**Regla de oro: siempre muestra el cambio en palabras sencillas y pregunta "¿Lo aplico?" antes
de tocar ningún archivo.** Espera un sí explícito.

Lee `drive_root` de `~/.videoqa/config.yaml` cuando lo necesites.

## Caso A — "No marques la palabra X"

Ejemplos: "no marques la palabra Kasa", "Molinrocha no es un error", "deja de marcar reels".

Es el glosario: palabras válidas aunque el diccionario no las conozca (marcas, nombres propios,
jerga).

1. Di: "Voy a añadir **Kasa** a la lista de palabras válidas, para que deje de marcarla como
   error de ortografía. ¿Lo aplico?"
2. Con el sí, añade la palabra (una por línea) al final de
   `<drive_root>/_config/glosario.txt`. Crea el archivo si no existe. No dupliques: si ya está,
   dilo ("Ya estaba en la lista") y no toques nada.
3. Confirma: "Listo. A partir del próximo video ya no la marca."

Para varias palabras a la vez, añádelas todas y confírmalo en una línea.

Si te piden ver el glosario, léelo y muéstralo como una lista simple.

## Caso B — "Que X sea bloqueante / que X sea solo un aviso"

Es `reglas.yaml`, sección `severities`. Traduce del castellano al nombre técnico:

| Lo que dice la persona | Clave en `reglas.yaml` |
| --- | --- |
| silencios, pausas largas | `silence` |
| faltas de ortografía, palabras mal escritas | `spelling_unknown_word` |
| tildes, puntuación, comas | `spelling_punctuation` |
| colores fuera de la marca | `brand_color` |
| texto que aparece muy poco tiempo | `text_visible_short` |
| subtítulos desincronizados | `subtitle_desync` |
| texto tapado por los iconos de TikTok/Reels | `text_occluded` |
| pantallas en negro | `black_frame` |
| imagen congelada | `frozen_frame` |
| audio saturado / distorsionado | `audio_clipping` |
| formato que no es vertical 9:16 | `aspect_ratio` |
| video sin audio | `no_audio` |

Y los niveles: **bloqueante** = `blocker` (manda el video a 02_Con_errores), **aviso** =
`warning` (se reporta pero no bloquea), **informativo** = `info` (solo se anota).

1. Di el cambio en claro: "Ahora los silencios largos son un **aviso**. Los voy a poner como
   **bloqueante**: a partir de ahora un video con un silencio largo no se aprueba. ¿Lo aplico?"
2. Con el sí, edita `reglas.yaml` con Edit (solo esa línea).
3. Si la revisión automática está encendida, reiníciala para que tome el cambio:

```bash
launchctl print gui/$UID/com.videoqa.watcher 2>/dev/null | grep -q 'state = running' \
  && launchctl kickstart -k gui/$UID/com.videoqa.watcher
```

4. Confirma: "Cambiado. Los videos que revise a partir de ahora usan la regla nueva; los que ya
   están revisados no cambian."

## Caso C — "¿Qué reglas hay?"

Lee `reglas.yaml` y muéstralo traducido, agrupado por gravedad. Nada de YAML a la vista:

> **Bloquean la publicación (🔴):**
> - Palabras mal escritas
> - Colores fuera de la paleta de marca
> - Pantallas en negro
>
> **Solo avisan (⚠️):**
> - Tildes y puntuación
> - Texto que se ve menos de 1 segundo
> - Subtítulos desincronizados
> - Texto tapado por los iconos de la app
> - Imagen congelada
> - Silencios largos
> - Audio saturado
> - Formato que no es vertical
> - Video sin audio
>
> ¿Quieres cambiar alguna?

## Cómo explicar el resultado

- Nunca muestres YAML, ni claves en inglés, ni rutas completas.
- Nunca edites nada sin el "sí" previo.
- Si te piden algo que no se puede ajustar desde aquí (por ejemplo cambiar los colores de la
  marca), dilo en claro: "Eso viene de la guía de marca. Si tienes el PDF nuevo, dímelo y lo
  volvemos a cargar."
- Si algo falla, resume en una frase y propón el siguiente paso. Nada de tracebacks.
