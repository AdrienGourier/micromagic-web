#!/usr/bin/env python3
"""Saca las facturas del correo rescatado de IONOS a una carpeta que se puede
pasar tal cual: los PDF ordenados por buzón y mes, cada correo en .eml (se abre
con doble clic en Outlook) y un índice que se abre en cualquier navegador.

Lee el Maildir que dejó rescatar-correo.sh. Un correo cuenta como factura si
el asunto o el nombre de un adjunto hablan de factura, invoice, recibo o abono,
o si el texto lo dice y además trae un PDF. Mejor que sobre alguno a que falte:
el índice enseña el asunto para descartar a ojo.

Uso:
  python3 scripts/extraer-facturas.py                      los dos buzones de facturas
  python3 scripts/extraer-facturas.py --desde 2026-07-01   solo desde esa fecha
  python3 scripts/extraer-facturas.py --salida ~/Desktop/Facturas
  python3 scripts/extraer-facturas.py --desde 2026-04-01 --por-mes
      una carpeta por mes, y dentro cada buzón con Recibidas y Enviadas: lo
      que pide la contabilidad trimestral
"""
import argparse, csv, email, hashlib, html, re, sys, urllib.parse
from datetime import date, datetime
from email import policy
from email.utils import parseaddr
from pathlib import Path

BUZONES = ["info@rhinopaint.es", "administracion@micromagic.tv"]
SALTAR = {"spam", "borradores", "drafts", "junk"}
CLAVE = re.compile(r"factur|invoice|recibo|abono|rectificativ", re.I)
ADJUNTO = (".pdf", ".xml", ".xsig")
NOMBRE_MAX = 90
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
ENVIADOS = {"elementos enviados", "enviados", "sent", "sent items", "sent messages"}


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


def carpetas(buzon: Path):
    """Cada carpeta Maildir del buzón (las que tienen cur/ o new/)."""
    for d in sorted([buzon, *buzon.rglob("*")]):
        if d.is_dir() and ((d / "cur").is_dir() or (d / "new").is_dir()):
            if d.name.lower() not in SALTAR:
                yield d


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
    args = ap.parse_args()

    if args.rescate:
        origen = Path(args.rescate).expanduser()
    else:
        hechos = sorted(d for d in Path.home().joinpath("Backups").glob("ionos-correo-*") if d.is_dir())
        origen = hechos[-1] if hechos else None
    if not origen or not origen.is_dir():
        sys.exit("No encuentro el rescate. Ejecuta antes ./scripts/rescatar-correo.sh")
    desde = date.fromisoformat(args.desde) if args.desde else None
    hasta = date.fromisoformat(args.hasta) if args.hasta else None
    salida = Path(args.salida).expanduser()
    if salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} ya existe y no está vacía: bórrala o elige otra con --salida")
    salida.mkdir(parents=True, exist_ok=True)

    filas = []
    for direccion in BUZONES:
        buzon = origen / direccion
        # El mismo PDF reenviado varias veces se guarda una vez por carpeta: así
        # cada carpeta de mes se basta sola.
        vistos: dict[tuple[str, Path], Path] = {}
        revisados = 0
        for carpeta in carpetas(buzon):
            nombre_carpeta = carpeta.relative_to(buzon).as_posix() if carpeta != buzon else "INBOX"
            for f in [*carpeta.glob("cur/*"), *carpeta.glob("new/*")]:
                revisados += 1
                # La fecha del fichero es la de llegada al buzón (CopyArrivalDate).
                llegada = datetime.fromtimestamp(f.stat().st_mtime)
                if (desde and llegada.date() < desde) or (hasta and llegada.date() > hasta):
                    continue
                try:
                    msg = email.message_from_bytes(f.read_bytes(), policy=policy.default)
                    asunto = str(msg.get("Subject", "") or "")
                    de = str(msg.get("From", "") or "")
                    adj = list(adjuntos(msg))
                except Exception:
                    continue
                en_cabecera = CLAVE.search(asunto) or any(CLAVE.search(n) for n, _ in adj)
                if not en_cabecera and not (adj and CLAVE.search(texto_plano(msg))):
                    continue

                dia = llegada.strftime("%Y-%m-%d")
                if args.por_mes:
                    lado = "Enviadas" if nombre_carpeta.lower() in ENVIADOS else "Recibidas"
                    mes = f"{llegada:%Y-%m} {MESES[llegada.month - 1]}"
                    destino = salida / mes / direccion / lado
                else:
                    destino = salida / direccion / llegada.strftime("%Y-%m")
                destino.mkdir(parents=True, exist_ok=True)
                prefijo = seguro(f"{dia} {remitente(de)}")
                eml = unico(destino / f"{seguro(f'{prefijo} - {asunto or 'sin asunto'}')}.eml")
                eml.write_bytes(f.read_bytes())

                ficheros = []
                for nombre, datos in adj:
                    h = (hashlib.sha256(datos).hexdigest(), destino)
                    if h not in vistos:
                        stem, ext = Path(nombre).stem, Path(nombre).suffix.lower() or ".pdf"
                        ruta = unico(destino / f"{seguro(f'{prefijo} - {stem}')}{ext}")
                        ruta.write_bytes(datos)
                        vistos[h] = ruta
                    ficheros.append(vistos[h])
                filas.append(dict(llegada=llegada, buzon=direccion, carpeta=nombre_carpeta,
                                  de=de, asunto=asunto, eml=eml, adjuntos=ficheros))
        n = sum(1 for r in filas if r["buzon"] == direccion)
        print(f"{direccion}: {revisados} correos revisados, {n} con factura, {len(vistos)} adjuntos")

    filas.sort(key=lambda r: r["llegada"], reverse=True)
    escribir_csv(salida, filas)
    escribir_indice(salida, filas, origen)
    print(f"\n{len(filas)} correos con factura en {salida}")
    print(f"Índice: file://{urllib.parse.quote(str(salida / 'index.html'))}")
    return 0


def escribir_csv(salida: Path, filas) -> None:
    # Punto y coma y BOM: así lo abre bien un Excel en español.
    with open(salida / "facturas.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Fecha", "Buzón", "Carpeta", "De", "Asunto", "Adjuntos", "Correo"])
        for r in filas:
            w.writerow([r["llegada"].strftime("%Y-%m-%d %H:%M"), r["buzon"], r["carpeta"], r["de"],
                        r["asunto"], " | ".join(a.relative_to(salida).as_posix() for a in r["adjuntos"]),
                        r["eml"].relative_to(salida).as_posix()])


def escribir_indice(salida: Path, filas, origen: Path) -> None:
    e = html.escape
    cuerpo, mes_actual = [], None
    for r in filas:
        mes = (r["llegada"].year, r["llegada"].month)
        if mes != mes_actual:
            n = sum(1 for x in filas if (x["llegada"].year, x["llegada"].month) == mes)
            cuerpo.append(f'<tr class="mes"><th colspan="5">{MESES[mes[1] - 1]} {mes[0]}'
                          f' <small>· {n} correos</small></th></tr>')
            mes_actual = mes
        adj = " ".join(f'<a href="{enlace(salida, a)}">{e(a.suffix[1:].upper())}</a>' for a in r["adjuntos"])
        cuerpo.append(
            f'<tr><td class="f">{r["llegada"]:%d/%m/%Y}</td><td>{e(r["buzon"].split("@")[0])}'
            f'{"" if r["carpeta"] == "INBOX" else f"<br><small>{e(r["carpeta"])}</small>"}</td>'
            f'<td>{e(remitente(r["de"]))}</td><td><a href="{enlace(salida, r["eml"])}">{e(r["asunto"] or "(sin asunto)")}</a></td>'
            f'<td class="a">{adj or "—"}</td></tr>')
    (salida / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Facturas del correo</title>
<style>
  body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;color:#111;background:#fff}}
  .env{{max-width:72rem;margin:auto;padding:2rem 1rem 4rem}}
  h1{{margin:0 0 .3rem;font-size:1.8rem}}
  p{{color:#555;margin:.2rem 0 1rem;max-width:60ch}}
  input{{font:inherit;font-size:1.05rem;padding:.6rem .8rem;width:100%;max-width:30rem;
         border:2px solid #111;margin:.5rem 0 1rem}}
  table{{border-collapse:collapse;width:100%;font-size:.95rem}}
  th,td{{border-bottom:1px solid #ddd;padding:.5rem .6rem;text-align:left;vertical-align:top}}
  th{{background:#f3f3f1;position:sticky;top:0}}
  tr.mes th{{background:#111;color:#fff;font-size:1.05rem;position:static;padding:.7rem .6rem}}
  tr.mes small{{color:#bbb;font-weight:400}}
  td.f{{white-space:nowrap;font-variant-numeric:tabular-nums}}
  td.a a{{display:inline-block;background:#111;color:#fff;text-decoration:none;
         padding:.15rem .5rem;margin:0 .2rem .2rem 0;font-size:.8rem;font-weight:700}}
  small{{color:#777}}
  a{{color:#0b57a4}}
</style></head><body><div class="env">
<h1>Facturas del correo</h1>
<p>{len(filas)} correos de <b>{" y ".join(BUZONES)}</b>, del más nuevo al más antiguo.
Pulsa <b>PDF</b> para abrir la factura, o el asunto para abrir el correo entero.</p>
<p><small>Sacado del rescate {e(origen.name)} el {datetime.now():%d/%m/%Y}.
El correo llegado después a forwardemail está también en la Hotmail de copia.</small></p>
<input id="q" type="search" placeholder="Buscar proveedor, asunto o fecha…" autofocus>
<table><thead><tr><th>Llegó</th><th>Buzón</th><th>De</th><th>Asunto</th><th>Factura</th></tr></thead>
<tbody>
{chr(10).join(cuerpo)}
</tbody></table></div>
<script>
  var q = document.getElementById('q'), filas = document.querySelectorAll('tbody tr:not(.mes)');
  q.addEventListener('input', function () {{
    var t = q.value.toLowerCase();
    filas.forEach(function (f) {{ f.style.display = f.textContent.toLowerCase().indexOf(t) < 0 ? 'none' : ''; }});
  }});
</script></body></html>
""", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
