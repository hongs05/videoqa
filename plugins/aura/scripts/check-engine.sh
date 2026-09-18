#!/usr/bin/env bash
#
# Hook SessionStart de Aura: imprime UNA línea en español con el estado del
# sistema (motor, configuración, videos pendientes, revisión automática).
#
# Reglas: rápido y silencioso ante cualquier problema. Pase lo que pase sale
# con 0, para no romper el arranque de la sesión.
#
set -u

MOTOR="$HOME/videoqa"
CONFIG="$HOME/.videoqa/config.yaml"

if [ ! -d "$MOTOR" ]; then
  echo "Aura: motor no instalado → escribe /aura:instalar"
  exit 0
fi

if [ ! -f "$CONFIG" ]; then
  echo "Aura: motor OK · sin configurar → escribe /aura:instalar"
  exit 0
fi

# drive_root del YAML: primera clave de primer nivel, sin comillas ni comentario.
DRIVE="$(grep -m1 '^drive_root:' "$CONFIG" 2>/dev/null \
  | sed -e 's/^drive_root:[[:space:]]*//' -e 's/[[:space:]]*$//' \
        -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")"
case "$DRIVE" in
  "~"/*) DRIVE="$HOME${DRIVE#\~}" ;;
esac

PEND="?"
if [ -n "$DRIVE" ] && [ -d "$DRIVE/01_Entrada" ]; then
  PEND="$(ls -1 "$DRIVE/01_Entrada" 2>/dev/null | wc -l | tr -d ' ')"
fi

case "$PEND" in
  0) COLA="sin videos pendientes" ;;
  1) COLA="1 video pendiente" ;;
  \?) COLA="carpeta de videos no encontrada" ;;
  *) COLA="$PEND videos pendientes" ;;
esac

if launchctl print "gui/$(id -u)/com.videoqa.watcher" 2>/dev/null | grep -q 'state = running'; then
  AUTO="automático: encendido"
else
  AUTO="automático: apagado"
fi

echo "Aura: motor OK · config OK · $COLA · $AUTO"
exit 0
