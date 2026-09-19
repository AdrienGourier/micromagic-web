#!/bin/bash
# Descarga entera cada cuenta de correo de IONOS a Maildir local, antes de
# cancelarlas. Cuando IONOS cierra un buzón su histórico NO se recupera, así
# que esto se ejecuta y se verifica ANTES de tocar nada en el panel.
#
# Usa mbsync (isync), que sincroniza IMAP contra un Maildir local.
# imapsync NO sirve aquí: solo va de servidor a servidor.
#
#   brew install isync
#
# Credenciales en ~/.ionos-correo, chmod 600, FUERA del repo. Una línea por
# buzón, la contraseña es todo lo que va tras el primer ':' (puede llevar
# dos puntos, espacios o lo que sea):
#
#   info@micromagic.tv:laContraseña
#   administracion@micromagic.tv:otraContraseña
#
# Uso:
#   ./scripts/rescatar-correo.sh            descarga todo
#   ./scripts/rescatar-correo.sh --listar   solo cuenta mensajes, no descarga

set -uo pipefail

CREDS="$HOME/.ionos-correo"
DESTINO="$HOME/Backups/ionos-correo-$(date +%Y-%m-%d)"
CONF="$(mktemp -t mbsyncrc)"
SERVIDOR="imap.ionos.es"

trap 'rm -f "$CONF"' EXIT   # la configuración lleva contraseñas: no sobrevive

command -v mbsync >/dev/null || { echo "Falta mbsync. Ejecuta: brew install isync" >&2; exit 1; }

if [ ! -r "$CREDS" ]; then
  echo "No encuentro $CREDS." >&2
  echo "Créalo con una línea 'direccion:contraseña' por buzón y protégelo:" >&2
  echo "  chmod 600 $CREDS" >&2
  exit 1
fi

# Que nadie más pueda leer las contraseñas.
PERM=$(stat -f '%Lp' "$CREDS")
if [ "$PERM" != "600" ]; then
  echo "AVISO: $CREDS tiene permisos $PERM. Corrígelo:  chmod 600 $CREDS" >&2
  exit 1
fi

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

total_cuentas=0
fallos=0

while IFS= read -r linea || [ -n "$linea" ]; do
  case "$linea" in ''|\#*) continue ;; esac
  direccion="${linea%%:*}"
  clave="${linea#*:}"
  [ -n "$direccion" ] && [ -n "$clave" ] || { echo "línea ilegible, la salto"; continue; }

  # Un nombre de canal sin caracteres raros para mbsync.
  canal=$(printf '%s' "$direccion" | tr -c 'a-zA-Z0-9' '-')
  carpeta="$DESTINO/$direccion"
  mkdir -p "$carpeta"

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
Create Near
Expunge None
Sync Pull
EOF
  chmod 600 "$CONF"

  echo
  echo "=== $direccion ==="
  if [ "${1:-}" = "--listar" ]; then
    mbsync -c "$CONF" --list "$canal" 2>&1 | sed 's/^/  /'
    continue
  fi

  if mbsync -c "$CONF" "$canal" 2>&1 | sed 's/^/  /'; then
    n=$(find "$carpeta" -type f -path '*/cur/*' -o -type f -path '*/new/*' 2>/dev/null | wc -l | tr -d ' ')
    echo "  descargados: $n mensajes"
    total_cuentas=$((total_cuentas + 1))
  else
    echo "  FALLÓ. Revisa la contraseña de $direccion." >&2
    fallos=$((fallos + 1))
  fi
done < "$CREDS"

echo
echo "════════════════════════════════════════════"
echo "  cuentas descargadas: $total_cuentas   fallos: $fallos"
echo "  destino: $DESTINO"
find "$DESTINO" -maxdepth 1 -mindepth 1 -type d | while read -r d; do
  printf "    %-38s %6s mensajes  %s\n" "$(basename "$d")" \
    "$(find "$d" \( -path '*/cur/*' -o -path '*/new/*' \) -type f 2>/dev/null | wc -l | tr -d ' ')" \
    "$(du -sh "$d" 2>/dev/null | cut -f1)"
done
echo "════════════════════════════════════════════"
echo
echo "Comprueba que los totales cuadran con lo que muestra el panel de IONOS"
echo "ANTES de cancelar ningún buzón. Luego borra las credenciales:"
echo "  rm -P $CREDS"
[ "$fallos" -eq 0 ] || exit 1
