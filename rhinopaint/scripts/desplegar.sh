#!/bin/bash
# Sube la copia estática de rhinopaint.es (rhinopaint/sitio) al bucket del stack
# rhinopaint-web, en la cuenta AWS de Rhino (088668667991, perfil `rhino`), y
# vacía la caché de CloudFront.
#
# Las páginas se cachean 5 minutos; el resto (CSS, JS, imágenes, fuentes),
# una semana: la web está congelada, no cambia.
#
# Uso:
#   python3 rhinopaint/scripts/copiar-web.py --salida rhinopaint/sitio   # solo mientras viva el WordPress de IONOS
#   python3 rhinopaint/scripts/probar-local.py rhinopaint/sitio
#   ./rhinopaint/scripts/desplegar.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PERFIL=rhino
REGION=us-east-1
CUENTA_ESPERADA=088668667991
SITIO=sitio

cuenta=$(aws --profile "$PERFIL" sts get-caller-identity --query Account --output text)
if [ "$cuenta" != "$CUENTA_ESPERADA" ]; then
  echo "El perfil $PERFIL apunta a la cuenta $cuenta, no a $CUENTA_ESPERADA. Paro." >&2
  exit 1
fi
[ -f "$SITIO/index.html" ] || { echo "No hay copia en rhinopaint/$SITIO." >&2; exit 1; }

salida() {
  aws --profile "$PERFIL" --region "$REGION" cloudformation describe-stacks \
    --stack-name rhinopaint-web \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
BUCKET=$(salida BucketSitio)
DISTRIBUCION=$(salida DistribucionId)

# Primero todo menos las páginas, para que una página nueva nunca apunte a un
# fichero que aún no está.
aws --profile "$PERFIL" s3 sync "$SITIO" "s3://$BUCKET" --delete --only-show-errors \
  --exclude "*.html" --exclude "*.xml" --exclude "robots.txt" \
  --cache-control "public, max-age=604800"
aws --profile "$PERFIL" s3 sync "$SITIO" "s3://$BUCKET" --only-show-errors \
  --exclude "*" --include "*.html" --include "*.xml" --include "robots.txt" \
  --cache-control "public, max-age=300"

# Tipos que el sistema no siempre conoce.
for ext in woff2:font/woff2 woff:font/woff svg:image/svg+xml webp:image/webp; do
  aws --profile "$PERFIL" s3 cp "$SITIO" "s3://$BUCKET" --recursive --only-show-errors \
    --exclude "*" --include "*.${ext%%:*}" \
    --content-type "${ext#*:}" --cache-control "public, max-age=604800"
done

aws --profile "$PERFIL" cloudfront create-invalidation --distribution-id "$DISTRIBUCION" \
  --paths "/*" --query Invalidation.Id --output text
echo "Subido a s3://$BUCKET; caché de $DISTRIBUCION invalidada."
