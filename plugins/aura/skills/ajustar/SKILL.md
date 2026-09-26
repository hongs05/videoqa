---
description: Cambia qué se marca como error, llena el glosario con las palabras del equipo y sube o baja la gravedad. Úsalo si dice "no marques X", "llena el glosario" o "que el silencio bloquee".
disable-model-invocation: true
allowed-tools: Read Edit Bash(launchctl kickstart:*) Bash(uv run --project ~/videoqa videoqa glosario:*)
---

# Ajustar la revisión

Habla en español informal (tú), sin jerga.

**Regla de oro: siempre muestra el cambio en palabras sencillas y pregunta "¿Lo aplico?" antes
de tocar ningún archivo.** Espera un sí explícito.

El motor vive en `~/videoqa`: las reglas están en `~/videoqa/reglas.yaml`. Si esa carpeta no
existe, dile "Todavía no está instalado: escribe `/aura:instalar`" y termina.

Lee `drive_root` de `~/.videoqa/config.yaml` cuando lo necesites.

**Si el cambio es para un cliente concreto** ("para Sushi CD, que…", "en los de Hacienda…"), no
toques lo general: eso lo hace `/aura:cliente` en el perfil de ese cliente. Díselo y síguelo ahí.

## Caso A — "No marques la palabra X"

Ejemplos: "no marques la palabra Kasa", "Molinrocha no es un error", "deja de marcar reels".

Es el glosario: palabras válidas aunque el diccionario no las conozca (marcas, nombres propios,
jerga).

1. Di: "Voy a añadir **Kasa** a la lista de palabras válidas, para que deje de marcarla como
   error de ortografía. ¿Lo aplico?"
2. Con el sí, añade la palabra (una por línea) al final de
   `<drive_root>/_config/glosario.txt`. Crea el archivo si no existe. No dupliques: si ya está,
   dilo ("Ya estaba en la lista") y no toques nada. Si el archivo está creciendo, agrupa las
   palabras por cuenta con un comentario encima (`# Goldstone`), para que dentro de unos meses
   se entienda por qué está cada una.
3. Confirma: "Listo. A partir del próximo video ya no la marca."

Para varias palabras a la vez, añádelas todas y confírmalo en una línea.

Si te piden ver el glosario, léelo y muéstralo como una lista simple.

## Caso B — "Que X sea bloqueante / que X sea solo un aviso"

Es `~/videoqa/reglas.yaml`, sección `severities`. Traduce del castellano al nombre técnico:

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
2. Con el sí, edita `~/videoqa/reglas.yaml` con Edit (solo esa línea).
3. Si la revisión automática está encendida, reiníciala para que tome el cambio. Si responde que
   no existe el servicio, es que está apagada: no es un error, no lo menciones.

```bash
launchctl kickstart -k gui/$UID/com.videoqa.watcher
```

4. Confirma: "Cambiado. Los videos que revise a partir de ahora usan la regla nueva; los que ya
   están revisados no cambian."

## Caso C — "¿Qué reglas hay?"

Lee `~/videoqa/reglas.yaml` y muéstralo traducido, agrupado por gravedad. Nada de YAML a la
vista:

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

## Caso D — "Llena el glosario" / "revisa qué palabras marca mal"

Sirve para sembrar el glosario de golpe con lo que ya se revisó, en vez de ir palabra por
palabra. Úsalo también la primera vez que se configura el equipo.

```bash
uv run --project ~/videoqa videoqa glosario
```

La primera línea dice cuántas candidatas hay; luego una por línea con las veces que se marcó
y en cuántos videos. **No le enseñes la tabla en crudo.** Sepáralas en dos grupos, en
castellano, empezando por las más repetidas:

> Encontré 9 palabras que se marcaron como error. Creo que 6 son válidas:
>
> - **Nombres de marca o herramientas:** Canva, Klook, Educanab
> - **Jerga:** corillo, chamba, bacano
>
> **Parecen lecturas raras del video, no las añado:** sarte, jel, detoils
>
> ¿Añado las 6 primeras a la lista de palabras válidas? Si alguna SÍ es una falta real, dime
> cuál y la dejo fuera también.

Para distinguir un grupo del otro: una palabra real es una que reconocerías si la vieras
escrita (una marca, un producto, una jerga de la calle); lo demás son casi siempre trozos que
el lector de texto del video leyó mal (una letra de más o de menos, una palabra cortada a
mitad). **Nunca metas en `--agregar` las que parecen lecturas raras**: una palabra basura en el
glosario del equipo apaga la detección de esa falta para siempre, en todos los videos futuros.

Con el sí (y quitando las que te diga):

```bash
uv run --project ~/videoqa videoqa glosario --agregar "canva,klook,educanab,corillo,chamba,bacano"
```

Confirma en una línea cuántas quedaron añadidas. Si la respuesta es `AGREGADAS: ninguna`, dile
que ya estaban todas. Si además ves una línea `YA_DE_FABRICA: ...`, es que alguna de esas
palabras ya venía incluida en el programa desde siempre; dile a la persona que esas ya
estaban aceptadas y no hizo falta tocar nada por ellas.

Si no hay candidatas (`CANDIDATAS 0`), díselo así: "No hay palabras pendientes: el corrector no
está marcando nada raro."

## Caso E — "Marca mal las palabras en inglés" / "solo revisa español"

El corrector consulta español e inglés: una palabra solo es falta si no existe en ninguno de
los dos. Se cambia con la clave `idiomas` de `~/.videoqa/config.yaml`.

- Si los videos son solo en español y quieren que el inglés SÍ se marque: deja `idiomas: [es]`.
- Si vuelve a marcar inglés correcto: comprueba que la línea diga `idiomas: [es, en]`.

Ojo: aunque se deje `idiomas: [es]`, las palabras de redes que el programa ya trae de fábrica
(link, online, marketing, delivery, outfit, tips, sale, pack, gift, skincare, fitness, workout,
mood, vibes y otras por el estilo) se siguen aceptando igual — esas vienen del glosario de
fábrica, no del idioma inglés, así que este cambio no las toca.

Explícalo así: "Ahora mismo acepto palabras en español y en inglés. Si quieres que marque el
inglés como error, lo dejo solo en español — aunque las palabras de redes que ya trae de
fábrica el programa van a seguir aceptándose igual. ¿Lo cambio?" Con el sí, edita esa línea con
Edit (créala si no está) y recuerda que solo afecta a los videos que se revisen a partir de
ahora.

## Cómo explicar el resultado

- Nunca muestres YAML, ni claves en inglés, ni rutas completas.
- Nunca edites nada sin el "sí" previo.
- Si te piden algo que no se puede ajustar desde aquí (por ejemplo cambiar los colores de la
  marca), dilo en claro: "Eso viene de la guía de marca. Si tienes el PDF nuevo, dímelo y lo
  volvemos a cargar."
- Si algo falla, resume en una frase y propón el siguiente paso. Nada de tracebacks.
- El programa ya trae de fábrica una lista de palabras de redes, anglicismos y jerga (reel,
  hashtag, Canva, chévere…). No hace falta añadir esas: si te piden una que ya viene, dilo y no
  toques el archivo.
