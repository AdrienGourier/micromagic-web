#!/usr/bin/env python3
"""Saca las imágenes originales del backup y reapunta las rutas del Markdown.

WordPress guarda, por cada imagen, una decena de miniaturas (`-300x200.jpg`).
Astro genera las suyas al construir, así que aquí solo interesan los originales.

Uso:  python3 scripts/extraer-imagenes.py
"""
import re, sys, tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TARBALL = Path.home() / "Backups/ionos-2026-09-18/files/MICROMAGICESPONJAPROFESIONAL.tar.gz"
DESTINO = RAIZ / "public/uploads"
PAGINAS = RAIZ / "src/content/paginas"

EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg")
MINIATURA = re.compile(r"-\d+x\d+(\.[A-Za-z]+)$")


def es_original(nombre: str) -> bool:
    return nombre.lower().endswith(EXT) and not MINIATURA.search(nombre)


def extraer() -> int:
    if not TARBALL.exists():
        sys.exit(f"no encuentro el backup: {TARBALL}")
    DESTINO.mkdir(parents=True, exist_ok=True)
    n = 0
    with tarfile.open(TARBALL, "r:gz") as tf:
        for m in tf:
            if not m.isfile() or "/wp-content/uploads/" not in m.name:
                continue
            if not es_original(m.name):
                continue
            rel = m.name.split("/wp-content/uploads/", 1)[1]   # 2019/02/foto.jpg
            salida = DESTINO / rel
            salida.parent.mkdir(parents=True, exist_ok=True)
            f = tf.extractfile(m)
            if f is None:
                continue
            salida.write_bytes(f.read())
            n += 1
    return n


def reapuntar() -> int:
    """https://micromagic.tv/wp-content/uploads/2019/02/x-300x200.jpg -> /uploads/2019/02/x.jpg"""
    cambios = 0
    for md in PAGINAS.glob("*.md"):
        t = original = md.read_text(encoding="utf-8")
        t = re.sub(r"https?://(?:www\.)?micromagic\.tv/wp-content/uploads/", "/uploads/", t)
        t = re.sub(r"(?<![\w/])wp-content/uploads/", "/uploads/", t)
        # colapsar cada miniatura a su original
        t = re.sub(r"(/uploads/\d{4}/\d{2}/[^)\s\"']+?)-\d+x\d+(\.[A-Za-z]+)", r"\1\2", t)
        if t != original:
            md.write_text(t, encoding="utf-8")
            cambios += 1
    return cambios


def comprobar() -> None:
    faltan = set()
    for md in PAGINAS.glob("*.md"):
        for ruta in re.findall(r"\(/uploads/([^)\s\"']+)\)", md.read_text(encoding="utf-8")):
            if not (DESTINO / ruta).exists():
                faltan.add(ruta)
    if faltan:
        print(f"\n  {len(faltan)} imágenes referenciadas que NO están en el backup:")
        for r in sorted(faltan)[:15]:
            print(f"    {r}")
    else:
        print("\n  todas las imágenes referenciadas existen en public/uploads")


if __name__ == "__main__":
    print(f"extrayendo originales de {TARBALL.name} …")
    n = extraer()
    c = reapuntar()
    print(f"{n} imágenes en {DESTINO.relative_to(RAIZ)}; {c} ficheros Markdown reapuntados")
    comprobar()
