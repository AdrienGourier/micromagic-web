#!/usr/bin/env python3
"""Copia rhinopaint.es (WordPress + WooCommerce en IONOS) a un sitio estático.

El contrato de IONOS termina el 27/12/2026 y con él el WordPress. La tienda no
ha tenido ni un pedido (la base de datos del 18/09/2026 no tiene ninguno), así
que se conserva la web tal cual se ve y se quita lo que necesita servidor:

- «Añadir al carrito» pasa a «Pedir presupuesto», que lleva a /contactar.
- El formulario de Contact Form 7 pasa a un enlace a info@rhinopaint.es (el
  buzón vive en forwardemail, no en IONOS).
- Se quitan el formulario de valoraciones, la búsqueda, el carrito de la
  cabecera y de la barra lateral, y los scripts que llaman a admin-ajax.
- Carrito y Mi cuenta salen del menú; Contactar entra.

Las URLs se conservan (cada página en <ruta>/index.html) y las de la tienda
muerta se redirigen en la CloudFront Function del template.

Uso:
  python3 rhinopaint/scripts/copiar-web.py --salida rhinopaint/sitio
  python3 rhinopaint/scripts/copiar-web.py --salida rhinopaint/sitio --faltan faltan.txt
    (descarga además las rutas de faltan.txt, una por línea: las que el
     navegador pidió y dieron 404 en la prueba local)
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "rhinopaint.es"
ORIGEN = f"https://{HOST}"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
CORREO = "info@rhinopaint.es"

# Rutas de la tienda que no se copian: la CloudFront Function las redirige.
TIENDA_MUERTA = {"/cart", "/carrito", "/checkout", "/finalizar-compra",
                 "/my-account", "/mi-cuenta"}

# Un recurso de WordPress, absoluto (también con las barras escapadas de los
# JSON de Elementor) o relativo a la raíz.
RE_RECURSO = re.compile(
    r"""(?:https?:)?(?:\\?/\\?/)(?:www\.)?rhinopaint\.es((?:\\?/)wp-(?:content|includes)(?:\\?/)[^"'\s)<>\\]*(?:\\/[^"'\s)<>\\]*)*)"""
    r"""|(?<=["'(\s,])((?:\\?/)wp-(?:content|includes)(?:\\?/)[^"'\s)<>]*)""")
RE_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)|@import\s+['"]([^'"]+)['"]""")


def bajar(url: str, intentos: int = 3) -> tuple[int, bytes, str]:
    """GET con reintentos. Devuelve (código, cuerpo, URL final)."""
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.code == 404 else b"", url
        except Exception:  # red: reintentar
            if n == intentos - 1:
                return 0, b"", url
            time.sleep(2 * (n + 1))
    return 0, b"", url


def paginas_del_sitemap() -> list[str]:
    _, indice, _ = bajar(f"{ORIGEN}/wp-sitemap.xml")
    rutas = {"/"}
    for sub in re.findall(rb"<loc>([^<]+)</loc>", indice):
        _, xml, _ = bajar(sub.decode())
        for loc in re.findall(rb"<loc>([^<]+)</loc>", xml):
            ruta = urllib.parse.urlsplit(loc.decode()).path or "/"
            rutas.add(ruta.rstrip("/") or "/")
    return sorted(r for r in rutas if r not in TIENDA_MUERTA)


def ruta_limpia(bruta: str) -> str | None:
    """'/wp-content/x.css?ver=1' (o con \\/ y &amp;) -> '/wp-content/x.css'."""
    r = html.unescape(bruta.replace("\\/", "/"))
    r = urllib.parse.urlsplit(r).path
    r = urllib.parse.unquote(r)
    # Corta en lo que no puede ir en una ruta: «, », comillas tipográficas…
    m = re.match(r"[\w./%~+-]+", r)
    r = m.group(0) if m else ""
    if not r.startswith(("/wp-content/", "/wp-includes/")) or r.endswith("/"):
        return None
    if r.endswith((".php",)):
        return None
    return r


def recursos_en(texto: str) -> set[str]:
    encontrados = set()
    for m in RE_RECURSO.finditer(texto):
        r = ruta_limpia(m.group(1) or m.group(2))
        if r:
            encontrados.add(r)
    # srcset: "a.jpg 300w, b.jpg 768w"
    for srcset in re.findall(r'srcset="([^"]+)"', texto):
        for parte in srcset.split(","):
            r = ruta_limpia(urllib.parse.urlsplit(parte.strip().split(" ")[0]).path)
            if r:
                encontrados.add(r)
    return encontrados


def recursos_en_css(css: str, ruta_css: str) -> set[str]:
    base = f"{ORIGEN}{ruta_css}"
    encontrados = set()
    for m in RE_CSS_URL.finditer(css):
        ref = (m.group(1) or m.group(2) or "").strip()
        if not ref or ref.startswith(("data:", "#")):
            continue
        absoluta = urllib.parse.urljoin(base, ref)
        partes = urllib.parse.urlsplit(absoluta)
        if partes.hostname not in (HOST, f"www.{HOST}"):
            continue
        r = ruta_limpia(partes.path)
        if r:
            encontrados.add(r)
    return encontrados


# --- Transformación del HTML -------------------------------------------------

BOTON_PRESUPUESTO = ('<a href="/contactar" class="single_add_to_cart_button button alt">'
                     'Pedir presupuesto</a>')
BLOQUE_CONTACTO = (
    '<div class="contacto-estatico">'
    f'<p>Escríbenos a <a href="mailto:{CORREO}">{CORREO}</a> y te contestamos '
    'con el presupuesto y el plazo de entrega.</p>'
    f'<p><a class="button" href="mailto:{CORREO}?subject=Consulta%20Rhinopaint">'
    'Escribir un correo</a></p></div>')
CSS_EXTRA = (
    "<style id=\"estatico\">"
    ".header-cart,.site-header-cart,#woocommerce_widget_cart-1,#search-1,"
    "#tab-title-reviews,#tab-reviews,.woocommerce-review-link{display:none!important}"
    ".contacto-estatico{margin:1.5em 0;font-size:1.1em}"
    ".contacto-estatico .button{display:inline-block;margin-top:.5em}"
    "</style>")


# Jetpack sirve las imágenes por el CDN de WordPress.com (i0.wp.com/rhinopaint.es/…)
# y el núcleo y WooCommerce desde c0.wp.com. Se traen a casa: la copia no debe
# depender de WordPress.com.
RE_FOTON = re.compile(r"""https?:(\\?/)\\?/i[0-3]\.wp\.com\\?/(?:www\.)?rhinopaint\.es(\\?/[^"'\s)?]*)(?:\?[^"'\s)]*)?""")
RE_C0_NUCLEO = re.compile(r"""https?:(\\?/)\\?/c0\.wp\.com\\?/c\\?/[\d.]+\\?/""")
RE_C0_PLUGIN = re.compile(r"""https?:(\\?/)\\?/c0\.wp\.com\\?/p\\?/([\w-]+)\\?/[\d.]+\\?/""")


RE_TROZO = re.compile(r"__elementorLoadChunk\(\s*[`'\"]([\w-]+)[`'\"]")


def relativizar(s: str) -> str:
    """Todo lo de rhinopaint.es pasa a ser relativo a la raíz (también con \\/)."""
    s = RE_FOTON.sub(lambda m: m.group(2), s)
    s = RE_C0_NUCLEO.sub(lambda m: m.group(1), s)
    s = RE_C0_PLUGIN.sub(lambda m: f"{m.group(1)}wp-content{m.group(1)}plugins{m.group(1)}{m.group(2)}{m.group(1)}", s)
    for prefijo in ("https://www.rhinopaint.es", "http://www.rhinopaint.es",
                    "https://rhinopaint.es", "http://rhinopaint.es"):
        s = s.replace(prefijo + "/", "/").replace(prefijo + '"', '/"').replace(prefijo + "'", "/'")
        escapado = prefijo.replace("/", "\\/")
        s = s.replace(escapado + "\\/", "\\/").replace(escapado + '"', '\\/"')
    return s


def transformar(pagina: str) -> str:
    s = pagina

    # Etiquetas que deben seguir siendo absolutas.
    protegidas: list[str] = []

    def proteger(m: re.Match) -> str:
        protegidas.append(m.group(0))
        return f"\x00{len(protegidas) - 1}\x00"

    s = re.sub(r'<link[^>]+rel=["\']canonical["\'][^>]*>|<meta[^>]+property=["\']og:url["\'][^>]*>',
               proteger, s)

    s = relativizar(s)

    # Tienda: botones del listado y del producto.
    s = re.sub(r'<a [^>]*href="[^"]*\?add-to-cart=\d+"[^>]*>.*?</a>',
               '<a href="/contactar" class="button">Pedir presupuesto</a>', s, flags=re.S)
    s = re.sub(r'<form class="cart".*?</form>', BOTON_PRESUPUESTO, s, flags=re.S)

    # Formulario de contacto -> correo.
    s = re.sub(r'<div class="wpcf7[^"]*".*?</form>\s*</div>', BLOQUE_CONTACTO, s, flags=re.S)

    # Valoraciones (necesitan wp-comments-post.php).
    s = re.sub(r'<div id="respond".*?</div><!-- #respond -->', "", s, flags=re.S)

    # Búsqueda (necesita PHP).
    s = re.sub(r'<form role="search".*?</form>', "", s, flags=re.S)

    # Menú: Carrito -> Contactar, fuera Mi cuenta.
    s = re.sub(r'(<a title=")Carrito(" href=")/(?:cart|carrito)(" class="nav-link">)Carrito',
               r"\1Contactar\2/contactar\3Contactar", s)
    s = re.sub(r'<li[^>]*>\s*<a title="Mi cuenta" href="/(?:my-account|mi-cuenta)"[^>]*>Mi cuenta</a>\s*</li>',
               "", s)

    # Icono de «Mi cuenta» de la cabecera.
    s = re.sub(r'<div class="header-my-account[^"]*">\s*<div class="header-login">\s*'
               r'<a href="/(?:my-account|mi-cuenta)"[^>]*>.*?</a>\s*</div>\s*</div>', "", s, flags=re.S)

    # Scripts de la tienda, del formulario y de estadísticas de Jetpack (WordPress.com),
    # en línea o con src: sin WordPress detrás solo darían errores.
    s = re.sub(r'<script\b[^>]*\bid="(?:wc-add-to-cart|wc-cart-fragments|woocommerce-analytics|'
               r'sourcebuster|wc-order-attribution|jetpack-stats|ce4wp_form_submit|contact-form-7'
               r')[^"]*"[^>]*>.*?</script>\s*', "", s, flags=re.S)

    # Scripts que llaman al servidor y enlaces a la API de WordPress.
    s = re.sub(r'<script[^>]+src="[^"]*(?:cart-fragments|add-to-cart|contact-form-7|wpcf7|'
               r'comment-reply)[^"]*"[^>]*></script>\s*', "", s)
    s = re.sub(r'<link[^>]+rel=["\'](?:EditURI|pingback|https://api\.w\.org/|shortlink)["\'][^>]*>\s*', "", s)
    s = re.sub(r'<link[^>]+rel=["\'](?:preconnect|dns-prefetch)["\'][^>]+\.wp\.com["\'][^>]*>\s*', "", s)
    s = re.sub(r'<link[^>]+type=["\']application/(?:json\+oembed|xml\+oembed|json)["\'][^>]*>\s*', "", s)

    s = s.replace("</head>", CSS_EXTRA + "</head>", 1)

    for i, original in enumerate(protegidas):
        s = s.replace(f"\x00{i}\x00", original)
    return s


def guardar(salida: Path, ruta: str, datos: bytes) -> None:
    destino = salida / ruta.lstrip("/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--faltan", type=Path, help="rutas extra que descargar, una por línea")
    args = ap.parse_args()
    salida: Path = args.salida
    salida.mkdir(parents=True, exist_ok=True)

    pendientes: set[str] = set()
    hechos: set[str] = set()
    fallos: list[str] = []
    copiadas: list[str] = []

    if args.faltan:
        for linea in args.faltan.read_text().split():
            r = ruta_limpia(linea)
            if r:
                pendientes.add(r)
    else:
        paginas = paginas_del_sitemap()
        print(f"{len(paginas)} páginas")
        for ruta in paginas:
            codigo, cuerpo, final = bajar(f"{ORIGEN}{ruta}")
            if codigo != 200:
                fallos.append(f"{codigo} {ruta}")
                continue
            texto = cuerpo.decode("utf-8", "replace")
            final_html = transformar(texto)
            pendientes |= recursos_en(texto) | recursos_en(final_html)
            fichero = "index.html" if ruta == "/" else f"{ruta.strip('/')}/index.html"
            guardar(salida, fichero, final_html.encode("utf-8"))
            copiadas.append(ruta)
            print(f"  página {ruta}")
        # La página 404 del tema, para CloudFront.
        codigo, cuerpo, _ = bajar(f"{ORIGEN}/esta-pagina-no-existe-404")
        if cuerpo:
            texto = transformar(cuerpo.decode("utf-8", "replace"))
            pendientes |= recursos_en(texto)
            guardar(salida, "404.html", texto.encode("utf-8"))
        codigo, cuerpo, _ = bajar(f"{ORIGEN}/favicon.ico")
        if codigo == 200:
            guardar(salida, "/favicon.ico", cuerpo)
        robots = "User-agent: *\nAllow: /\nSitemap: https://rhinopaint.es/sitemap.xml\n"
        guardar(salida, "robots.txt", robots.encode())
        urls = "".join(f"<url><loc>{ORIGEN}{r}</loc></url>" for r in copiadas)
        guardar(salida, "sitemap.xml", (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n').encode())

    while pendientes:
        ruta = pendientes.pop()
        if ruta in hechos:
            continue
        hechos.add(ruta)
        url = ORIGEN + urllib.parse.quote(ruta)
        codigo, cuerpo, _ = bajar(url)
        if codigo != 200:
            fallos.append(f"{codigo} {ruta}")
            continue
        if ruta.endswith((".css", ".js", ".json")):
            texto = relativizar(cuerpo.decode("utf-8", "replace"))
            guardar(salida, ruta, texto.encode("utf-8"))
            if ruta.endswith(".css"):
                pendientes |= recursos_en_css(texto, ruta) - hechos
            pendientes |= recursos_en(texto) - hechos
            # Elementor carga trozos de JS a demanda (__elementorLoadChunk(`nombre`))
            # desde <su carpeta>/chunks/nombre.min.js: ninguna página los nombra.
            carpeta = ruta.rsplit("/", 1)[0]
            for nombre in RE_TROZO.findall(texto):
                pendientes.add(f"{carpeta}/chunks/{nombre}.min.js")
        else:
            guardar(salida, ruta, cuerpo)
    print(f"{len(hechos)} recursos")

    if fallos:
        print(f"{len(fallos)} sin descargar:")
        for f in sorted(fallos):
            print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
