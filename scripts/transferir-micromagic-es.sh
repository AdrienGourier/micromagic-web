#!/bin/bash
# Transfiere micromagic.es de IONOS a Route 53 Domains, en la cuenta AWS de
# Rhino (088668667991, perfil `rhino`). La transferencia de un .es cuesta 0 $;
# la renovación, 10 $ al año (caduca el 17/09/2027).
#
# Hay que hacerlo antes del 27/12/2026: ese día termina el contrato de IONOS
# (85925345) y con él el dominio.
#
# Titular: Ingenieria y Bioproteccion Ambiental S.L. (CIF B86512613), igual que
# en IONOS, así que no es un cambio de titular. Route 53 exige que los
# contactos administrativo y técnico sean una persona física, con su DNI/NIE.
# Ese documento se teclea aquí, sin eco: no se guarda ni pasa por el chat.
#
# El código de autorización se lee de ~/.micromagic-es-authcode (chmod 600).
# Caduca: si Route 53 lo rechaza, pedir otro en IONOS (Dominios → micromagic.es
# → Transferencia y renovación → Mostrar código de autorización).
#
# Los servidores DNS son los de la zona de Route 53 ya creada (stack
# micromagic-es-dns), que tiene la web y el correo de forwardemail.
#
# Uso, en una Terminal normal (pide datos por teclado):
#   ./scripts/transferir-micromagic-es.sh            # pide el DNI/NIE y transfiere
#   ./scripts/transferir-micromagic-es.sh --probar   # enseña los contactos, sin enviar
# Seguimiento:
#   aws --profile rhino --region us-east-1 route53domains get-operation-detail --operation-id <id>

set -euo pipefail
PERFIL=rhino
REGION=us-east-1
DOMINIO=micromagic.es
CODIGO_FICHERO="$HOME/.micromagic-es-authcode"
CUENTA_ESPERADA=088668667991

PROBAR=0
[ "${1:-}" = "--probar" ] && PROBAR=1

cuenta=$(aws --profile "$PERFIL" sts get-caller-identity --query Account --output text)
if [ "$cuenta" != "$CUENTA_ESPERADA" ]; then
  echo "El perfil $PERFIL apunta a la cuenta $cuenta, no a $CUENTA_ESPERADA. Paro." >&2
  exit 1
fi

[ -r "$CODIGO_FICHERO" ] || { echo "Falta $CODIGO_FICHERO con el código de IONOS." >&2; exit 1; }
CODIGO=$(tr -d ' \n' < "$CODIGO_FICHERO")

NS=$(aws --profile "$PERFIL" --region "$REGION" cloudformation describe-stacks \
  --stack-name micromagic-es-dns \
  --query "Stacks[0].Outputs[?OutputKey=='ServidoresDNS'].OutputValue" --output text)
[ -n "$NS" ] || { echo "No encuentro los servidores DNS del stack micromagic-es-dns." >&2; exit 1; }

echo "Transferibilidad:"
aws --profile "$PERFIL" --region "$REGION" route53domains check-domain-transferability \
  --domain-name "$DOMINIO" --query Transferability.Transferable --output text

echo
echo "Contacto administrativo y técnico (persona física). Intro acepta el valor entre corchetes."
read -r -p "Nombre [Jacques]: " NOMBRE;      NOMBRE=${NOMBRE:-Jacques}
read -r -p "Apellidos [Gourier]: " APELLIDOS; APELLIDOS=${APELLIDOS:-Gourier}
read -r -p "Tipo de documento: 1 = DNI (español), 2 = NIE (extranjero residente) [2]: " T
case "${T:-2}" in
  1) TIPO=DNI_AND_NIF ;;
  2) TIPO=NIE ;;
  *) echo "Tipo no válido." >&2; exit 1 ;;
esac
read -r -s -p "Número de $TIPO (no se ve al teclear): " DOC; echo
DOC=$(printf '%s' "$DOC" | tr -d ' -' | tr '[:lower:]' '[:upper:]')
if [ "$TIPO" = NIE ] && ! [[ "$DOC" =~ ^[XYZ][0-9]{7}[A-Z]$ ]]; then
  echo "Un NIE es letra + 7 cifras + letra (X1234567L)." >&2; exit 1
fi
if [ "$TIPO" = DNI_AND_NIF ] && ! [[ "$DOC" =~ ^[0-9]{8}[A-Z]$ ]]; then
  echo "Un DNI es 8 cifras + letra (12345678Z)." >&2; exit 1
fi

umask 077
TMP=$(mktemp -d)
trap 'rm -P "$TMP"/* 2>/dev/null; rmdir "$TMP"' EXIT

DIRECCION='"AddressLine1": "Calle del Electrodo 72", "City": "Rivas-Vaciamadrid", "State": "Madrid", "CountryCode": "ES", "ZipCode": "28522", "PhoneNumber": "+34.630181219", "Email": "jlmgourier@hotmail.com"'

cat > "$TMP/titular.json" <<EOF
{"ContactType": "COMPANY", "OrganizationName": "Ingenieria y Bioproteccion Ambiental S.L.",
 "FirstName": "$NOMBRE", "LastName": "$APELLIDOS", $DIRECCION,
 "ExtraParams": [
   {"Name": "ES_LEGAL_FORM", "Value": "LIMITED_COMPANY"},
   {"Name": "ES_IDENTIFICATION_TYPE", "Value": "DNI_AND_NIF"},
   {"Name": "ES_IDENTIFICATION", "Value": "B86512613"}]}
EOF
cat > "$TMP/persona.json" <<EOF
{"ContactType": "PERSON", "FirstName": "$NOMBRE", "LastName": "$APELLIDOS", $DIRECCION,
 "ExtraParams": [
   {"Name": "ES_LEGAL_FORM", "Value": "INDIVIDUAL"},
   {"Name": "ES_IDENTIFICATION_TYPE", "Value": "$TIPO"},
   {"Name": "ES_IDENTIFICATION", "Value": "$DOC"}]}
EOF
python3 - "$NS" > "$TMP/ns.json" <<'PY'
import json, sys
print(json.dumps([{"Name": n} for n in sys.argv[1].split()]))
PY

echo
echo "Titular:"; cat "$TMP/titular.json"
echo "Admin y técnico:"; sed "s/$DOC/${DOC:0:1}*******${DOC: -1}/" "$TMP/persona.json"
echo "Servidores DNS: $NS"

if [ "$PROBAR" = 1 ]; then
  echo; echo "--probar: no se ha enviado nada."; exit 0
fi

echo
read -r -p "¿Enviar la transferencia de $DOMINIO a Route 53? (escribe si): " OK
[ "$OK" = si ] || { echo "Cancelado."; exit 1; }

aws --profile "$PERFIL" --region "$REGION" route53domains transfer-domain \
  --domain-name "$DOMINIO" \
  --duration-in-years 1 \
  --auth-code "$CODIGO" \
  --nameservers "file://$TMP/ns.json" \
  --registrant-contact "file://$TMP/titular.json" \
  --admin-contact "file://$TMP/persona.json" \
  --tech-contact "file://$TMP/persona.json" \
  --billing-contact "file://$TMP/persona.json" \
  --no-privacy-protect-admin-contact \
  --no-privacy-protect-billing-contact \
  --no-privacy-protect-registrant-contact \
  --no-privacy-protect-tech-contact \
  --auto-renew \
  --output text

echo
echo "Enviada. Route 53 manda los avisos a jlmgourier@hotmail.com: si llega uno que pide"
echo "aprobar la transferencia, hay que aprobarlo (hay 10 días)."
