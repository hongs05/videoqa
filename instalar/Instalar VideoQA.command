#!/usr/bin/env bash
# Haz doble clic en este archivo para instalar VideoQA.
cd "$(dirname "$0")" || exit 1

# En el paquete que se entrega, este archivo está en la raíz y el instalador
# dentro de la carpeta "instalar/". En el repositorio, están juntos.
if [ ! -f install.sh ] && [ -f instalar/install.sh ]; then
  cd instalar || exit 1
fi

bash install.sh
estado=$?

printf '\n'
if [ "$estado" -ne 0 ]; then
  printf '  La instalación se detuvo. Mira el mensaje de arriba.\n'
fi
read -r -p "Pulsa Enter para cerrar" _
exit "$estado"
