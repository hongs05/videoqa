---
description: Crea o cambia el perfil de revisión de un cliente (marca, tono, prohibido, obligatorio) y el brief de una pieza. Úsalo con "crea el perfil de Sushi CD" o "pon el brief del reel3".
allowed-tools: Read Write Edit Bash(ls:*) Bash(mkdir:*) Bash(cp:*)
---

# Perfil de cliente

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin rutas ni nombres de
archivo a la vista (salvo la carpeta donde subir los videos).

Cada cliente puede tener su forma de revisar. Los videos que se suben a
`01_Entrada/<Cliente>/` se revisan con el perfil de ese cliente; los que van sueltos en
`01_Entrada/`, con el general.

`drive_root` está en `~/.videoqa/config.yaml`. El perfil vive en
`<drive_root>/_config/clientes/<Cliente>/`. Si `~/videoqa` no existe, dile "Todavía no está
instalado: escribe `/aura:instalar`" y termina.

**Regla de oro: resume siempre lo que vas a guardar y pregunta "¿Lo guardo?" antes de escribir.**

## Crear un perfil

1. **Nombre del cliente**, tal como quiere ver la carpeta ("Sushi CD", "Hacienda Chocolat"). Sin
   `/` ni empezar por punto. Si ya existe `<drive_root>/_config/clientes/<Cliente>/`, pasa a
   "Cambiar un perfil".

2. **Hazle estas preguntas, de una en una**, en lenguaje llano. Si dice "no sé" o "lo de
   siempre", pasa a la siguiente (se hereda lo general):
   1. ¿Tiene guía de marca en PDF? (si sí, pídele que la arrastre al chat o te diga dónde está)
   2. ¿Qué tono usa? (cercano, formal, tutea o no, humor…)
   3. ¿Qué **no** puede salir nunca? (palabras, competencia, temas, promesas)
   4. ¿Qué **debe** salir siempre? (logo al cierre, nombre de la marca, CTA, precio en cierta
      moneda, @ del cliente…)
   5. ¿Palabras suyas que están bien aunque parezcan faltas? (productos, nombres, jerga)
   6. ¿Algo que para este cliente sea más o menos grave de lo normal? (p. ej. "los silencios no
      importan", "el color fuera de marca es gravísimo")

3. **Resume** en 4–6 líneas y pregunta "¿Lo guardo?".

4. Con el sí, crea la carpeta y escribe (solo lo que haya respondido):

```bash
mkdir -p "<drive_root>/_config/clientes/<Cliente>" "<drive_root>/01_Entrada/<Cliente>"
```

   - `criterios.md` con este formato (una línea por criterio, en sus palabras):

```markdown
# Criterios de <Cliente>

## Tono
- …

## Nunca
- …

## Siempre
- …

## Otros
- …
```

   - `glosario.txt`: una palabra por línea (la respuesta 5).
   - Guía de marca: cópiala como `guia_de_marca.pdf` dentro de la carpeta del perfil
     (`cp "<ruta del PDF>" "<drive_root>/_config/clientes/<Cliente>/guia_de_marca.pdf"`). La
     primera revisión la lee y saca los colores sola.
   - `reglas.yaml` **solo** si la respuesta 6 cambia la gravedad de algo. Solo las líneas que
     cambian, con los mismos nombres que `~/videoqa/reglas.yaml` (léelo para traducir):

```yaml
severities:
  silence: info          # "los silencios no importan"
  brand_color: blocker
```

     Gravedades: `blocker` = bloquea la publicación, `warning` = aviso, `info` = solo nota.

5. Confirma: "Listo. Sube los videos de <Cliente> a la carpeta **01_Entrada/<Cliente>** y se
   revisarán con su perfil."

## Cambiar un perfil

"Para Sushi CD, que el silencio no bloquee", "añade que nunca digan *barato*", "Hacienda ya no
exige el logo":

1. Lee los archivos del perfil.
2. Di el cambio en una frase y pregunta "¿Lo aplico?".
3. Con el sí, cambia **solo esa línea** con Edit (criterios en `criterios.md`, palabras en
   `glosario.txt`, gravedades en `reglas.yaml`, créalo si no existe).

Si pide ver un perfil, resúmelo como lista sencilla. Si pide "¿qué clientes hay?", lista las
carpetas de `<drive_root>/_config/clientes/`.

## Brief de una pieza

El brief es lo que se planeó para un video concreto: objetivo, guion o puntos clave, copy, CTA y
lo obligatorio. Con él, la revisión detecta si falta el cierre, si el precio no es el del plan,
etc.

"Pon el brief del reel3 de Sushi CD: …" → escríbelo con Write en un `.txt` con **el mismo nombre
que el video**, al lado del video:

- Si el video ya está subido: `<drive_root>/01_Entrada/<Cliente>/reel3.txt` junto a `reel3.mp4`.
- Si aún no: créalo igual; cuando suban `reel3.mp4` a esa carpeta, se usará.

Formato sugerido (lo que tenga):

```
Objetivo: …
Mensaje principal: …
Guion / puntos clave:
- …
Copy en pantalla: …
CTA: …
Obligatorio: …
```

Confirma: "Guardado. Cuando se revise ese video, se comparará con este brief." Si trae el
calendario del mes, puedes sacar el brief de la fila de esa pieza.
