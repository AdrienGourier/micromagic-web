#!/usr/bin/env python3
"""Saca las facturas del correo a una carpeta que se puede pasar tal cual: los
PDF ordenados por buzón y mes, cada correo en .eml (se abre con doble clic en
Outlook) y un índice que se abre en cualquier navegador.

De dónde lee cada buzón:
  - de forwardemail por IMAP, si está en ~/.forwardemail-correo: ahí está el
    histórico subido más todo lo llegado después del corte del 7 de octubre
  - del Maildir que dejó rescatar-correo.sh, si no (o con --solo-local)
Por IMAP solo lee: EXAMINE y BODY.PEEK, así que no marca nada como leído.

Un correo cuenta como factura si el asunto, el remitente (nombre o dirección) o
el nombre de un adjunto hablan de factura, fatura, invoice, recibo o abono, o si
el texto lo dice y además trae un PDF. Mejor que sobre alguno a que falte: el
índice enseña el asunto para descartar a ojo.

Los PDF recibidos que no parecen factura van aparte, en «Otros documentos»
(pedidos, justificantes de pago, ofertas…): así se comprueba a ojo que no se
ha quedado ninguna fuera.

Los que dicen venir de un dominio propio y fallan DMARC son suplantaciones (un
«Su factura de IONOS» con un enlace trampa): se listan en rojo y no se copian.

Se ordena por fecha de LLEGADA al buzón: una factura de septiembre que llegó
el 2 de octubre está en octubre.

Uso:
  python3 scripts/extraer-facturas.py                      los cuatro buzones, todo
  python3 scripts/extraer-facturas.py --desde 2026-07-01   solo desde esa fecha
  python3 scripts/extraer-facturas.py --salida ~/Desktop/Facturas
  python3 scripts/extraer-facturas.py --desde 2026-07-01 --por-mes
      una carpeta por mes, y dentro cada buzón con Recibidas y Enviadas: lo
      que pide la contabilidad trimestral
  python3 scripts/extraer-facturas.py --buzon info@rhinopaint.es   solo ese (repetible)
  python3 scripts/extraer-facturas.py --cotejar ~/Backups/ionos-correo-2026-10-07
      además comprueba, por Message-ID, que cada factura de ese rescate desde
      --desde está en el export. Sale con 1 si falta alguna.
"""
import argparse, csv, email, hashlib, html, imaplib, re, sys, urllib.parse
from datetime import date, datetime, timedelta
from email import policy
from email.utils import parseaddr
from pathlib import Path

from correo_imap import cabeceras_de, carpetas as carpetas_imap, examinar, id_mensaje, leer_creds, legible

BUZONES = ["info@rhinopaint.es", "administracion@micromagic.tv",
           "director@micromagic.tv", "info@micromagic.tv"]
SALTAR = {"spam", "borradores", "drafts", "junk"}
SALTAR_FLAGS = ("\\Junk", "\\Drafts")
CLAVE = re.compile(r"factur|fatura|invoice|recibo|abono|rectificativ", re.I)
ADJUNTO = (".pdf", ".xml", ".xsig")
NOMBRE_MAX = 90
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
# IMAP exige los meses en inglés en SEARCH, sea cual sea el idioma del sistema.
MESES_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ENVIADOS = {"elementos enviados", "enviados", "sent", "sent items", "sent messages", "sent mail"}
OTROS = "Otros documentos"
# Si un correo dice venir de uno de estos dominios y falla DMARC, alguien está
# suplantando a la empresa: el clásico «Su factura de IONOS» con un enlace.
PROPIOS = {"micromagic.tv", "micromagic.es", "rhinopaint.es"}


def seguro(texto: str) -> str:
    """Un nombre que Windows acepte: sin <>:"/\\|?*, sin punto final, corto."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", texto)
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t[:NOMBRE_MAX].rstrip(" .") or "sin nombre"


def unico(ruta: Path) -> Path:
    n = 2
    while ruta.exists():
        ruta = ruta.with_name(f"{ruta.stem} ({n}){ruta.suffix}")
        n += 1
    return ruta


def remitente(cab: str) -> str:
    nombre, direccion = parseaddr(cab)
    return nombre.strip() or direccion.split("@")[-1] or "desconocido"


def lista(cosas: list[str]) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


def texto_plano(msg) -> str:
    trozos = []
    for p in msg.walk():
        if p.get_content_maintype() != "text" or p.get_filename():
            continue
        try:
            t = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if p.get_content_subtype() == "html":
            t = re.sub(r"<[^>]+>", " ", t)
        trozos.append(t)
    return " ".join(trozos)[:20000]


def adjuntos(msg):
    for p in msg.walk():
        if p.get_content_maintype() == "multipart":
            continue
        nombre = p.get_filename() or ""
        tipo = p.get_content_type()
        es_pdf = tipo == "application/pdf" or nombre.lower().endswith(".pdf")
        if not (es_pdf or nombre.lower().endswith(ADJUNTO)):
            continue
        datos = p.get_payload(decode=True)
        if datos:
            yield (nombre or "adjunto.pdf"), datos


def suplantado(msg, de: str) -> bool:
    """Dice venir de un dominio propio pero el servidor que lo recibió vio
    fallar DMARC: no lo mandó la empresa."""
    dominio = parseaddr(de)[1].rpartition("@")[2].lower()
    resultados = " ".join(str(v) for v in msg.get_all("Authentication-Results", []))
    return dominio in PROPIOS and "dmarc=fail" in resultados.lower()


def clasificar(msg, asunto: str, de: str, adj, enviado: bool) -> str | None:
    """'factura', 'otro' (un PDF recibido que no lo parece), 'sospechoso' o None."""
    tipo = _clasificar(msg, asunto, de, adj, enviado)
    if tipo and not enviado and suplantado(msg, de):
        return "sospechoso"
    return tipo


def _clasificar(msg, asunto: str, de: str, adj, enviado: bool) -> str | None:
    nombre, direccion = parseaddr(de)
    quien = f"{nombre} {direccion.split('@')[0]}"
    if (CLAVE.search(asunto) or CLAVE.search(quien) or any(CLAVE.search(n) for n, _ in adj)
            or (adj and CLAVE.search(texto_plano(msg)))):
        return "factura"
    if not enviado and any(n.lower().endswith(".pdf") for n, _ in adj):
        return "otro"
    return None


def identidad(crudo: bytes) -> str:
    """Message-ID, o la huella del correo entero si no lo trae."""
    mid, _ = id_mensaje(cabeceras_de(crudo))
    return mid or "sha256:" + hashlib.sha256(crudo).hexdigest()


# --- de dónde salen los correos -------------------------------------------
# Cada fuente da (llegada, carpeta, enviado, bytes del correo) dentro del periodo.

def carpetas_maildir(buzon: Path):
    """Cada carpeta Maildir del buzón (las que tienen cur/ o new/)."""
    for d in sorted([buzon, *buzon.rglob("*")]):
        if d.is_dir() and ((d / "cur").is_dir() or (d / "new").is_dir()):
            if d.name.lower() not in SALTAR:
                yield d


def desde_maildir(buzon: Path, desde, hasta):
    for carpeta in carpetas_maildir(buzon):
        nombre = carpeta.relative_to(buzon).as_posix() if carpeta != buzon else "INBOX"
        enviado = nombre.lower() in ENVIADOS
        for f in [*carpeta.glob("cur/*"), *carpeta.glob("new/*")]:
            # La fecha del fichero es la de llegada al buzón (CopyArrivalDate).
            llegada = datetime.fromtimestamp(f.stat().st_mtime)
            if (desde and llegada.date() < desde) or (hasta and llegada.date() > hasta):
                continue
            yield llegada, nombre, enviado, f.read_bytes()


def fecha_imap(d: date) -> str:
    return f"{d.day:02d}-{MESES_IMAP[d.month - 1]}-{d.year}"


def desde_imap(servidor: str, direccion: str, clave: str, desde, hasta):
    imap = imaplib.IMAP4_SSL(servidor, 993, timeout=120)
    imap.login(direccion, clave)
    try:
        for nombre, sep, flags in carpetas_imap(imap):
            visible = legible(nombre, sep)
            if visible.lower() in SALTAR or any(f in flags for f in SALTAR_FLAGS):
                continue
            enviado = "\\Sent" in flags or visible.lower() in ENVIADOS
            if not examinar(imap, nombre):
                continue
            # SINCE/BEFORE filtran por INTERNALDATE, la fecha de llegada: la misma
            # que la del fichero en el Maildir.
            criterio = []
            if desde:
                criterio += ["SINCE", fecha_imap(desde)]
            if hasta:
                criterio += ["BEFORE", fecha_imap(hasta + timedelta(days=1))]
            _, datos = imap.uid("SEARCH", *(criterio or ["ALL"]))
            uids = datos[0].split()
            for i in range(0, len(uids), 25):
                _, datos = imap.uid("FETCH", b",".join(uids[i:i + 25]), "(INTERNALDATE BODY.PEEK[])")
                for d in datos:
                    if not isinstance(d, tuple):
                        continue
                    t = imaplib.Internaldate2tuple(d[0])
                    if t:
                        yield datetime(*t[:6]), visible, enviado, d[1]
    finally:
        imap.logout()


def enlace(desde: Path, a: Path) -> str:
    return "/".join(urllib.parse.quote(p) for p in a.relative_to(desde).parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescate", help="carpeta ~/Backups/ionos-correo-<fecha>")
    ap.add_argument("--salida", default="~/Desktop/Facturas-correo")
    ap.add_argument("--desde", help="AAAA-MM-DD")
    ap.add_argument("--hasta", help="AAAA-MM-DD, incluido")
    ap.add_argument("--por-mes", action="store_true",
                    help="carpeta por mes primero, con Recibidas/Enviadas por buzón")
    ap.add_argument("--buzon", action="append", help="solo ese buzón (se puede repetir)")
    ap.add_argument("--servidor", default="imap.forwardemail.net")
    ap.add_argument("--creds", default="~/.forwardemail-correo",
                    help="los buzones que estén aquí se leen por IMAP")
    ap.add_argument("--solo-local", action="store_true", help="leerlo todo del rescate local")
    ap.add_argument("--cotejar", metavar="RESCATE",
                    help="comprobar que cada factura de ese rescate está en el export")
    args = ap.parse_args()

    buzones = [b for b in BUZONES if not args.buzon or b in args.buzon]
    if args.buzon and (otros := set(args.buzon) - set(BUZONES)):
        sys.exit(f"Buzón desconocido: {', '.join(otros)}. Son: {', '.join(BUZONES)}")

    ruta_creds = Path(args.creds).expanduser()
    claves = {} if args.solo_local or not ruta_creds.exists() else dict(leer_creds(ruta_creds))
    por_imap = [b for b in buzones if b in claves]

    origen = None
    if args.rescate:
        origen = Path(args.rescate).expanduser()
    else:
        hechos = sorted(d for d in Path.home().joinpath("Backups").glob("ionos-correo-*") if d.is_dir())
        origen = hechos[-1] if hechos else None
    if len(por_imap) < len(buzones) and (not origen or not origen.is_dir()):
        sys.exit("No encuentro el rescate. Ejecuta antes ./scripts/rescatar-correo.sh")

    desde = date.fromisoformat(args.desde) if args.desde else None
    hasta = date.fromisoformat(args.hasta) if args.hasta else None
    salida = Path(args.salida).expanduser()
    if salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} ya existe y no está vacía: bórrala o elige otra con --salida")
    salida.mkdir(parents=True, exist_ok=True)

    filas, fuentes = [], {}
    for direccion in buzones:
        if direccion in por_imap:
            fuentes[direccion] = f"forwardemail ({args.servidor})"
            correos = desde_imap(args.servidor, direccion, claves[direccion], desde, hasta)
        else:
            buzon = origen / direccion
            if not buzon.is_dir():
                print(f"{direccion}: no está en el rescate {origen.name}, lo salto")
                continue
            fuentes[direccion] = f"rescate {origen.name}"
            correos = desde_maildir(buzon, desde, hasta)
        # El mismo PDF reenviado varias veces se guarda una vez por carpeta: así
        # cada carpeta de mes se basta sola.
        vistos: dict[tuple[str, Path], Path] = {}
        revisados = 0
        try:
            for llegada, nombre_carpeta, enviado, crudo in correos:
                revisados += 1
                try:
                    msg = email.message_from_bytes(crudo, policy=policy.default)
                    asunto = str(msg.get("Subject", "") or "")
                    de = str(msg.get("From", "") or "")
                    adj = list(adjuntos(msg))
                    tipo = clasificar(msg, asunto, de, adj, enviado)
                except Exception:
                    continue
                if tipo is None:
                    continue
                if tipo == "sospechoso":
                    # Ni el .eml ni los adjuntos: el enlace es la trampa.
                    filas.append(dict(tipo=tipo, llegada=llegada, buzon=direccion, carpeta=nombre_carpeta,
                                      de=de, asunto=asunto, eml=None, adjuntos=[], id=identidad(crudo)))
                    continue

                dia = llegada.strftime("%Y-%m-%d")
                if args.por_mes:
                    lado = "Enviadas" if enviado else "Recibidas"
                    mes = f"{llegada:%Y-%m} {MESES[llegada.month - 1]}"
                    destino = salida / mes / direccion / (lado if tipo == "factura" else OTROS)
                else:
                    destino = salida / direccion / llegada.strftime("%Y-%m")
                    if tipo == "otro":
                        destino = destino / OTROS
                destino.mkdir(parents=True, exist_ok=True)
                prefijo = seguro(f"{dia} {remitente(de)}")
                eml = unico(destino / f"{seguro(f'{prefijo} - {asunto or 'sin asunto'}')}.eml")
                eml.write_bytes(crudo)

                ficheros = []
                for nombre, datos in adj:
                    if tipo == "otro" and not nombre.lower().endswith(".pdf"):
                        continue
                    h = (hashlib.sha256(datos).hexdigest(), destino)
                    if h not in vistos:
                        stem, ext = Path(nombre).stem, Path(nombre).suffix.lower() or ".pdf"
                        ruta = unico(destino / f"{seguro(f'{prefijo} - {stem}')}{ext}")
                        ruta.write_bytes(datos)
                        vistos[h] = ruta
                    ficheros.append(vistos[h])
                filas.append(dict(tipo=tipo, llegada=llegada, buzon=direccion, carpeta=nombre_carpeta,
                                  de=de, asunto=asunto, eml=eml, adjuntos=ficheros, id=identidad(crudo)))
        except (imaplib.IMAP4.error, OSError) as e:
            print(f"{direccion}: FALLO leyendo de {fuentes[direccion]}: {e}")
            return 1
        n = sum(1 for r in filas if r["buzon"] == direccion and r["tipo"] == "factura")
        o = sum(1 for r in filas if r["buzon"] == direccion and r["tipo"] == "otro")
        x = sum(1 for r in filas if r["buzon"] == direccion and r["tipo"] == "sospechoso")
        print(f"{direccion} ({fuentes[direccion]}): {revisados} correos en el periodo, "
              f"{n} con factura, {o} otros documentos, {len(vistos)} adjuntos"
              + (f", {x} SOSPECHOSOS (suplantación, no copiados)" if x else ""))

    filas.sort(key=lambda r: r["llegada"], reverse=True)
    escribir_csv(salida, filas)
    escribir_indice(salida, filas, fuentes)
    n = sum(1 for r in filas if r["tipo"] == "factura")
    o = sum(1 for r in filas if r["tipo"] == "otro")
    print(f"\n{n} correos con factura y {o} otros documentos en {salida}")
    print(f"Índice: file://{urllib.parse.quote(str(salida / 'index.html'))}")

    if args.cotejar:
        servidor = {b: (args.servidor, claves[b]) for b in por_imap}
        return cotejar(Path(args.cotejar).expanduser(), filas, list(fuentes), desde, hasta, servidor)
    return 0


def buscar_en_servidor(servidor: str, direccion: str, clave: str, ids: list[str]) -> dict[str, str]:
    """Dónde está cada Message-ID en el servidor, en cualquier carpeta y fecha."""
    encontrados = {}
    imap = imaplib.IMAP4_SSL(servidor, 993, timeout=120)
    imap.login(direccion, clave)
    try:
        for nombre, sep, flags in carpetas_imap(imap):
            if not examinar(imap, nombre):
                continue
            for mid in ids:
                if mid in encontrados or mid.startswith("sha256:"):
                    continue
                _, d = imap.search(None, "HEADER", "Message-ID", '"' + mid.strip("<>").replace('"', "") + '"')
                numeros = d[0].split()
                if numeros:
                    _, f = imap.fetch(numeros[0], "(INTERNALDATE)")
                    t = imaplib.Internaldate2tuple(f[0])
                    cuando = f", llegada {t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year}" if t else ""
                    encontrados[mid] = f"{legible(nombre, sep)}{cuando}"
    finally:
        imap.logout()
    return encontrados


def cotejar(rescate: Path, filas, buzones: list[str], desde, hasta, servidor: dict) -> int:
    """Cada factura del rescate local tiene que estar en el export, por Message-ID.

    Sirve para fiarse de un export leído de forwardemail: si la subida o el
    servidor perdieron algo, aquí sale.

    Que no esté en el export no siempre es una pérdida. Si el correo se movió o
    se volvió a guardar, el servidor le pone otra fecha de llegada (puede caer
    fuera del periodo) u otra carpeta (Spam no se exporta). Por eso lo que falta
    se busca en el servidor, y solo cuenta como fallo lo que ya no está en él.
    """
    if not rescate.is_dir():
        sys.exit(f"No encuentro el rescate {rescate} para cotejar.")
    exportadas = {r["id"] for r in filas if r["tipo"] == "factura"}
    print(f"\nCotejo con {rescate.name}:")
    perdidas_total = avisos_total = 0
    for direccion in buzones:
        buzon = rescate / direccion
        if not buzon.is_dir():
            continue
        esperadas, faltan = 0, []
        for llegada, carpeta, enviado, crudo in desde_maildir(buzon, desde, hasta):
            try:
                msg = email.message_from_bytes(crudo, policy=policy.default)
                asunto = str(msg.get("Subject", "") or "")
                tipo = clasificar(msg, asunto, str(msg.get("From", "") or ""), list(adjuntos(msg)), enviado)
            except Exception:
                continue
            if tipo != "factura":
                continue
            esperadas += 1
            mid = identidad(crudo)
            if mid not in exportadas:
                faltan.append((llegada, carpeta, asunto, mid))
        # Lo que falta y se leyó de un servidor: ¿sigue ahí, en otra fecha o carpeta?
        donde = {}
        if faltan and direccion in servidor:
            srv, clave = servidor[direccion]
            donde = buscar_en_servidor(srv, direccion, clave, [f[3] for f in faltan])
        perdidas = [f for f in faltan if f[3] not in donde]
        print(f"  {direccion:<30} {esperadas:>4} facturas en el rescate   "
              + ("todas en el export" if not faltan else
                 f"{len(faltan)} fuera del export, {len(perdidas)} ya no están en el servidor"))
        for llegada, carpeta, asunto, mid in sorted(faltan)[:15]:
            motivo = f"en el servidor: {donde[mid]}" if mid in donde else (
                "NO ESTÁ EN EL SERVIDOR" if direccion in servidor else "no está en el export")
            print(f"      · {llegada:%d/%m/%Y} [{carpeta}] {asunto[:60] or '(sin asunto)'} — {motivo}")
        perdidas_total += len(perdidas)
        avisos_total += len(faltan) - len(perdidas)
    if perdidas_total:
        print(f"COTEJO: {perdidas_total} factura(s) del rescate ya no están en el servidor")
    else:
        print("COTEJO OK" + (f" ({avisos_total} siguen en el servidor con otra fecha o carpeta: revísalas)"
                             if avisos_total else ""))
    return 1 if perdidas_total else 0


def escribir_csv(salida: Path, filas) -> None:
    # Punto y coma y BOM: así lo abre bien un Excel en español.
    with open(salida / "facturas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Tipo", "Fecha", "Buzón", "Carpeta", "De", "Asunto", "Adjuntos", "Correo"])
        for r in filas:
            w.writerow([{"factura": "Factura", "otro": "Otro documento", "sospechoso": "SOSPECHOSO"}[r["tipo"]],
                        r["llegada"].strftime("%Y-%m-%d %H:%M"), r["buzon"], r["carpeta"], r["de"],
                        r["asunto"], " | ".join(a.relative_to(salida).as_posix() for a in r["adjuntos"]),
                        r["eml"].relative_to(salida).as_posix() if r["eml"] else "(no copiado)"])


def fila_html(salida: Path, r, clase: str = "") -> str:
    e = html.escape
    adj = " ".join(f'<a href="{enlace(salida, a)}">{e(a.suffix[1:].upper())}</a>' for a in r["adjuntos"])
    atributo = f' class="{clase}"' if clase else ""
    texto = e(r["asunto"] or "(sin asunto)")
    asunto = f'<a href="{enlace(salida, r["eml"])}">{texto}</a>' if r["eml"] else texto
    return (
        f'<tr{atributo}><td class="f">{r["llegada"]:%d/%m/%Y}</td>'
        f'<td>{e(r["buzon"].split("@")[0])}<br><small>{e(r["buzon"].split("@")[1])}'
        f'{"" if r["carpeta"] == "INBOX" else " · " + e(r["carpeta"])}</small></td>'
        f'<td>{e(remitente(r["de"]))}</td><td>{asunto}</td>'
        f'<td class="a">{adj or "—"}</td></tr>')


def escribir_indice(salida: Path, filas, fuentes: dict[str, str]) -> None:
    e = html.escape
    meses = sorted({(r["llegada"].year, r["llegada"].month) for r in filas}, reverse=True)
    cuerpo = []
    for mes in meses:
        del_mes = [r for r in filas if (r["llegada"].year, r["llegada"].month) == mes]
        facturas = [r for r in del_mes if r["tipo"] == "factura"]
        otros = [r for r in del_mes if r["tipo"] == "otro"]
        falsos = [r for r in del_mes if r["tipo"] == "sospechoso"]
        cuerpo.append(f'<tr class="mes"><th colspan="5">{MESES[mes[1] - 1]} {mes[0]}'
                      f' <small>· {len(facturas)} con factura'
                      f'{f" · {len(otros)} otros documentos" if otros else ""}</small></th></tr>')
        cuerpo += [fila_html(salida, r) for r in facturas]
        if otros:
            cuerpo.append(f'<tr class="sub"><th colspan="5">Otros documentos recibidos · {len(otros)}'
                          ' <small>— PDF que no parecen factura. Echa un vistazo por si alguno lo es.</small></th></tr>')
            cuerpo += [fila_html(salida, r, "otro") for r in otros]
        if falsos:
            cuerpo.append(f'<tr class="peligro"><th colspan="5">Correos falsos · {len(falsos)}'
                          ' <small>— dicen venir de vuestra propia dirección pero no los mandó la empresa.'
                          ' No se han copiado. Si te llega uno igual, no abras sus enlaces.</small></th></tr>')
            cuerpo += [fila_html(salida, r, "falso") for r in falsos]

    n = sum(1 for r in filas if r["tipo"] == "factura")
    de_imap = [b for b, f in fuentes.items() if f.startswith("forwardemail")]
    de_local = [b for b, f in fuentes.items() if not f.startswith("forwardemail")]
    procedencia = []
    if de_imap:
        procedencia.append(f"{lista(de_imap)}: leído de forwardemail, con todo lo llegado hasta hoy")
    if de_local:
        procedencia.append(f"{lista(de_local)}: del {fuentes[de_local[0]]}. Lo llegado después del corte "
                           "(7 de octubre) no está aquí; tiene copia en la Hotmail")
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Facturas del correo</title>
<style>
  body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;color:#111;background:#fff}}
  .env{{max-width:72rem;margin:auto;padding:2rem 1rem 4rem}}
  h1{{margin:0 0 .3rem;font-size:1.8rem}}
  p{{color:#555;margin:.2rem 0 1rem;max-width:64ch}}
  .aviso{{border-left:4px solid #b4541f;padding:.4rem .8rem;color:#333;background:#fbf4ee}}
  input{{font:inherit;font-size:1.05rem;padding:.6rem .8rem;width:100%;max-width:30rem;
         border:2px solid #111;margin:.5rem 0 1rem}}
  table{{border-collapse:collapse;width:100%;font-size:.95rem}}
  th,td{{border-bottom:1px solid #ddd;padding:.5rem .6rem;text-align:left;vertical-align:top}}
  th{{background:#f3f3f1;position:sticky;top:0}}
  tr.mes th{{background:#111;color:#fff;font-size:1.05rem;position:static;padding:.7rem .6rem}}
  tr.mes small{{color:#bbb;font-weight:400}}
  tr.sub th{{background:#ecebe6;position:static;font-size:.95rem}}
  tr.otro td{{color:#555}}
  tr.peligro th{{background:#b3261e;color:#fff;position:static}}
  tr.peligro small{{color:#fde}}
  tr.falso td{{color:#b3261e;text-decoration:line-through}}
  td.f{{white-space:nowrap;font-variant-numeric:tabular-nums}}
  td.a a{{display:inline-block;background:#111;color:#fff;text-decoration:none;
         padding:.15rem .5rem;margin:0 .2rem .2rem 0;font-size:.8rem;font-weight:700}}
  small{{color:#777}}
  a{{color:#0b57a4}}
</style></head><body><div class="env">
<h1>Facturas del correo</h1>
<p>{n} correos con factura de <b>{e(lista(list(fuentes)))}</b>, del más nuevo al más antiguo.
Pulsa <b>PDF</b> para abrir la factura, o el asunto para abrir el correo entero.</p>
<p class="aviso">Ordenado por el día en que el correo <b>llegó</b>, no por la fecha de la factura:
una factura de septiembre que llegó el 2 de octubre está en octubre. Para cerrar un
trimestre, mira también los primeros días del mes siguiente.</p>
<p><small>{"<br>".join(e(p) for p in procedencia)}.<br>Sacado el {datetime.now():%d/%m/%Y}.</small></p>
<input id="q" type="search" placeholder="Buscar proveedor, asunto o fecha…" autofocus>
<table><thead><tr><th>Llegó</th><th>Buzón</th><th>De</th><th>Asunto</th><th>Factura</th></tr></thead>
<tbody>
{chr(10).join(cuerpo)}
</tbody></table></div>
<script>
  var q = document.getElementById('q'), filas = document.querySelectorAll('tbody tr:not(.mes):not(.sub):not(.peligro)');
  q.addEventListener('input', function () {{
    var t = q.value.toLowerCase();
    filas.forEach(function (f) {{ f.style.display = f.textContent.toLowerCase().indexOf(t) < 0 ? 'none' : ''; }});
  }});
</script></body></html>
""", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
