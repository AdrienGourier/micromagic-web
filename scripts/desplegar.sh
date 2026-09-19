#!/bin/bash
# Construye el sitio y lo publica en S3 + CloudFront.
# Sigue el patrón de portfolio-repo/scripts/deploy-frontend.sh: lee los outputs
# del stack en vez de llevar los identificadores escritos a mano.
#
# Uso: ./scripts/desplegar.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PERFIL="${AWS_PROFILE:-rhino}"
REGION="us-east-1"          # CloudFront + ACM viven aquí
STACK="micromagic-web"

echo "=== perfil $PERFIL / stack $STACK ==="
BUCKET=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --profile "$PERFIL" --query "Stacks[0].Outputs[?OutputKey=='BucketSitio'].OutputValue" \
  --output text)
DIST=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --profile "$PERFIL" --query "Stacks[0].Outputs[?OutputKey=='DistribucionId'].OutputValue" \
  --output text)

if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "No encuentro el stack $STACK. Despliégalo primero:" >&2
  echo "  aws cloudformation deploy --template-file template.yaml \\" >&2
  echo "    --stack-name $STACK --region $REGION --profile $PERFIL \\" >&2
  echo "    --parameter-overrides CertificadoArn=<arn-del-certificado>" >&2
  exit 1
fi

echo "bucket: $BUCKET"
echo "distribución: $DIST"
echo
echo "=== construyendo ==="
npm run build

echo
echo "=== sincronizando ==="
# Los ficheros con huella en el nombre pueden cachearse para siempre.
aws s3 sync dist/ "s3://$BUCKET/" --profile "$PERFIL" --delete \
  --exclude "*.html" --cache-control "public,max-age=31536000,immutable"
# El HTML no: debe revalidarse para que un despliegue se vea al instante.
aws s3 sync dist/ "s3://$BUCKET/" --profile "$PERFIL" --delete \
  --exclude "*" --include "*.html" --cache-control "public,max-age=0,must-revalidate"

echo
echo "=== invalidando CloudFront ==="
ID=$(aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" \
  --profile "$PERFIL" --query 'Invalidation.Id' --output text)
echo "invalidación $ID lanzada"

URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --profile "$PERFIL" --query "Stacks[0].Outputs[?OutputKey=='UrlCloudFront'].OutputValue" \
  --output text)
echo
echo "listo: $URL"
