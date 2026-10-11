"""Piezas de correo que comparten verificar-correo.py y extraer-facturas.py.

Credenciales, nombres de carpeta IMAP, apertura de solo lectura, Message-ID
y el mapa de carpetas que también lee subir-correo.sh.
"""
import base64, imaplib, re, sys
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser
from email.policy import compat32
from pathlib import Path

LISTA = re.compile(rb'\((?P<flags>[^)]*)\) (?P<sep>"[^"]*"|NIL) (?P<nombre>.+)')

# Los flags SPECIAL-USE (RFC 6154): dicen qué carpeta es la de enviados,
# borradores… aunque cada servidor la llame a su manera.
ESPECIALES = ("\\Sent", "\\Drafts", "\\Trash", "\\Junk", "\\Archive", "\\All", "\\Flagged")


def leer_creds(ruta: Path) -> list[tuple[str, str]]:
    if not ruta.is_file():
        sys.exit(f"No encuentro {ruta}.")
    if ruta.stat().st_mode & 0o777 != 0o600:
        sys.exit(f"AVISO: {ruta} no tiene permisos 600. Corrígelo:  chmod 600 {ruta}")
    cuentas = []
    for linea in ruta.read_text().splitlines():
        if not linea or linea.startswith("#") or ":" not in linea:
            continue
        direccion, clave = linea.split(":", 1)   # la contraseña puede llevar ':'
        cuentas.append((direccion, clave))
    return cuentas


def utf7_imap(nombre: str) -> str:
    """Los nombres de carpeta IMAP no ASCII van en UTF-7 modificado (RFC 3501)."""
    def tramo(m: re.Match) -> str:
        if m.group(1) == "":
            return "&"
        b64 = m.group(1).replace(",", "/")
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", tramo, nombre)


def carpetas(imap: imaplib.IMAP4_SSL) -> list[tuple[str, str, str]]:
    """(nombre en el servidor, separador, flags) de cada carpeta seleccionable."""
    _, filas = imap.list()
    salida = []
    for fila in filas:
        m = LISTA.match(fila if isinstance(fila, bytes) else b"")
        if not m:
            continue
        flags = m["flags"].decode()
        if "\\Noselect" in flags or "\\NonExistent" in flags:
            continue
        nombre = m["nombre"].decode()
        if nombre.startswith('"'):
            nombre = nombre[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        sep = m["sep"].decode().strip('"') if m["sep"] != b"NIL" else ""
        salida.append((nombre, sep, flags))
    return salida


def legible(nombre: str, sep: str) -> str:
    """El nombre tal como lo escribe una persona: UTF-8 y '/' como separador,
    que es también como lo guarda mbsync en el Maildir."""
    n = utf7_imap(nombre)
    return n.replace(sep, "/") if sep and sep != "/" else n


def especiales(flags: str) -> list[str]:
    return [f for f in ESPECIALES if f in flags]


def examinar(imap: imaplib.IMAP4_SSL, nombre: str) -> int:
    """Abre la carpeta en solo lectura (EXAMINE): no marca nada como leído."""
    cita = '"' + nombre.replace("\\", "\\\\").replace('"', '\\"') + '"'
    estado, datos = imap.select(cita, readonly=True)
    if estado != "OK":
        raise imaplib.IMAP4.error(f"no se puede abrir {nombre}")
    return int(datos[0])


def id_mensaje(cabeceras: bytes) -> tuple[str | None, str]:
    """(Message-ID normalizado o None, asunto) a partir de las cabeceras.

    El mismo cálculo para el Maildir y para el servidor, así que un correo
    subido coincide consigo mismo aunque el servidor pliegue las líneas.
    """
    msg = BytesHeaderParser(policy=compat32).parsebytes(cabeceras)
    crudo = msg.get("Message-ID") or msg.get("Message-Id") or ""
    if not crudo:
        # Una cabecera rota (una línea suelta sin «:» en medio de un asunto
        # plegado) hace que el parser deje de leer ahí, y el Message-ID que
        # viene detrás se pierde. Visto en un boletín de Contasimple.
        m = re.search(rb"(?mi)^message-id:[ \t]*(.*(?:\r?\n[ \t].*)*)", cabeceras)
        crudo = m.group(1).decode("latin-1") if m else ""
    mid = re.sub(r"\s+", "", str(crudo)) or None
    asunto = str(msg.get("Subject", "") or "")
    try:
        asunto = str(make_header(decode_header(asunto)))
    except Exception:
        pass   # un asunto mal codificado se enseña tal cual
    return mid, re.sub(r"\s+", " ", asunto).strip()


def cabeceras_de(datos: bytes) -> bytes:
    """Solo la parte de cabeceras de un correo entero."""
    for corte in (b"\r\n\r\n", b"\n\n"):
        i = datos.find(corte)
        if i >= 0:
            return datos[: i + len(corte)]
    return datos


def ids_servidor(imap: imaplib.IMAP4_SSL, total: int, lote: int = 500) -> list[tuple[str | None, str]]:
    """(Message-ID, asunto) de cada correo de la carpeta abierta.

    BODY.PEEK no toca el flag \\Seen: el Outlook del padre no ve cambios.
    """
    salida = []
    for inicio in range(1, total + 1, lote):
        fin = min(inicio + lote - 1, total)
        _, datos = imap.fetch(f"{inicio}:{fin}", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT)])")
        for d in datos:
            if isinstance(d, tuple):
                salida.append(id_mensaje(d[1]))
    return salida


def leer_mapa(ruta: Path) -> dict[str, str]:
    """origen=destino por línea; destino vacío = esa carpeta no se sube.

    Mismo formato que lee subir-correo.sh. Sale si queda algún hueco <…>.
    """
    if not ruta.is_file():
        sys.exit(f"No encuentro el mapa {ruta}.")
    mapa, huecos = {}, []
    for linea in ruta.read_text().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        origen, destino = (t.strip() for t in linea.split("=", 1))
        if "<" in destino:
            huecos.append(origen)
        mapa[origen] = destino
    if huecos:
        sys.exit(f"{ruta.name} tiene huecos sin rellenar: {', '.join(huecos)}.\n"
                 "Rellénalos con los nombres que da el paso 1 (verificar-correo.py --solo-servidor).")
    return mapa
