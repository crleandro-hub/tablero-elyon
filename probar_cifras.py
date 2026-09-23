#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probar_cifras.py - Tablero Gestion Grupo Elyon
==============================================
DIAGNOSTICO, no actualiza nada.

Pregunta que contesta
---------------------
El indice CIFRAS y el de Construccion en Acero se publican en
cifrasonline.com.ar, pero la pagina no trae ni tabla ni planilla: solo una
revista embebida de issuu y un boton "Descargar Informe" que apunta a un PDF
en Google Drive.

La unica via automatizable seria ese PDF, y depende de una sola cosa: que
tenga capa de texto. Si la tiene, se puede leer con la biblioteca estandar,
igual que se hace con el PDF de APYMECO. Si es una imagen escaneada, no hay
nada que hacer por script (es lo que paso con el informe de CEDUC).

Esto baja el PDF, intenta sacarle el texto y muestra lo que encontro, para
decidir con datos en vez de suponer.

Uso:
    python probar_cifras.py
    (o hace doble clic en 9-PROBAR-CIFRAS.bat)
"""

import os
import re
import sys
import zlib
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SALIDA   = os.path.join(BASE_DIR, "_diagnostico_cifras")

PAGINAS = {
    "CIFRAS":              "https://www.cifrasonline.com.ar/indice-cifras/",
    "Construccion en Acero": "https://www.cifrasonline.com.ar/indice-construccion-en-acero/",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 60


def abrir(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": "https://www.cifrasonline.com.ar/",
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def id_de_drive(html):
    """El boton 'Descargar Informe' apunta a drive.google.com/file/d/<ID>/view."""
    m = re.search(r"drive\.google\.com/file/d/([A-Za-z0-9_-]{20,})", html)
    return m.group(1) if m else None


def doc_de_issuu(html):
    """Por las dudas: el nombre del documento de issuu dice de que mes es."""
    m = re.search(r"e\.issuu\.com/embed\.html\?d=([A-Za-z0-9_\-]+)", html)
    return m.group(1) if m else None


def texto_de_pdf(datos):
    """Texto de un PDF, con la biblioteca estandar. Mismo metodo que APYMECO:
    los streams vienen comprimidos en zlib y las cadenas de texto van entre
    parentesis dentro de los operadores de dibujo."""
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", datos, re.S):
        bruto = m.group(1)
        try:
            partes.append(zlib.decompress(bruto))
        except Exception:
            partes.append(bruto)
    if not partes:
        partes = [datos]

    def desescapar(s):
        s = re.sub(rb"\\([()\\])", rb"\1", s)
        return re.sub(rb"\\([0-7]{1,3})",
                      lambda g: bytes([int(g.group(1), 8) & 0xFF]), s)

    salida = []
    for bloque in partes:
        for m in re.finditer(rb"\((?:\\.|[^\\()])*\)", bloque, re.S):
            salida.append(desescapar(m.group(0)[1:-1]))
    return b" ".join(salida).decode("latin-1", errors="replace")


def probar(nombre, url):
    print("=" * 62)
    print(" " + nombre)
    print("=" * 62)

    try:
        with abrir(url) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print("   [ERROR] No se pudo abrir la pagina: %s" % e)
        return

    doc = doc_de_issuu(html)
    if doc:
        print("   Revista de issuu : %s" % doc)

    fid = id_de_drive(html)
    if not fid:
        print("   [ERROR] La pagina no tiene el boton 'Descargar Informe'.")
        return
    print("   Archivo de Drive : %s" % fid)

    url_pdf = "https://drive.google.com/uc?export=download&id=" + fid
    try:
        with abrir(url_pdf) as r:
            datos = r.read()
    except Exception as e:
        print("   [ERROR] No se pudo bajar el PDF: %s" % e)
        return

    print("   Bajado           : %d KB" % (len(datos) // 1024))

    if not datos.startswith(b"%PDF"):
        print("   [NO SIRVE] Lo que vino no es un PDF. Drive suele devolver una")
        print("              pagina de confirmacion cuando el archivo es grande")
        print("              o no esta compartido por link.")
        print("              Primeros bytes: %r" % datos[:60])
        return

    texto = texto_de_pdf(datos)
    limpio = re.sub(r"\s+", " ", texto).strip()
    porcentajes = re.findall(r"-?\d{1,3}[.,]\d{1,2}\s*%", limpio)

    print("   Capa de texto    : %d caracteres" % len(limpio))
    if len(limpio) < 200:
        print("   [NO SIRVE] Practicamente sin texto: el PDF es una imagen.")
        print("              No hay forma de automatizarlo por script.")
    else:
        print("   Porcentajes      : %d encontrados" % len(porcentajes))
        if porcentajes:
            print("      %s" % ", ".join(porcentajes[:20]))
        print("   [SIRVE] Hay texto. Con esto se puede escribir el parseo.")

    os.makedirs(SALIDA, exist_ok=True)
    base = nombre.lower().replace(" ", "_")
    with open(os.path.join(SALIDA, base + ".pdf"), "wb") as f:
        f.write(datos)
    with open(os.path.join(SALIDA, base + ".txt"), "w", encoding="utf-8") as f:
        f.write(limpio)
    print("   Guardado en _diagnostico_cifras/%s.txt (y el .pdf al lado)" % base)
    print()


def main():
    print()
    print("Diagnostico: se puede automatizar el indice CIFRAS y el de Acero?")
    print()
    for nombre, url in PAGINAS.items():
        probar(nombre, url)
    print("Pasale a Claude lo que dice aca arriba y el .txt que quedo en")
    print("la carpeta _diagnostico_cifras, y con eso escribe el parseo.")
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
