#!/bin/bash
# Sube a forwardemail el histórico que rescatar-correo.sh bajó de IONOS, para
# que los tres buzones reales no arranquen vacíos.
#
# mbsync sincroniza en ambos sentidos: el mismo Maildir que se descargó con
# `Sync Pull` se sube aquí con `Sync Push`.
#
# El almacén remoto se llama distinto que en rescatar-correo.sh a propósito:
# mbsync nombra su estado por almacén, y con el mismo nombre leería el estado
# de IONOS, creería los correos ya subidos y no subiría nada.
# CopyArrivalDate conserva la fecha de llegada original (la del fichero).
#
# Las carpetas especiales cambian de nombre según mapa-carpetas.txt
# («Elementos enviados» → la \Sent de forwardemail…): un canal de mbsync por
# carpeta mapeada, y otro para el resto con su mismo nombre, todos en un grupo.
# El resto se nombra carpeta a carpeta y no con `Patterns *`: con el asterisco,
# cada carpeta que solo existe en forwardemail (su Trash, su Sent…) da error y
# la subida acaba en fallo aunque todo haya subido bien (comprobado).
#
# Credenciales en ~/.forwardemail-correo, chmod 600, FUERA del repo. Una línea
# por buzón, 'direccion:contraseña'. OJO: la contraseña NO es la de la cuenta de
# forwardemail, sino la que genera su panel para cada alias. Y no se regenera
# una que ya exista: forwardemail cifra el buzón con ella.
#
#   info@rhinopaint.es:contraseñaDelAlias
#   administracion@micromagic.tv:contraseñaDelAlias
#   director@micromagic.tv:contraseñaDelAlias
#
# Uso:
#   ./scripts/subir-correo.sh                        todo, del rescate más reciente
#   ./scripts/subir-correo.sh <carpeta-rescate>      de ese rescate
#   ./scripts/subir-correo.sh --buzon info@rhinopaint.es       un solo buzón
#   ./scripts/subir-correo.sh --buzon … --carpeta IMPORTANTE   una sola carpeta
#   ./scripts/subir-correo.sh --probar               enseña qué subiría, sin tocar nada
#   ./scripts/subir-correo.sh --mostrar-config       la configuración, sin conectar
#
# Se puede cortar y relanzar: mbsync guarda por dónde iba.
#
# AuthMechs PLAIN es obligatorio: forwardemail anuncia también PLAIN-CLIENTTOKEN,
# mbsync lo prefiere, y el plugin SASL de macOS que lo implementa falla con
# «SASL(-7): invalid parameter supplied». IONOS no lo anuncia.

set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CREDS="${CREDS:-$HOME/.forwardemail-correo}"
MAPA="${MAPA:-$DIR/mapa-carpetas.txt}"
CONF="$(mktemp -t mbsyncrc)"
SERVIDOR="imap.forwardemail.net"

trap 'rm -f "$CONF"' EXIT   # la configuración lleva contraseñas

command -v mbsync >/dev/null || { echo "Falta mbsync. Ejecuta: brew install isync" >&2; exit 1; }

modo="subir"; origen=""; solo_buzon=""; solo_carpeta=""
while [ $# -gt 0 ]; do
  case "$1" in
    --probar)         modo="probar" ;;
    --mostrar-config) modo="config" ;;
    --buzon)          solo_buzon="${2:?falta la dirección tras --buzon}"; shift ;;
    --carpeta)        solo_carpeta="${2:?falta la carpeta tras --carpeta}"; shift ;;
    -*)               echo "Opción desconocida: $1" >&2; exit 1 ;;
    *)                origen="$1" ;;
  esac
  shift
done

# --- el mapa de carpetas (bash 3.2: dos listas paralelas, sin diccionarios) ---
recorta() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; printf '%s' "${s%"${s##*[![:space:]]}"}"; }
cita() { local s="${1//\\/\\\\}"; printf '"%s"' "${s//\"/\\\"}"; }

[ -r "$MAPA" ] || { echo "No encuentro el mapa $MAPA" >&2; exit 1; }
MO=(); MD=(); huecos=""
while IFS= read -r linea || [ -n "$linea" ]; do
  linea="$(recorta "$linea")"
  case "$linea" in ''|\#*) continue ;; esac
  case "$linea" in *=*) ;; *) continue ;; esac
  o="$(recorta "${linea%%=*}")"; d="$(recorta "${linea#*=}")"
  case "$d" in *"<"*) huecos="$huecos «${o}»" ;; esac
  MO+=("$o"); MD+=("$d")
done < "$MAPA"
if [ -n "$huecos" ]; then
  echo "$(basename "$MAPA") tiene huecos sin rellenar:$huecos." >&2
  echo "Rellénalos con lo que da el paso 1:" >&2
  echo "  python3 scripts/verificar-correo.py --servidor imap.forwardemail.net --creds ~/.forwardemail-correo --solo-servidor" >&2
  exit 1
fi
en_mapa() {  # imprime el índice de la carpeta en el mapa, o nada
  local i
  for i in "${!MO[@]}"; do [ "${MO[$i]}" = "$1" ] && { printf '%s' "$i"; return; }; done
}

# --- origen y credenciales ---
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
  [ -z "$solo_buzon" ] || [ "$direccion" = "$solo_buzon" ] || continue

  carpeta="$origen/$direccion"
  if [ ! -d "$carpeta" ]; then
    echo "=== $direccion ==="
    echo "  no hay histórico rescatado en $carpeta, lo salto"
    continue
  fi

  canal=$(printf '%s' "$direccion" | tr -c 'a-zA-Z0-9' '-')
  n=$(find "$carpeta" \( -path '*/cur/*' -o -path '*/new/*' \) -type f 2>/dev/null | wc -l | tr -d ' ')

  # Carpetas del rescate, con '/' como separador: INBOX, INBOX/federico…
  LOCALES=()
  while IFS= read -r c; do
    d="${c%/cur}"; nombre="${d#"$carpeta"/}"
    LOCALES+=("$nombre")
  done < <(find "$carpeta" -type d -name cur | sort)

  cat > "$CONF" <<EOF
IMAPAccount $canal
Host $SERVIDOR
Port 993
User $direccion
Pass $(cita "$clave")
TLSType IMAPS
AuthMechs PLAIN
PipelineDepth 1

IMAPStore $canal-forwardemail
Account $canal

MaildirStore $canal-local
Path $carpeta/
Inbox $carpeta/INBOX
SubFolders Verbatim
EOF

  canales=(); resto=(); objetivo=""; aviso=""
  for nombre in "${LOCALES[@]}"; do
    i="$(en_mapa "$nombre")"
    if [ -z "$i" ]; then
      resto+=("$nombre")
      [ "$solo_carpeta" = "$nombre" ] && objetivo="$canal-resto:$nombre"
      continue
    fi
    if [ -z "${MD[$i]}" ]; then
      [ "$solo_carpeta" = "$nombre" ] && aviso="«${nombre}» no se sube (mapa-carpetas.txt)"
      continue
    fi
    cat >> "$CONF" <<EOF

Channel $canal-m$i
Far :$canal-forwardemail:$(cita "${MD[$i]}")
Near :$canal-local:$(cita "$nombre")
Create Far
Expunge None
Sync Push
CopyArrivalDate yes
EOF
    canales+=("$canal-m$i")
    [ "$solo_carpeta" = "$nombre" ] && objetivo="$canal-m$i"
  done

  if [ ${#resto[@]} -gt 0 ]; then
    patrones=""
    for nombre in "${resto[@]}"; do patrones="$patrones $(cita "$nombre")"; done
    cat >> "$CONF" <<EOF

Channel $canal-resto
Far :$canal-forwardemail:
Near :$canal-local:
Patterns$patrones
Create Far
Expunge None
Sync Push
CopyArrivalDate yes
EOF
    canales+=("$canal-resto")
  fi

  printf '\nGroup %s-todo\n' "$canal" >> "$CONF"
  for c in "${canales[@]}"; do printf 'Channel %s\n' "$c" >> "$CONF"; done
  chmod 600 "$CONF"

  echo "=== $direccion ($n mensajes locales) ==="

  if [ "$modo" = "config" ]; then
    sed -E 's/^Pass .*/Pass ********/' "$CONF" | sed 's/^/  /'
    echo
    continue
  fi

  if [ -n "$solo_carpeta" ]; then
    if [ -n "$aviso" ]; then echo "  $aviso"; echo; continue; fi
    if [ -z "$objetivo" ]; then echo "  «${solo_carpeta}» no está en el rescate de este buzón"; echo; continue; fi
  else
    objetivo="$canal-todo"
  fi

  opciones=()
  [ "$modo" = "probar" ] && opciones=(--dry-run)
  if mbsync -c "$CONF" "${opciones[@]+"${opciones[@]}"}" "$objetivo" 2>&1 | sed 's/^/  /'; [ "${PIPESTATUS[0]}" -eq 0 ]; then
    if [ "$modo" = "probar" ]; then echo "  simulado: no se ha subido nada"; else echo "  subido"; fi
    subidas=$((subidas + 1))
  else
    echo "  FALLÓ. Revisa la contraseña del alias o el mensaje de mbsync de arriba." >&2
    fallos=$((fallos + 1))
  fi
  echo
done < "$CREDS"

[ "$modo" = "config" ] && exit 0
echo "════════════════════════════════════════════"
echo "  buzones: $subidas correctos   fallos: $fallos"
echo "════════════════════════════════════════════"
echo
echo "Coteja la subida por Message-ID antes de dar nada por hecho:"
echo "  python3 scripts/verificar-correo.py --servidor imap.forwardemail.net \\"
echo "      --creds ~/.forwardemail-correo --mapa scripts/mapa-carpetas.txt"
[ "$fallos" -eq 0 ] || exit 1
