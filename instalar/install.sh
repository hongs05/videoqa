#!/usr/bin/env bash
#
# Instalador de VideoQA para Macs con Apple Silicon.
# Se puede volver a ejecutar las veces que haga falta: todo lo que ya esté
# instalado se salta.
#
# Deja listos los programas base (Homebrew, uv, ffmpeg, Claude Code) y el
# plugin `aura`. El motor en sí (~/videoqa) lo trae después `/aura:instalar`,
# hablando con Claude.
#
set -euo pipefail

# --- utilidades de presentación --------------------------------------------

paso()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()    { printf '    ✅ %s\n' "$*"; }
info()  { printf '    %s\n' "$*"; }
aviso() { printf '    ⚠️  %s\n' "$*"; }
error() { printf '\n\033[1;31m❌ %s\033[0m\n' "$*" >&2; }

abortar() {
  error "$1"
  printf '\n    Si no sabes qué hacer, manda una foto de esta ventana a quien te pasó la herramienta.\n\n'
  exit 1
}

# De dónde se instala el plugin. Se puede apuntar a una copia local para
# probar:  MARKETPLACE_SOURCE=/ruta/al/repo bash install.sh
MARKETPLACE="${MARKETPLACE_SOURCE:-hongs05/videoqa}"

printf '\n\033[1m  VideoQA — instalación\033[0m\n'
printf '  Esto instala los programas necesarios y los comandos de Aura.\n'
printf '  Puede tardar entre 5 y 15 minutos. No cierres la ventana.\n'

# --- 1. Comprobar que es un Mac con chip Apple ------------------------------

paso "1/5  Revisando tu Mac"
if [ "$(uname -m)" != "arm64" ]; then
  abortar "Esta herramienta solo funciona en Macs con chip Apple (M1, M2, M3...). Tu Mac tiene un procesador Intel."
fi
ok "Mac con chip Apple. Perfecto."

# --- 2. Homebrew ------------------------------------------------------------

paso "2/5  Homebrew (el instalador de programas del Mac)"
if [ -x /opt/homebrew/bin/brew ]; then
  ok "Ya estaba instalado."
else
  info "No lo tienes. Lo instalo ahora."
  info "IMPORTANTE: te va a pedir una contraseña. Es la contraseña con la que"
  info "enciendes el Mac. Al escribirla no se ve nada en pantalla; es normal."
  info "Escríbela y pulsa Enter."
  printf '\n'
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    || abortar "No se pudo instalar Homebrew. Revisa tu conexión a internet e inténtalo otra vez."
  ok "Homebrew instalado."
fi

eval "$(/opt/homebrew/bin/brew shellenv)"

# Dejarlo también para las próximas veces que abra la Terminal.
ZPROFILE="$HOME/.zprofile"
LINEA_BREW='eval "$(/opt/homebrew/bin/brew shellenv)"'
touch "$ZPROFILE"
if ! grep -qF "$LINEA_BREW" "$ZPROFILE"; then
  printf '\n%s\n' "$LINEA_BREW" >> "$ZPROFILE"
fi

# --- 3. uv y ffmpeg ---------------------------------------------------------

paso "3/5  Programas de apoyo (uv y ffmpeg)"
for prog in uv ffmpeg; do
  if command -v "$prog" >/dev/null 2>&1; then
    ok "$prog ya estaba instalado."
  else
    info "Instalando $prog... (esto tarda un poco)"
    brew install "$prog" || abortar "No se pudo instalar $prog. Revisa tu conexión a internet e inténtalo otra vez."
    ok "$prog instalado."
  fi
done

# --- 4. Claude Code ---------------------------------------------------------

paso "4/5  Claude Code"
export PATH="$HOME/.local/bin:$PATH"
if command -v claude >/dev/null 2>&1; then
  ok "Ya estaba instalado."
else
  info "Instalando Claude Code..."
  curl -fsSL https://claude.ai/install.sh | bash \
    || abortar "No se pudo instalar Claude Code. Revisa tu conexión a internet e inténtalo otra vez."
  ok "Claude Code instalado."
fi

LINEA_PATH='export PATH="$HOME/.local/bin:$PATH"'
if ! grep -qF "$LINEA_PATH" "$ZPROFILE"; then
  printf '\n%s\n' "$LINEA_PATH" >> "$ZPROFILE"
fi

# --- 5. El plugin Aura ------------------------------------------------------

paso "5/5  Los comandos de Aura"
info "Descargando el catálogo..."
claude plugin marketplace add "$MARKETPLACE" \
  || abortar "No se pudo descargar el catálogo de plugins. Revisa tu conexión a internet e inténtalo otra vez."

info "Instalando Aura..."
claude plugin install aura@videoqa \
  || abortar "No se pudo instalar el plugin Aura. Revisa tu conexión a internet e inténtalo otra vez."
ok "Aura instalada."

# --- Siguientes pasos -------------------------------------------------------

paso "¡Listo!"
cat <<'FIN'

    Ya está todo instalado. Falta un último paso, y lo haces hablando:

      1. Abre Claude (la aplicación, pestaña Code) o escribe `claude` en esta
         ventana.
      2. Escribe:  /aura:instalar
      3. Sigue lo que te vaya diciendo (te va a pedir que elijas la carpeta
         de videos de Drive).

    La primera vez que abras Claude te pedirá iniciar sesión: se abre el
    navegador y entras con tu cuenta. Solo pasa una vez.

FIN

respuesta=""
read -r -p "    ¿Abrir Claude ahora? (s/n) " respuesta || true
case "${respuesta:-n}" in
  [sSyY]*)
    printf '\n    Abriendo Claude. Recuerda: escribe  /aura:instalar\n\n'
    cd "$HOME"
    exec claude
    ;;
  *)
    printf '\n    Sin problema. Cuando quieras, abre Claude (app, pestaña Code)\n'
    printf '    o escribe en la Terminal:\n'
    printf '        claude\n'
    printf '    y luego  /aura:instalar\n\n'
    ;;
esac
