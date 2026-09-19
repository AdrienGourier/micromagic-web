#!/bin/bash
# Sube a forwardemail el histórico que rescatar-correo.sh bajó de IONOS, para
# que los dos buzones reales no arranquen vacíos.
#
# mbsync sincroniza en ambos sentidos: el mismo Maildir que se descargó con
# `Sync Pull` se sube aquí con `Sync Push`.
#
# Credenciales en ~/.forwardemail-correo, chmod 600, FUERA del repo. Una línea
# por buzón, 'direccion:contraseña'. OJO: la contraseña NO es la de la cuenta de
# forwardemail, sino la que genera su panel para cada alias.
#
#   administracion@micromagic.tv:contraseñaDelAlias
#   info@rhinopaint.es:contraseñaDelAlias
#
# Uso:
#   ./scripts/subir-correo.sh                 usa el backup más reciente
#   ./scripts/subir-correo.sh <carpeta>       usa ese backup concreto
#   ./scripts/subir-correo.sh --probar        conecta y lista, no sube nada

set -uo pipefail

CREDS="$HOME/.forwardemail-correo"
CONF="$(mktemp -t mbsyncrc)"
SERVIDOR="imap.forwardemail.net"

trap 'rm -f "$CONF"' EXIT   # la configuración lleva contraseñas

command -v mbsync >/dev/null || { echo "Falta mbsync. Ejecuta: brew install isync" >&2; exit 1; }

modo="subir"
origen=""
case "${1:-}" in
  --probar) modo="probar" ;;
  "")       ;;
  *)        origen="$1" ;;
esac

# Por defecto, el rescate más reciente.
if [ -z "$origen" ]; then
  origen=$(find "$HOME/Backups" -maxdepth 1 -type d -name 'ionos-correo-*' 2>/dev/null | sort | tail -1)
fi
[ -n "$origen" ] && [ -d "$origen" ] || {
  echo "No encuentro ningún rescate en ~/Backups/ionos-correo-*." >&2
  echo "Ejecuta antes ./scripts/rescatar-correo.sh" >&2
  exit 1
}

[ -r "$CREDS" ] || { echo "No encuentro $CREDS (chmod 600, una línea 'direccion:contraseña')." >&2; exit 1; }
PERM=$(stat -f '%Lp' "$CREDS")
[ "$PERM" = "600" ] || { echo "AVISO: $CREDS tiene permisos $PERM. Corrígelo:  chmod 600 $CREDS" >&2; exit 1; }

echo "origen: $origen"
echo

subidas=0
fallos=0

while IFS= read -r linea || [ -n "$linea" ]; do
  case "$linea" in ''|\#*) continue ;; esac
  direccion="${linea%%:*}"
  clave="${linea#*:}"
  [ -n "$direccion" ] && [ -n "$clave" ] || continue

  carpeta="$origen/$direccion"
  if [ ! -d "$carpeta" ]; then
    echo "=== $direccion ==="
    echo "  no hay histórico rescatado en $carpeta, lo salto"
    continue
  fi

  n=$(find "$carpeta" \( -path '*/cur/*' -o -path '*/new/*' \) -type f 2>/dev/null | wc -l | tr -d ' ')
  canal=$(printf '%s' "$direccion" | tr -c 'a-zA-Z0-9' '-')

  cat > "$CONF" <<EOF
IMAPAccount $canal
Host $SERVIDOR
Port 993
User $direccion
Pass "$clave"
TLSType IMAPS
PipelineDepth 1

IMAPStore $canal-remoto
Account $canal

MaildirStore $canal-local
Path $carpeta/
Inbox $carpeta/INBOX
SubFolders Verbatim

Channel $canal
Far :$canal-remoto:
Near :$canal-local:
Patterns *
Create Far
Expunge None
Sync Push
EOF
  chmod 600 "$CONF"

  echo "=== $direccion ($n mensajes locales) ==="
  if [ "$modo" = "probar" ]; then
    mbsync -c "$CONF" --list "$canal" 2>&1 | sed 's/^/  /'
    continue
  fi

  if mbsync -c "$CONF" "$canal" 2>&1 | sed 's/^/  /'; then
    echo "  subido"
    subidas=$((subidas + 1))
  else
    echo "  FALLÓ. Revisa la contraseña del alias en el panel de forwardemail." >&2
    fallos=$((fallos + 1))
  fi
done < "$CREDS"

echo
echo "════════════════════════════════════════════"
echo "  buzones subidos: $subidas   fallos: $fallos"
echo "════════════════════════════════════════════"
echo
echo "Comprueba en el webmail de forwardemail que los mensajes están ahí antes"
echo "de cancelar nada en IONOS. Luego borra las credenciales:"
echo "  rm -P $CREDS"
[ "$fallos" -eq 0 ] || exit 1
