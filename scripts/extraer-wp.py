#!/usr/bin/env python3
"""Extrae el contenido publicado de micromagic.tv desde WordPress a Markdown.

Fuente por defecto: la BD viva en IONOS via `ssh ionos`. Cuando IONOS se cancele,
restaura el volcado de ~/Backups/ionos-2026-09-18/db/ en un MySQL local y usa --mysql.

Uso:  python3 scripts/extraer-wp.py [--out src/content/paginas]
"""
import argparse, base64, html, json, re, subprocess, sys, urllib.request
from pathlib import Path

SITIO = "MICROMAGICESPONJAPROFESIONAL"
BASE_URL = "https://micromagic.tv"
PORTADA = "home"          # page_on_front = 1704 = /

# Páginas de fontanería de WooCommerce: no tienen contenido propio, se descartan.
DESCARTAR = {
    "carrito", "cart", "checkout", "finalizar-compra", "mi-cuenta", "my-account",
    "shop", "tienda", "post-page-elements", "sample-page",
    # Relleno de la plantilla: lorem ipsum en inglés, ocho de ellas idénticas entre sí.
    "live-customizer-options", "fully-responsive-theme", "woocommerce-support",
    "quick-view-support", "wishlist-support", "awesome-features", "speed-optimized",
    "compare-support", "seo-optimized",
}

REMOTO = r"""
cd ~/clickandbuilds/%s || exit 1
cfg=wp-config.php
n=$(sed -n "s/.*DB_NAME'[^']*'\([^']*\)'.*/\1/p" $cfg | head -1)
u=$(sed -n "s/.*DB_USER'[^']*'\([^']*\)'.*/\1/p" $cfg | head -1)
p=$(sed -n "s/.*DB_PASSWORD'[^']*'\([^']*\)'.*/\1/p" $cfg | head -1)
h=$(sed -n "s/.*DB_HOST'[^']*'\([^']*\)'.*/\1/p" $cfg | head -1)
pref=$(sed -n "s/.*table_prefix *= *'\([^']*\)'.*/\1/p" $cfg | head -1)
export MYSQL_PWD="$p"
mysql -h "$h" -u "$u" "$n" -N -B -e "
  SELECT REPLACE(REPLACE(TO_BASE64(JSON_OBJECT(
    'id', ID, 'slug', post_name, 'title', post_title, 'type', post_type,
    'date', DATE_FORMAT(post_date,'%%Y-%%m-%%d'), 'modified', DATE_FORMAT(post_modified,'%%Y-%%m-%%d'),
    'excerpt', post_excerpt, 'menu_order', menu_order, 'content', post_content)),'\n',''),'\r','')
  FROM ${pref}posts
  WHERE post_status='publish' AND post_type IN ('page','post')
  ORDER BY post_type, menu_order, post_title;"
""" % SITIO


def traer():
    r = subprocess.run(["ssh", "ionos", REMOTO], capture_output=True, text=True, timeout=180)
    if r.returncode:
        sys.exit(f"ssh falló: {r.stderr[:400]}")
    filas = []
    for linea in r.stdout.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        filas.append(json.loads(base64.b64decode(linea).decode("utf-8", "replace")))
    return filas


def traer_render(slug: str) -> str:
    """Descarga la página servida y devuelve el HTML de su zona principal.

    Algunas páginas (la portada, las de Elementor) no guardan nada en post_content:
    las construye la plantilla del tema. Para esas, el HTML renderizado es la única
    fuente. Requiere que el WordPress de IONOS siga en pie.
    """
    url = f"{BASE_URL}/" if slug == PORTADA else f"{BASE_URL}/{slug}/"
    req = urllib.request.Request(url, headers={"User-Agent": "micromagic-migracion/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            doc = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  no se pudo descargar {url}: {e}")
        return ""
    # Fuera lo que nunca es contenido.
    for tag in ("script", "style", "nav", "header", "footer", "form", "noscript"):
        doc = re.sub(rf"<{tag}\b.*?</{tag}>", "", doc, flags=re.S | re.I)
    # Quedarse con la región principal si el tema la marca.
    for patron in (r"<main\b[^>]*>(.*?)</main>",
                   r'<div[^>]*class="[^"]*(?:entry-content|site-main|page-content)[^"]*"[^>]*>(.*)'):
        m = re.search(patron, doc, flags=re.S | re.I)
        if m:
            return m.group(1)
    return doc


# --- limpieza del HTML de WordPress/Elementor -------------------------------

def limpiar(bruto: str) -> str:
    t = bruto or ""
    # Los shortcodes de Elementor/Woo no significan nada fuera de WordPress.
    t = re.sub(r"\[/?[a-zA-Z_][^\]]*\]", "", t)
    # Comentarios de bloque de Gutenberg.
    t = re.sub(r"<!--\s*/?wp:.*?-->", "", t, flags=re.S)
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    # <script>/<style> completos.
    t = re.sub(r"<(script|style)\b.*?</\1>", "", t, flags=re.S | re.I)
    # Saltos de línea a partir de los bloques.
    t = re.sub(r"</(p|div|h[1-6]|li|tr|section)>", "\n\n", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    # Encabezados e imágenes a Markdown antes de tirar el resto de etiquetas.
    t = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", lambda m: "\n" + "#" * int(m.group(1)) + " " + m.group(2).strip() + "\n", t, flags=re.S | re.I)
    t = re.sub(r'<img[^>]*src="([^"]+)"[^>]*alt="([^"]*)"[^>]*>', r"\n![\2](\1)\n", t, flags=re.I)
    t = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', r"\n![](\1)\n", t, flags=re.I)
    t = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", t, flags=re.S | re.I)
    # Markdown no admite espacio pegado a los asteriscos: `**x **` saldría literal.
    # El espacio sobrante se saca fuera del énfasis.
    t = re.sub(r"<(strong|b)>(\s*)(.*?)(\s*)</\1>",
               lambda m: f"{m.group(2)}**{m.group(3)}**{m.group(4)}" if m.group(3).strip() else m.group(0),
               t, flags=re.S | re.I)
    t = re.sub(r"<(em|i)>(\s*)(.*?)(\s*)</\1>",
               lambda m: f"{m.group(2)}*{m.group(3)}*{m.group(4)}" if m.group(3).strip() else m.group(0),
               t, flags=re.S | re.I)
    t = re.sub(r"<li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)               # el resto de etiquetas, fuera
    t = html.unescape(t)
    # Viñetas que se quedaron sin texto: son los <li> de menús, carruseles y
    # rejillas de producto, que no llevan prosa dentro.
    t = "\n".join(l for l in t.splitlines() if l.strip() not in ("-", "*", "•", ""))

    # Cada línea del contenido de WordPress era su propio bloque. En Markdown,
    # dos líneas seguidas se funden en un párrafo, así que hay que separarlas.
    # Excepción: los elementos de lista consecutivos deben seguir juntos.
    lineas = t.splitlines()
    bloques: list[str] = []
    for i, l in enumerate(lineas):
        bloques.append(l)
        if not l.strip():
            continue
        sig = lineas[i + 1] if i + 1 < len(lineas) else ""
        if not sig.strip():
            continue
        if l.lstrip().startswith("- ") and sig.lstrip().startswith("- "):
            continue
        bloques.append("")
    t = "\n".join(bloques)

    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def yaml_seguro(s: str) -> str:
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="src/content/paginas")
    args = ap.parse_args()
    raiz = Path(__file__).resolve().parent.parent
    destino = raiz / args.out
    destino.mkdir(parents=True, exist_ok=True)

    filas = traer()
    escritas = omitidas = 0
    for f in filas:
        slug = (f.get("slug") or "").strip()
        if not slug or slug in DESCARTAR:
            omitidas += 1
            continue
        cuerpo = limpiar(f.get("content"))
        origen = "bd"
        if len(cuerpo) < 40:
            # Sin contenido en la BD: la construye la plantilla. Vamos al HTML servido.
            print(f"  {slug}: vacía en BD, descargando la página servida…")
            cuerpo = limpiar(traer_render(slug))
            origen = "html-renderizado"
        if len(cuerpo) < 40:
            omitidas += 1
            print(f"  omitida (sin texto recuperable): {slug}")
            continue
        fm = [
            "---",
            f"titulo: {yaml_seguro(html.unescape(f.get('title') or slug))}",
            f"slug: {slug}",
            f"tipo: {f.get('type')}",
            f"fecha: {f.get('date')}",
            f"orden: {f.get('menu_order', 0)}",
            f"resumen: {yaml_seguro(limpiar(f.get('excerpt'))[:200])}",
            f"origen: {origen}",
            "---",
            "",
        ]
        (destino / f"{slug}.md").write_text("\n".join(fm) + cuerpo + "\n", encoding="utf-8")
        escritas += 1

    print(f"\n{escritas} páginas escritas en {destino}, {omitidas} descartadas.")


if __name__ == "__main__":
    main()
