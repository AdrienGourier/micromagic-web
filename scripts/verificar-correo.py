#!/usr/bin/env python3
"""Comprueba que un rescate de correo está completo, carpeta por carpeta.

Cuenta los mensajes de cada carpeta en el servidor y en el Maildir local que
dejó rescatar-correo.sh. Solo lee: abre las carpetas con EXAMINE, así que no
marca nada como leído ni cambia nada en el buzón.

De paso saca dos fechas que dicen cómo se usa cada buzón:
  - el correo más antiguo de la bandeja de entrada: si es reciente, Outlook
    descarga por POP3 y borra del servidor, y el histórico está en el PC
  - el último enviado: qué direcciones se usan de verdad para escribir

Con --solo-servidor enseña además los flags SPECIAL-USE (\\Sent, \\Drafts…):
así se sabe cómo llama forwardemail a sus carpetas especiales para rellenar
mapa-carpetas.txt.

Con --mapa comprueba una SUBIDA: cada correo de cada carpeta local tiene que
estar en su carpeta de destino del servidor, cotejado por Message-ID. Contar
no basta: el correo nuevo que entra en INBOX taparía los huecos de lo subido.

Mismo fichero de credenciales que rescatar-correo.sh (chmod 600):
  direccion:contraseña

Uso:
  python3 scripts/verificar-correo.py                      el rescate más reciente
  python3 scripts/verificar-correo.py <carpeta>            ese rescate
  python3 scripts/verificar-correo.py --solo-servidor      sin comparar con local
  python3 scripts/verificar-correo.py --servidor imap.forwardemail.net \\
      --creds ~/.forwardemail-correo --solo-servidor       qué hay en forwardemail
  python3 scripts/verificar-correo.py --servidor imap.forwardemail.net \\
      --creds ~/.forwardemail-correo --mapa scripts/mapa-carpetas.txt
                                                           cotejo de la subida
Sale con 1 si falta algo o falla un login.
"""
import argparse, imaplib, sys, time
from pathlib import Path

from correo_imap import (carpetas, cabeceras_de, especiales, examinar, id_mensaje,
                         ids_servidor, leer_creds, leer_mapa, legible, utf7_imap)


def fechas(imap: imaplib.IMAP4_SSL) -> tuple[str, str]:
    """La fecha de llegada más antigua y la más reciente de la carpeta abierta.

    Hay que mirarlas todas: el orden de los mensajes es el de guardado, y un
    buzón importado guarda primero correos más nuevos que algunos que vienen
    detrás.
    """
    _, datos = imap.fetch("1:*", "(INTERNALDATE)")
    tuplas = [imaplib.Internaldate2tuple(d) for d in datos if isinstance(d, bytes)]
    dias = sorted(time.strftime("%Y-%m-%d", t) for t in tuplas if t)
    return (dias[0], dias[-1]) if dias else ("?", "?")


def ficheros(carpeta: Path) -> list[Path]:
    return [f for sub in ("cur", "new") if (carpeta / sub).is_dir()
            for f in (carpeta / sub).iterdir() if f.is_file()]


def locales(carpeta: Path) -> int:
    return len(ficheros(carpeta))


def maildir(base: Path, nombre: str, sep: str) -> Path:
    """Dónde deja mbsync (SubFolders Verbatim) cada carpeta IMAP."""
    for n in (nombre, utf7_imap(nombre)):
        ruta = base.joinpath(*(n.split(sep) if sep else [n]))
        if ruta.is_dir():
            return ruta
    return base.joinpath(*(nombre.split(sep) if sep else [nombre]))


def carpetas_locales(buzon: Path) -> list[tuple[str, Path]]:
    """(nombre con '/', ruta) de cada carpeta Maildir del rescate de un buzón."""
    salida = []
    for d in sorted([buzon, *buzon.rglob("*")]):
        if d.is_dir() and (d / "cur").is_dir():
            salida.append((d.relative_to(buzon).as_posix(), d))
    return salida


def contar(imap, direccion, origen, problemas) -> int:
    """El modo de siempre: cuántos hay en cada carpeta, servidor contra local."""
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
            mas_antiguo = fechas(imap)[0]
        enviados = "\\Sent" in flags or nombre.lower() in ("elementos enviados", "sent")
        if enviados and n_srv:
            ultimo_enviado = fechas(imap)[1]
        total_srv += n_srv

        if origen is None:
            marca = " ".join(especiales(flags))
            print(f"  {utf7_imap(nombre):<28} {n_srv:>6}" + (f"   {marca}" if marca else ""))
            continue
        n_loc = locales(maildir(origen / direccion, nombre, sep))
        total_loc += n_loc
        # Más en local que en el servidor es normal: Expunge None no borra lo
        # que el servidor haya borrado después del rescate.
        veredicto = "OK" if n_loc >= n_srv else f"FALTAN {n_srv - n_loc}"
        if n_loc < n_srv:
            problemas += 1
        print(f"  {utf7_imap(nombre):<28} servidor {n_srv:>6}   local {n_loc:>6}   {veredicto}")

    resumen = f"  total servidor {total_srv}"
    if origen is not None:
        resumen += f"   local {total_loc}"
    print(resumen)
    print(f"  correo más antiguo en la bandeja: {mas_antiguo}")
    print(f"  último enviado:                   {ultimo_enviado}\n")
    return problemas


def cotejar(imap, direccion, origen, mapa, problemas) -> int:
    """La subida: cada correo local tiene que estar en su carpeta de destino."""
    buzon = origen / direccion
    if not buzon.is_dir():
        print(f"  no hay rescate de este buzón en {origen}\n")
        return problemas
    en_servidor = {legible(n, s): n for n, s, _ in carpetas(imap)}

    for nombre_local, ruta in carpetas_locales(buzon):
        destino = mapa.get(nombre_local, nombre_local)
        etiqueta = f"{nombre_local:<22} → {destino or '-':<18}"
        if destino == "":
            print(f"  {nombre_local:<22}   no se sube (mapa)")
            continue

        locales_ids, sin_id_local = {}, 0
        archivos = ficheros(ruta)
        for f in archivos:
            with open(f, "rb") as fh:
                mid, asunto = id_mensaje(cabeceras_de(fh.read(256 * 1024)))
            if mid:
                locales_ids.setdefault(mid, asunto)
            else:
                sin_id_local += 1

        real = en_servidor.get(destino) or next(
            (v for k, v in en_servidor.items() if k.upper() == destino.upper() == "INBOX"), None)
        if real is None:
            print(f"  {etiqueta} NO EXISTE EN EL SERVIDOR ({len(archivos)} correos sin subir)")
            problemas += 1
            continue

        total = examinar(imap, real)
        servidor = ids_servidor(imap, total) if total else []
        ids_srv = {mid for mid, _ in servidor if mid}
        sin_id_srv = sum(1 for mid, _ in servidor if not mid)
        faltan = [mid for mid in locales_ids if mid not in ids_srv]

        # «local» son ficheros: un correo guardado dos veces cuenta dos, pero
        # en el cotejo por Message-ID basta con que esté una.
        linea = f"  {etiqueta} local {len(archivos):>6}   servidor {total:>6}   "
        if faltan:
            problemas += 1
            print(linea + f"FALTAN {len(faltan)}")
            for mid in faltan[:5]:
                print(f"      · {locales_ids[mid][:90] or '(sin asunto)'}")
        else:
            print(linea + "OK")
        # Sin Message-ID no hay forma de emparejar uno a uno: se comparan cuántos.
        if sin_id_local:
            aviso = "" if sin_id_srv >= sin_id_local else "   ← en el servidor hay menos"
            print(f"      {sin_id_local} correo(s) sin Message-ID en local, {sin_id_srv} en el servidor{aviso}")
            if sin_id_srv < sin_id_local:
                problemas += 1
    print()
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rescate", nargs="?", help="carpeta ~/Backups/ionos-correo-<fecha>")
    ap.add_argument("--servidor", default="imap.ionos.es")
    ap.add_argument("--creds", default="~/.ionos-correo")
    ap.add_argument("--solo-servidor", action="store_true")
    ap.add_argument("--mapa", help="mapa-carpetas.txt: coteja la subida por Message-ID")
    args = ap.parse_args()
    if args.mapa and args.solo_servidor:
        sys.exit("--mapa compara con el rescate local: no va con --solo-servidor.")

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
    mapa = leer_mapa(Path(args.mapa).expanduser()) if args.mapa else None

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
        if mapa is not None:
            problemas = cotejar(imap, direccion, origen, mapa, problemas)
        else:
            problemas = contar(imap, direccion, origen, problemas)
        imap.logout()

    print("TODO CUADRA" if problemas == 0 else f"PROBLEMAS: {problemas}")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
