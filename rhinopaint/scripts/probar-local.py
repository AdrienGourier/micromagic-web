#!/usr/bin/env python3
"""Sirve la copia estática como lo hará CloudFront y la recorre con Chrome.

Abre cada página del sitemap en Chrome sin ventana y apunta todo lo que el
navegador pide y no existe (scripts que cargan otros scripts, fondos de CSS,
fuentes). Eso es lo que hay que pasar a `copiar-web.py --faltan`.

También comprueba que no queda nada de la tienda ni del formulario.

Uso:
  python3 rhinopaint/scripts/probar-local.py rhinopaint/sitio [--faltan faltan.txt]
Sale con 1 si falta algo o queda algo de la tienda.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import re
import subprocess
import sys
import threading
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TIENDA = {"/cart", "/carrito", "/checkout", "/finalizar-compra", "/my-account", "/mi-cuenta",
          "/shop", "/tienda-2"}
faltan: set[str] = set()


class Manejador(http.server.SimpleHTTPRequestHandler):
    """Las mismas reglas que la CloudFront Function del template."""

    def do_GET(self):  # noqa: N802
        ruta = self.path.split("?", 1)[0]
        if ruta.rstrip("/") in TIENDA:
            self.send_response(301)
            self.send_header("Location", "/contactar")
            self.end_headers()
            return
        if ruta.endswith("/"):
            self.path = ruta + "index.html"
        elif "." not in ruta.rsplit("/", 1)[-1]:
            self.path = ruta + "/index.html"
        else:
            self.path = ruta
        destino = Path(self.translate_path(self.path))
        if not destino.exists():
            faltan.add(ruta)
        super().do_GET()

    def log_message(self, *a):  # silencio
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sitio", type=Path)
    ap.add_argument("--faltan", type=Path)
    args = ap.parse_args()

    servidor = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Manejador, directory=str(args.sitio)))
    puerto = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    sitemap = (args.sitio / "sitemap.xml").read_text()
    rutas = [re.sub(r"^https://[^/]+", "", u) or "/" for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
    problemas = []
    for ruta in rutas:
        url = f"http://127.0.0.1:{puerto}{ruta}"
        dom = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
             "--virtual-time-budget=6000", "--window-size=1366,900", "--dump-dom", url],
            capture_output=True, text=True, timeout=90).stdout
        for marca in ("add-to-cart", "wpcf7-form", "wp-comments-post", 'role="search"',
                      "Añadir al carrito", "Mi cuenta"):
            if marca in dom:
                problemas.append(f"{ruta}: queda «{marca}»")
    servidor.shutdown()

    reales = sorted(f for f in faltan if not f.endswith("/favicon.ico"))
    for f in reales:
        print("FALTA", f)
    for p in problemas:
        print("TIENDA", p)
    if args.faltan:
        args.faltan.write_text("\n".join(reales) + "\n")
    print(f"{len(rutas)} páginas, {len(reales)} recursos que faltan, {len(problemas)} restos de la tienda")
    return 1 if reales or problemas else 0


if __name__ == "__main__":
    sys.exit(main())
