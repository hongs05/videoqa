---
description: Instala y enciende (o apaga) el juez de respaldo, un modelo gratis en la Mac que revisa cuando Claude se queda sin uso. Úsalo con "activa el respaldo" o "apaga el respaldo".
disable-model-invocation: true
allowed-tools: Read Edit Bash(uv run --project ~/videoqa videoqa:*) Bash(brew:*) Bash(ollama:*) Bash(sysctl:*) Bash(which:*) Bash(launchctl kickstart:*)
---

# Juez de respaldo

Habla en español informal (tú), sin jerga, sin comandos a la vista.

Cuando Claude se queda sin uso disponible, los videos esperan hasta que vuelva. El juez de
respaldo es un modelo pequeño y gratuito que corre en la propia Mac (con **Ollama**) y los
revisa mientras tanto. No envía el video a ningún sitio.

**Explícalo claro antes de instalar nada:** es menos preciso que Claude. Por eso no puede
quitar un error grave del código (como mucho lo deja como aviso para que alguien lo mire), y el
reporte dice que la revisión la hizo el respaldo.

El motor vive en `~/videoqa`. Si no existe, dile "Todavía no está instalado: escribe
`/aura:instalar`" y termina.

## Encender

1. **Memoria de la Mac.**

```bash
sysctl -n hw.memsize
```

   Menos de 8 GB (8589934592): dile que no le va a caber y termina. Con 8 GB: avisa de que va
   justo y de que, mientras revisa con el respaldo, la Mac irá más lenta.

2. Pregunta: "Voy a instalar Ollama y descargar el modelo (unos 3–4 GB, una sola vez). ¿Sigo?"
   Espera un sí.

3. **Ollama.** Si `which ollama` no encuentra nada:

```bash
brew install ollama
```

   Y que arranque solo con la Mac:

```bash
brew services start ollama
```

4. **El modelo** (tarda según la conexión; avísalo):

```bash
ollama pull qwen3.5:4b
```

5. **Prueba:**

```bash
uv run --project ~/videoqa videoqa respaldo
```

   Si dice `RESPALDO OK`, sigue. Si dice `RESPALDO NO DISPONIBLE`, explica el motivo en una frase
   (lo más común: Ollama no está arrancado → repite el paso 3) y no actives nada.

6. **Activarlo:** en `~/videoqa/reglas.yaml`, dentro de `juez_respaldo:`, cambia `activo: false`
   por `activo: true` (con Edit, sin tocar nada más).

7. Si la revisión automática está encendida, reiníciala para que lo use:

```bash
launchctl kickstart -k gui/$UID/com.videoqa.watcher
```

   Si responde que no existe el servicio, está apagada: no pasa nada, no lo menciones.

8. Confirma: "Listo. Cuando Claude se quede sin uso, los videos los revisa el respaldo en vez
   de esperar. En el reporte verás «Revisado con el juez de respaldo»."

## Apagar

Pregunta "¿Lo apago?". Con el sí, en `~/videoqa/reglas.yaml` cambia `activo: true` por
`activo: false` dentro de `juez_respaldo:` y reinicia la automática como en el paso 7. Ollama y
el modelo se quedan instalados; si quiere liberar el espacio, `ollama rm qwen3.5:4b`.

## ¿Funciona?

Si pregunta si está funcionando, lanza la prueba del paso 5 y cuéntale el resultado.
