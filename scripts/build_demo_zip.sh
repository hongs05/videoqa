#!/usr/bin/env bash
#
# Construye el paquete de bienvenida que se le entrega a la revisora.
#
#   ~/Desktop/VideoQA-demo.zip
#     VideoQA-demo/
#       Instalar VideoQA.command     <- doble clic
#       LEEME.md
#       instalar/install.sh
#
# El paquete ya no lleva el proyecto dentro: el instalador deja los programas
# base y el plugin `aura`, y el motor se descarga después con /aura:instalar.
#
# Uso:  bash scripts/build_demo_zip.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOMBRE="VideoQA-demo"
ZIP="$HOME/Desktop/$NOMBRE.zip"

cd "$REPO"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

RAIZ="$TMP/$NOMBRE"
mkdir -p "$RAIZ/instalar"

# El instalador, el lanzador de doble clic y la guía del equipo.
cp "$REPO/instalar/install.sh" "$RAIZ/instalar/install.sh"
cp "$REPO/instalar/Instalar VideoQA.command" "$RAIZ/Instalar VideoQA.command"
cp "$REPO/LEEME.md" "$RAIZ/LEEME.md"

# El .command queda en la raíz del paquete, así que tiene que entrar en
# instalar/ antes de lanzar install.sh (dentro del repo están juntos y no hace
# falta).
chmod +x "$RAIZ/Instalar VideoQA.command" "$RAIZ/instalar/install.sh"

# Comprimir (-X quita metadatos de macOS que solo ensucian el zip).
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
