---
description: Enciende o apaga la revisión automática, para que los videos que subas a 01_Entrada se revisen solos. Úsalo cuando la persona diga "que lo haga solo", "activa lo automático" o "apaga el robot".
disable-model-invocation: true
allowed-tools: Bash(sed:*) Bash(launchctl:*) Bash(command -v:*) Bash(mkdir:*) Read
---

# Revisión automática (encender / apagar)

Habla en español informal (tú). El motor vive en `~/videoqa`; si esa carpeta no existe, dile
"Todavía no está instalado: escribe `/aura:instalar`" y termina.

Primero averigua si te piden **encenderla** o **apagarla**. Si no queda claro, pregunta.

## Encender

1. Comprueba que ya está configurado: si no existe `~/.videoqa/config.yaml`, dile que escriba
   `/aura:instalar` primero y termina.

2. Instala el agente. El proyecto es siempre `$HOME/videoqa`:

```bash
mkdir -p ~/Library/LaunchAgents
sed -e "s|__HOME__|$HOME|g" -e "s|__PROJECT__|$HOME/videoqa|g" -e "s|__UV__|$(command -v uv)|g" \
  "$HOME/videoqa/launchd/com.videoqa.watcher.plist" > ~/Library/LaunchAgents/com.videoqa.watcher.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.videoqa.watcher.plist
```

Si `bootstrap` se queja de que ya está cargado, quítalo primero con
`launchctl bootout gui/$UID/com.videoqa.watcher` y vuelve a intentarlo una vez.

3. Comprueba que arrancó:

```bash
launchctl print gui/$UID/com.videoqa.watcher 2>/dev/null | grep -q 'state = running' && echo ENCENDIDA || echo NO_ARRANCO
```

4. Si arrancó, díselo así:

> ✅ Listo. A partir de ahora, cada video que subas a **01_Entrada** se revisa solo, sin que me
> lo pidas. Tarda unos minutos por video.
>
> Una cosa importante: **la Mac tiene que quedar encendida y con tu sesión abierta.** La pantalla
> puede estar bloqueada, no pasa nada — pero si cierras sesión o la apagas, deja de revisar hasta
> que vuelvas a entrar.
>
> Cuando quieras saber cómo va, pregúntame "¿cómo va la cola?".

5. Si no arrancó, no muestres el error en crudo. Mira `~/.videoqa/launchd.err.log` (últimas
   líneas, con Read), resume la causa en una frase y propón el siguiente paso. Las causas
   habituales:
   - `uv` no está instalado → "Falta un programa base. Haz doble clic en 'Instalar
     VideoQA.command' y me dices."
   - falta la configuración → "Todavía no elegiste la carpeta de videos. Escribe
     `/aura:instalar`."

## Apagar

```bash
launchctl bootout gui/$UID/com.videoqa.watcher
```

Si responde que no estaba cargado, no es un error: dile que ya estaba apagada.

Confirma: "Apagada. Los videos ya no se revisan solos — cuando quieras que revise, dime 'revisa
los videos nuevos'."

## Cómo explicar el resultado

- Nunca digas "launchd", "agente", "plist", "daemon" ni muestres rutas de `~/Library`. Habla de
  "la revisión automática".
- Repite siempre la condición de la Mac encendida con sesión abierta al encenderla: es la causa
  número uno de "no me revisó nada".
- Si algo falla, una frase con la causa y un siguiente paso concreto. Nada de tracebacks.
- Si te preguntan si está encendida, usa la comprobación del punto 3 y responde con una línea.
