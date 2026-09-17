#!/usr/bin/env bash
#
# Construye el paquete de demo que se le entrega a la revisora.
#
#   ~/Desktop/VideoQA-demo.zip
#     VideoQA-demo/
#       Instalar VideoQA.command     <- doble clic
#       LEEME.md
#       instalar/install.sh
#       videoqa-proyecto/            <- el repo (git archive HEAD)
#
# El contenido de videoqa-proyecto/ sale de `git archive HEAD`, así que lleva
# lo versionado y nada más: sin .venv, sin .git, sin .superpowers, sin
# tests/fixtures/out. Sí lleva .claude/skills, .claude/settings.json,
# reglas.yaml, launchd/ y docs/.
#
# Uso:  bash scripts/build_demo_zip.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOMBRE="VideoQA-demo"
ZIP="$HOME/Desktop/$NOMBRE.zip"

cd "$REPO"

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "error: el repositorio no tiene ningún commit todavía" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "aviso: hay cambios sin commitear; el paquete usa HEAD y no los incluirá" >&2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

RAIZ="$TMP/$NOMBRE"
mkdir -p "$RAIZ/instalar" "$RAIZ/videoqa-proyecto"

# 1. El proyecto, tal y como está en HEAD.
git archive HEAD | tar -x -C "$RAIZ/videoqa-proyecto"

# 2. El instalador y el lanzador de doble clic en la raíz del paquete.
cp "$REPO/instalar/install.sh" "$RAIZ/instalar/install.sh"
cp "$REPO/instalar/Instalar VideoQA.command" "$RAIZ/Instalar VideoQA.command"
cp "$REPO/LEEME.md" "$RAIZ/LEEME.md"

# El .command queda en la raíz, así que tiene que entrar en instalar/ antes de
# lanzar install.sh (dentro del repo están juntos y no hace falta).
chmod +x "$RAIZ/Instalar VideoQA.command" "$RAIZ/instalar/install.sh"

# 3. Comprimir (-X quita metadatos de macOS que solo ensucian el zip).
mkdir -p "$HOME/Desktop"
rm -f "$ZIP"
( cd "$TMP" && zip -q -r -X "$ZIP" "$NOMBRE" )

TAM="$(du -h "$ZIP" | cut -f1 | tr -d ' ')"
echo
echo "Paquete listo:"
echo "  $ZIP"
echo "  Tamaño: $TAM"
echo
echo "Pásaselo tal cual. Ella lo descomprime y hace doble clic en 'Instalar VideoQA.command'."
