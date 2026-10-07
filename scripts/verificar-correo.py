#!/usr/bin/env python3
"""Comprueba que un rescate de correo está completo, carpeta por carpeta.

Cuenta los mensajes de cada carpeta en el servidor y en el Maildir local que
dejó rescatar-correo.sh. Solo lee: abre las carpetas con EXAMINE, así que no
marca nada como leído ni cambia nada en el buzón.

De paso saca dos fechas que dicen cómo se usa cada buzón:
  - el correo más antiguo de la bandeja de entrada: si es reciente, Outlook
    descarga por POP3 y borra del servidor, y el histórico está en el PC
  - el último enviado: qué direcciones se usan de verdad para escribir

Mismo fichero de credenciales que rescatar-correo.sh (chmod 600):
  direccion:contraseña

Uso:
  python3 scripts/verificar-correo.py                      el rescate más reciente
  python3 scripts/verificar-correo.py <carpeta>            ese rescate
  python3 scripts/verificar-correo.py --solo-servidor      sin comparar con local
  python3 scripts/verificar-correo.py --servidor imap.forwardemail.net \\
      --creds ~/.forwardemail-correo --solo-servidor       lo subido a forwardemail
Sale con 1 si falta algo o falla un login.
"""
import argparse, base64, imaplib, re, sys, time
from pathlib import Path

LISTA = re.compile(rb'\((?P<flags>[^)]*)\) (?P<sep>"[^"]*"|NIL) (?P<nombre>.+)')


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


def examinar(imap: imaplib.IMAP4_SSL, nombre: str) -> int:
    cita = '"' + nombre.replace("\\", "\\\\").replace('"', '\\"') + '"'
    estado, datos = imap.select(cita, readonly=True)
    if estado != "OK":
        raise imaplib.IMAP4.error(f"no se puede abrir {nombre}")
    return int(datos[0])


def fecha(imap: imaplib.IMAP4_SSL, cual: str) -> str:
    """INTERNALDATE del mensaje '1' (el más antiguo) o '*' (el último)."""
    _, datos = imap.fetch(cual, "(INTERNALDATE)")
    t = imaplib.Internaldate2tuple(datos[0]) if datos and datos[0] else None
    return time.strftime("%Y-%m-%d", t) if t else "?"


def locales(carpeta: Path) -> int:
    return sum(1 for sub in ("cur", "new") if (carpeta / sub).is_dir()
               for f in (carpeta / sub).iterdir() if f.is_file())


def maildir(base: Path, nombre: str, sep: str) -> Path:
    """Dónde deja mbsync (SubFolders Verbatim) cada carpeta IMAP."""
    for n in (nombre, utf7_imap(nombre)):
        ruta = base.joinpath(*(n.split(sep) if sep else [n]))
        if ruta.is_dir():
            return ruta
    return base.joinpath(*(nombre.split(sep) if sep else [nombre]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rescate", nargs="?", help="carpeta ~/Backups/ionos-correo-<fecha>")
    ap.add_argument("--servidor", default="imap.ionos.es")
    ap.add_argument("--creds", default="~/.ionos-correo")
    ap.add_argument("--solo-servidor", action="store_true")
    args = ap.parse_args()

    origen = None
    if not args.solo_servidor:
        if args.rescate:
            origen = Path(args.rescate).expanduser()
        else:
            hechos = sorted(Path.home().joinpath("Backups").glob("ionos-correo-*"))
            origen = hechos[-1] if hechos else None
        if not origen or not origen.is_dir():
            sys.exit("No encuentro el rescate. Ejecuta antes ./scripts/rescatar-correo.sh")
        print(f"rescate: {origen}\n")

    problemas = 0
    for direccion, clave in leer_creds(Path(args.creds).expanduser()):
        print(f"=== {direccion} ===")
        try:
            imap = imaplib.IMAP4_SSL(args.servidor, 993, timeout=60)
            imap.login(direccion, clave)
        except (imaplib.IMAP4.error, OSError) as e:
            print(f"  LOGIN FALLIDO: {e}\n")
            problemas += 1
            continue

        mas_antiguo = ultimo_enviado = "-"
        total_srv = total_loc = 0
        for nombre, sep, flags in carpetas(imap):
            try:
                n_srv = examinar(imap, nombre)
            except imaplib.IMAP4.error as e:
                print(f"  {utf7_imap(nombre):<28} ERROR: {e}")
                problemas += 1
                continue
            if nombre.upper() == "INBOX" and n_srv:
                mas_antiguo = fecha(imap, "1")
            enviados = "\\Sent" in flags or nombre.lower() in ("elementos enviados", "sent")
            if enviados and n_srv:
                ultimo_enviado = fecha(imap, "*")
            total_srv += n_srv

            if origen is None:
                print(f"  {utf7_imap(nombre):<28} {n_srv:>6}")
                continue
            n_loc = locales(maildir(origen / direccion, nombre, sep))
            total_loc += n_loc
            # Más en local que en el servidor es normal: Expunge None no borra lo
            # que el servidor haya borrado después del rescate.
            veredicto = "OK" if n_loc >= n_srv else f"FALTAN {n_srv - n_loc}"
            if n_loc < n_srv:
                problemas += 1
            print(f"  {utf7_imap(nombre):<28} servidor {n_srv:>6}   local {n_loc:>6}   {veredicto}")
        imap.logout()

        resumen = f"  total servidor {total_srv}"
        if origen is not None:
            resumen += f"   local {total_loc}"
        print(resumen)
        print(f"  correo más antiguo en la bandeja: {mas_antiguo}")
        print(f"  último enviado:                   {ultimo_enviado}\n")

    print("TODO CUADRA" if problemas == 0 else f"PROBLEMAS: {problemas}")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
