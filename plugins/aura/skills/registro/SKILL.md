---
description: Explica qué pasó con un video o con la revisión mirando el registro, y prepara un .zip para soporte. Úsalo con "¿qué pasó con X?", "¿por qué falló?" o "manda los registros".
allowed-tools: Bash(uv run --project ~/videoqa videoqa registro:*) Bash(open:*) Read
---

# Registro de la revisión

La persona es **no técnica**: habla en español informal (tú), sin jerga, sin comandos a la vista.

El motor anota todo lo que hace: un registro general y uno por video (`registro.log`, que también
queda en la carpeta del video junto al reporte). Esta skill sirve para **explicar qué pasó** y,
si hace falta ayuda, **juntar los registros en un .zip** para mandarlo.

El motor vive en `~/videoqa`. Si esa carpeta no existe, dile "Todavía no está instalado:
escribe `/aura:instalar`" y termina.

Si el comando responde con algo como "invalid choice", el motor es más viejo que esta guía: dile
"Hay que poner el motor al día: escribe `/aura:actualizar`" y termina.

## Qué pasó con un video

```bash
uv run --project ~/videoqa videoqa registro "<nombre o trozo del nombre del video>"
```

- `VARIOS` → muéstrale los nombres y pregunta cuál.
- `NO_ENCONTRADO` → ese video no aparece entre los revisados en esta Mac.
- `SIN_REGISTRO` → se revisó con una versión anterior, que no guardaba registro por video. Mira el
  general (abajo).

Cuéntalo en dos o tres frases: cuándo empezó, cuánto tardó, cómo terminó y, si algo falló, qué
fue y qué hacer. Por ejemplo: "Lo revisé ayer a las 16:05 y tardó 3 minutos; el paso lento fue
escuchar el audio. Salió con errores por dos faltas de ortografía."

## Qué está pasando en general

```bash
uv run --project ~/videoqa videoqa registro --problemas --lineas 60
```

Solo trae avisos y errores. Si no hay ninguno, dilo en positivo ("No hubo ningún problema
reciente"). Si hay, agrúpalos ("tres veces Drive no terminó de sincronizar un video") y propón el
siguiente paso. Para ver todo, sin `--problemas`.

## Mandar los registros a soporte

Cuando la persona quiera ayuda, o tú no sepas explicar un fallo:

```bash
uv run --project ~/videoqa videoqa registro --paquete
```

Añade el nombre del video (`registro "<video>" --paquete`) si el problema es de uno en concreto.
Responde `PAQUETE <ruta del .zip>`: por defecto queda en el Escritorio. Muéstralo en Finder con
`open -R "<ruta>"` y dile: "Te dejé un archivo en el Escritorio; mándalo a quien te dé soporte."
Aclárale que lleva solo registros (nombres de videos y lo que hizo el motor), nunca los videos,
las contraseñas ni la sesión de Claude.

## Reglas

- **Resume, no pegues.** Nunca muestres las líneas tal cual, ni rutas, ni tracebacks, ni nombres
  de módulos.
- Si ves `claude -p: … USD`, es lo que costó el criterio de Claude en ese video: puedes decirlo si
  te lo preguntan ("unos 10 céntimos").
- Si el fallo es la sesión de Claude ("authenticate", "sesión caducó"), dile que diga
  **"arregla la sesión"**.
