#!/usr/bin/env bash
#
# Instalador de VideoQA para Macs con Apple Silicon.
# Se puede volver a ejecutar las veces que haga falta: todo lo que ya esté
# instalado se salta.
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

# Carpeta donde está este script y raíz del paquete que te pasaron.
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAQUETE="$(cd "$AQUI/.." && pwd)"
DESTINO="$HOME/videoqa"

printf '\n\033[1m  VideoQA — instalación\033[0m\n'
printf '  Esto instala lo necesario y copia el programa a tu carpeta personal.\n'
printf '  Puede tardar entre 5 y 15 minutos. No cierres la ventana.\n'

# --- 1. Comprobar que es un Mac con chip Apple ------------------------------

paso "1/7  Revisando tu Mac"
if [ "$(uname -m)" != "arm64" ]; then
  abortar "Esta herramienta solo funciona en Macs con chip Apple (M1, M2, M3...). Tu Mac tiene un procesador Intel."
fi
ok "Mac con chip Apple. Perfecto."

# --- 2. Homebrew ------------------------------------------------------------

paso "2/7  Homebrew (el instalador de programas del Mac)"
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

paso "3/7  Programas de apoyo (uv y ffmpeg)"
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

paso "4/7  Claude Code"
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

# --- 5. Copiar el programa --------------------------------------------------

paso "5/7  Copiando el programa a tu carpeta personal"
ORIGEN="$PAQUETE/videoqa-proyecto"
if [ ! -d "$ORIGEN" ]; then
  abortar "Falta la carpeta 'videoqa-proyecto' dentro del paquete. Vuelve a descomprimir el archivo .zip completo y ejecuta el instalador desde ahí."
fi

mkdir -p "$DESTINO"
rsync -a --delete --exclude .venv --exclude .git "$ORIGEN/" "$DESTINO/" \
  || abortar "No se pudo copiar el programa a $DESTINO."
ok "Copiado en $DESTINO"

# --- 6. Preparar Python -----------------------------------------------------

paso "6/7  Preparando el motor (Python y librerías)"
info "Esto es lo que más tarda. Paciencia."
cd "$DESTINO"
uv python install 3.12 || abortar "No se pudo instalar Python 3.12."
uv sync                || abortar "No se pudieron instalar las librerías. Revisa tu conexión a internet e inténtalo otra vez."
ok "Motor listo."

# --- 7. Siguientes pasos ----------------------------------------------------

paso "7/7  ¡Listo!"
cat <<'FIN'

    Ya está todo instalado. Falta un último paso, y lo haces hablando:

      1. Abre Claude Code en la carpeta ~/videoqa
      2. Escribe:  /instalar
      3. Sigue lo que te vaya diciendo (te va a pedir que elijas la carpeta
         de videos de Drive).

    La primera vez que abras Claude te pedirá iniciar sesión: se abre el
    navegador y entras con tu cuenta. Solo pasa una vez.

FIN

respuesta=""
read -r -p "    ¿Abrir Claude ahora? (s/n) " respuesta || true
case "${respuesta:-n}" in
  [sSyY]*)
    printf '\n    Abriendo Claude. Recuerda: escribe  /instalar\n\n'
    cd "$DESTINO"
    exec claude
    ;;
  *)
    printf '\n    Sin problema. Cuando quieras, abre la Terminal y escribe:\n'
    printf '        cd ~/videoqa && claude\n'
    printf '    y luego  /instalar\n\n'
    ;;
esac
