#!/usr/bin/env bash
#
# Deja guardada la sesión de Claude para que VideoQA revise videos sin que la
# sesión caduque. Lo ejecuta la persona en la Terminal (doble clic o `open`).
# Pide autorizar en el navegador una vez. Claude (la app) nunca ve el token.
#
# Variables para tests: VIDEOQA_HOME (dónde guardar), GUARDAR_TOKEN_SIN_PAUSA=1
# (no esperar Enter al final).
set -u

HOME_VQA="${VIDEOQA_HOME:-$HOME/.videoqa}"
TOKEN_FILE="$HOME_VQA/token"
PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"

pausa() {
  if [ -z "${GUARDAR_TOKEN_SIN_PAUSA:-}" ]; then
    echo
    read -r -p "Pulsa Enter para cerrar esta ventana." _
  fi
}

echo "═══════════════════════════════════════════════"
echo "  VideoQA · guardar la sesión de Claude"
echo "═══════════════════════════════════════════════"
echo
if ! command -v claude >/dev/null 2>&1; then
  echo "No encuentro el programa 'claude' en esta Mac."
  echo "Vuelve a Claude y escribe /aura:instalar para que lo instale."
  pausa; exit 1
fi

echo "Se va a abrir el navegador. Autoriza con tu cuenta de Claude y,"
echo "si te pide pegar un código aquí, pégalo y pulsa Enter."
echo

SALIDA_TMP="$(mktemp)"
trap 'rm -f "$SALIDA_TMP"' EXIT
# stdin sigue siendo la Terminal, así setup-token puede pedir el código.
claude setup-token 2>&1 | tee "$SALIDA_TMP"
TOKEN="$(grep -oE 'sk-ant-oat01-[A-Za-z0-9_-]+' "$SALIDA_TMP" | tail -1)"

if [ -z "$TOKEN" ]; then
  echo
  echo "No vi el token en la pantalla. Si claude lo mostró, cópialo y pégalo aquí"
  echo "(no se verá mientras lo pegas). Si no, pulsa Enter para salir."
  read -r -s -p "> " TOKEN
  echo
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
fi

if [ -z "$TOKEN" ]; then
  echo "No se guardó ninguna sesión. Vuelve a Claude y dile «arregla la sesión» para intentarlo otra vez."
  pausa; exit 1
fi

mkdir -p "$HOME_VQA"
umask 077
printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo
echo "✅ Sesión guardada. Comprobando que Claude responde…"
if command -v uv >/dev/null 2>&1 && [ -d "$HOME/videoqa" ]; then
  uv run --project "$HOME/videoqa" videoqa doctor || { echo "La sesión quedó guardada pero Claude no respondió. Vuelve a Claude y dile «arregla la sesión»."; pausa; exit 1; }
fi
echo
echo "Listo. Ya puedes cerrar esta ventana y volver a Claude."
pausa
exit 0
