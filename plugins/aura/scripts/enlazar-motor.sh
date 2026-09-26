#!/usr/bin/env bash
#
# Deja el motor (~/videoqa) enlazado con internet y listo para actualizarse.
#
# Hace falta porque el motor se puede haber instalado como copia de carpeta
# (un disco, un AirDrop): esa copia no trae enlace, así que `git pull` no tiene
# de dónde traer nada y la persona se queda clavada en una versión vieja para
# siempre.
#
# Nunca pierde lo que hubiera en la carpeta: si la copia tiene algo distinto de
# la versión de internet, lo guarda antes en una rama local `copia-local-...`
# y lo dice. Nunca sube nada a internet.
#
# Imprime UNA línea; la primera palabra es el resultado, para que la skill sepa
# qué contar:
#
#   ya-enlazado          el motor ya estaba enlazado y al día o por detrás
#   enlazado             se enlazó y se puso la versión de internet
#   enlazado-con-copia   igual, y lo que tenía de distinto quedó guardado
#   no-instalado         no existe la carpeta del motor
#   sin-internet         no se pudo hablar con GitHub
#   error                cualquier otra cosa
#
set -u

PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

MOTOR="${VIDEOQA_MOTOR:-$HOME/videoqa}"
REMOTO="${VIDEOQA_REMOTO:-https://github.com/hongs05/videoqa}"
RAMA="${VIDEOQA_RAMA:-main}"

g()  { git -C "$MOTOR" "$@"; }
gq() { git -C "$MOTOR" "$@" >/dev/null 2>&1; }

fin() { echo "$*"; case "${1%% *}" in ya-enlazado|enlazado|enlazado-con-copia) exit 0 ;; *) exit 1 ;; esac; }

[ -d "$MOTOR" ] || fin "no-instalado El motor no está en $MOTOR"
command -v git >/dev/null 2>&1 || fin "error Falta git en esta Mac"

# --- 1. Que sea un repositorio ---------------------------------------------

if ! gq rev-parse --git-dir; then
  gq init -q || fin "error No se pudo preparar la carpeta del motor"
fi

# Lo pesado y lo generado no entra en la copia de seguridad.
EXCLUDE="$(g rev-parse --git-path info/exclude 2>/dev/null)"
if [ -n "$EXCLUDE" ]; then
  mkdir -p "$(dirname "$EXCLUDE")"
  for patron in '.venv/' '__pycache__/' '*.pyc'; do
    grep -qxF "$patron" "$EXCLUDE" 2>/dev/null || printf '%s\n' "$patron" >> "$EXCLUDE"
  done
fi

# --- 2. Que apunte a internet ----------------------------------------------

if ! gq remote get-url origin; then
  gq remote add origin "$REMOTO" || fin "error No se pudo apuntar el motor a internet"
  NUEVO_ENLACE=1
else
  NUEVO_ENLACE=0
fi

gq fetch --quiet origin "$RAMA" || fin "sin-internet No se pudo descargar la versión nueva"

# --- 3. ¿La copia tiene algo que no esté en internet? -----------------------

SUCIO=0
[ -n "$(g status --porcelain 2>/dev/null)" ] && SUCIO=1
if gq rev-parse --verify HEAD; then
  gq merge-base --is-ancestor HEAD "origin/$RAMA" || SUCIO=1
else
  SUCIO=1   # recién iniciado: todavía no hay nada guardado
fi

if [ "$SUCIO" = 0 ]; then
  [ "$NUEVO_ENLACE" = 1 ] || fin "ya-enlazado El motor ya estaba enlazado"
fi

# --- 4. Guardar lo que tenga de distinto, sin tocar internet ----------------

COPIA=""
if [ "$SUCIO" = 1 ]; then
  COPIA="copia-local-$(date +%Y%m%d-%H%M%S)"
  gq checkout -q -B "$COPIA" || fin "error No se pudo guardar lo que tenía la copia"
  if [ -n "$(g status --porcelain 2>/dev/null)" ]; then
    gq add -A || fin "error No se pudo guardar lo que tenía la copia"
    gq -c user.name=Aura -c user.email=aura@videoqa.local \
       commit -q -m "Copia local del motor antes de enlazarlo con internet" \
      || fin "error No se pudo guardar lo que tenía la copia"
  fi
fi

# --- 5. Ponerle la versión de internet --------------------------------------

gq checkout -q -B "$RAMA" "origin/$RAMA" || fin "error No se pudo poner la versión nueva"
gq branch --set-upstream-to "origin/$RAMA" "$RAMA"

if [ -n "$COPIA" ] && gq rev-parse --verify "$COPIA"; then
  fin "enlazado-con-copia Enlazado; lo que tenía la copia quedó guardado en esta Mac ($COPIA)"
fi
fin "enlazado El motor quedó enlazado y con la versión nueva"
