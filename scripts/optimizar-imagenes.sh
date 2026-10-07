#!/bin/bash
# Compatible con el bash 3.2 que trae macOS: nada de ${var,,} ni arrays asociativos.
# Deja en public/uploads solo las imágenes que el contenido referencia, y las
# reduce a tamaño web. Los originales siguen en el tarball del backup, así que
# esto se puede repetir desde cero: extraer-imagenes.py y luego este script.
#
# Uso: ./scripts/optimizar-imagenes.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ANCHO_MAX=1600
CALIDAD=70

usadas=$(mktemp)
trap 'rm -f "$usadas"' EXIT
grep -ohE '\(/uploads/[^)]+\)' src/content/paginas/*.md | tr -d '()' | sort -u > "$usadas"

antes=$(du -sm public/uploads | cut -f1)

# 1. fuera las que no referencia nadie
borradas=0
while IFS= read -r -d '' f; do
  rel="${f#public}"
  grep -qxF "$rel" "$usadas" || { rm -f "$f"; borradas=$((borradas+1)); }
done < <(find public/uploads -type f -print0)
find public/uploads -type d -empty -delete 2>/dev/null || true

# 2. reducir las que quedan
tocadas=0
while IFS= read -r -d '' f; do
  min=$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')
  case "$min" in
    *.jpg|*.jpeg|*.png)
      ancho=$(sips -g pixelWidth "$f" 2>/dev/null | awk '/pixelWidth/{print $2}')
      [ -z "${ancho:-}" ] && continue
      if [ "$ancho" -gt "$ANCHO_MAX" ]; then
        sips -Z "$ANCHO_MAX" "$f" >/dev/null 2>&1 || true
        tocadas=$((tocadas+1))
      fi
      case "$min" in
        *.jpg|*.jpeg)
          sips -s format jpeg -s formatOptions "$CALIDAD" "$f" --out "$f" >/dev/null 2>&1 || true ;;
      esac ;;
  esac
done < <(find public/uploads -type f -print0)

despues=$(du -sm public/uploads | cut -f1)
echo "borradas sin usar: $borradas"
echo "redimensionadas:   $tocadas"
echo "public/uploads:    ${antes} MB -> ${despues} MB"
