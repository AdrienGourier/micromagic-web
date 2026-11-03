#!/bin/bash
# Guarda las contraseñas de los buzones de forwardemail en ~/.forwardemail-correo
# (chmod 600, fuera del repo) sin que se vean en pantalla ni queden en el
# historial de la terminal, y comprueba cada una contra el servidor al momento.
#
# Pide las tres en orden. Intro deja la que ya hubiera guardada, o ninguna: así
# se puede volver a ejecutar para añadir director@ cuando tenga contraseña.
#
# Las de administracion@ e info@rhinopaint.es son las que ya tiene puestas el
# Outlook. No se regeneran: forwardemail cifra el buzón con ellas.
#
# Uso: ./scripts/guardar-claves.sh

set -uo pipefail
CREDS="${CREDS:-$HOME/.forwardemail-correo}"
SERVIDOR="${SERVIDOR:-imap.forwardemail.net}"
BUZONES=(info@rhinopaint.es administracion@micromagic.tv director@micromagic.tv)
[ $# -gt 0 ] && BUZONES=("$@")

umask 077
touch "$CREDS"
chmod 600 "$CREDS"

echo "Lo que escribas no se verá. Pega la contraseña y pulsa Intro."
echo
for d in "${BUZONES[@]}"; do
  if grep -q "^${d}:" "$CREDS"; then aviso="Intro = dejar la guardada"; else aviso="Intro = saltar"; fi
  printf '  %s (%s): ' "$d" "$aviso"
  IFS= read -rs p; echo
  [ -n "$p" ] || continue
  grep -v "^${d}:" "$CREDS" > "$CREDS.tmp"
  printf '%s:%s\n' "$d" "$p" >> "$CREDS.tmp"
  mv "$CREDS.tmp" "$CREDS"
done
unset p
chmod 600 "$CREDS"

echo
echo "Comprobando contra ${SERVIDOR}…"
python3 -I - "$CREDS" "$SERVIDOR" <<'PY'
import imaplib, sys
creds, servidor = sys.argv[1], sys.argv[2]
mal = 0
for linea in open(creds).read().splitlines():
    if ":" not in linea or linea.startswith("#"):
        continue
    direccion, clave = linea.split(":", 1)   # la contraseña puede llevar ':'
    try:
        m = imaplib.IMAP4_SSL(servidor, 993, timeout=30)
        m.login(direccion, clave)
        m.logout()
        print(f"  OK     {direccion}")
    except imaplib.IMAP4.error:
        print(f"  FALLA  {direccion}  — el servidor no acepta esa contraseña")
        mal += 1
    except OSError as e:
        print(f"  ?      {direccion}  — no se pudo conectar: {e}")
        mal += 1
if mal:
    print("\nSi falla administracion@ o info@rhinopaint.es, NO generes una nueva:")
    print("vuelve a ejecutar esto y pega la que tiene puesta el Outlook.")
sys.exit(1 if mal else 0)
PY
