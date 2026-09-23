#!/usr/bin/env bash
#
# Hook SessionStart de Aura: imprime UNA línea en español con el estado del
# sistema (motor, configuración, videos pendientes, revisión automática).
#
# Reglas: rápido y silencioso ante cualquier problema. Pase lo que pase sale
# con 0, para no romper el arranque de la sesión.
#
set -u

PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"

MOTOR="$HOME/videoqa"
HOME_VQA="${VIDEOQA_HOME:-$HOME/.videoqa}"
CONFIG="$HOME_VQA/config.yaml"
TOKEN="$HOME_VQA/token"
DOCTOR="$HOME_VQA/doctor.json"
ESPERA="$HOME_VQA/espera.json"

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
  PEND="$(find "$DRIVE/01_Entrada" -maxdepth 1 -type f ! -name '.*' \
            \( -iname '*.mp4' -o -iname '*.mov' -o -iname '*.m4v' \) 2>/dev/null | wc -l | tr -d ' ')"
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

SESION="sesión OK"
CADUCADA="⚠️ sesión de Claude caducada → dime «arregla la sesión»"
if [ -f "$DOCTOR" ] && grep -q '"ok": *false' "$DOCTOR" && { [ ! -f "$TOKEN" ] || [ "$DOCTOR" -nt "$TOKEN" ]; }; then
  SESION="$CADUCADA"
elif [ -f "$TOKEN" ]; then
  SESION="sesión OK"
elif claude auth status >/dev/null 2>&1; then
  SESION="sesión OK"
else
  SESION="$CADUCADA"
fi

# Límite de uso de Claude: los videos esperan en 01_Entrada hasta la hora de reinicio.
USO=""
if [ -f "$ESPERA" ]; then
  HASTA_TS="$(grep -o '"hasta_ts": *[0-9]*' "$ESPERA" 2>/dev/null | grep -o '[0-9]*$')"
  HASTA="$(grep -o '"hasta": *"[^"]*"' "$ESPERA" 2>/dev/null | sed -e 's/.*T\([0-9][0-9]:[0-9][0-9]\).*/\1/')"
  if [ -n "$HASTA_TS" ] && [ "$HASTA_TS" -gt "$(date +%s)" ] 2>/dev/null; then
    if grep -q '"respaldo": *true' "$ESPERA" 2>/dev/null; then
      USO=" · ⏳ Claude sin uso disponible hasta las $HASTA: revisando con el juez de respaldo"
    else
      USO=" · ⏳ Claude sin uso disponible hasta las $HASTA: los videos esperan y se revisan solos"
    fi
  fi
fi

echo "Aura: motor OK · config OK · $COLA · $AUTO · $SESION$USO"
exit 0
