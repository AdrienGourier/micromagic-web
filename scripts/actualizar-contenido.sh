#!/bin/bash
# Rehace el contenido del sitio desde el WordPress antiguo, en el orden correcto.
# Los tres pasos dependen unos de otros: extraer-imagenes reescribe rutas que
# solo existen tras extraer-wp, y optimizar necesita saber qué referencia el
# Markdown ya reapuntado.
#
# Uso: ./scripts/actualizar-contenido.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/3  contenido desde la base de datos"
python3 scripts/extraer-wp.py

echo
echo "2/3  imágenes originales desde el backup"
python3 scripts/extraer-imagenes.py

echo
echo "3/3  podar y reducir a tamaño web"
bash scripts/optimizar-imagenes.sh
