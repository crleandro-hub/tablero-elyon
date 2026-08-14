#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probar_ieric_cordoba.py - Tablero Gestion Grupo Elyon
=====================================================
DIAGNOSTICO. No escribe ningun cache, no toca el tablero, no publica nada.

Que hace
--------
Abre la pagina de series estadisticas de Cordoba del IERIC, lista todas las
planillas que cuelgan de ahi, las baja y vuelca su estructura: hojas, tamaño,
primeras y ultimas filas. Con eso se decide que se puede convertir en
indicador antes de escribir un solo parser.

    https://www.ieric.org.ar/series_estadisticas/cordoba/

Por que hace falta
------------------
1. Las URLs del IERIC llevan la carpeta AAAA/MM de la fecha de subida y
   cambian cuando refrescan el archivo. Hardcodearlas deja el script obsoleto
   SIN dar error, que es la peor forma de romperse. Hay que resolverlas
   leyendo la pagina en cada corrida, y esto confirma que ese metodo anda.

2. Los .xls del IERIC son formato viejo (BIFF/OLE2), que la libreria estandar
   no lee. xlsx_lite.py sirve para .xlsx pero no para esto. Hay que confirmar
   que xlrd este instalado y que abra los archivos.

3. Nadie pudo abrir todavia estos archivos, asi que no sabemos que periodo
   cubren, que columnas traen ni si el de cemento separa bolsa de granel.
   Escribir el parser sin ver eso seria adivinar.

Que NO hace
-----------
No genera *_cache.js, no corre build_publicar.py, no hace commit ni push.
Los archivos bajados quedan en _diagnostico_ieric\, que esta en el
.gitignore para que no se publiquen solos en el repo publico.

Uso:
    python probar_ieric_cordoba.py
"""

import os
import re
import ssl
import sys
import urllib.request as req
from urllib.parse import urljoin

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_DIR = os.path.join(BASE_DIR, "_diagnostico_ieric")

PAGINA = "https://www.ieric.org.ar/series_estadisticas/cordoba/"
TIMEOUT = 60
MAX_ARCHIVOS = 15
MAX_BYTES = 20 * 1024 * 1024

FILAS_CABEZA = 22      # primeras filas que se vuelcan de cada hoja
FILAS_COLA = 10        # ultimas filas (ahi esta el dato mas reciente)
COLS = 12              # columnas que se vuelcan
ANCHO = 18             # ancho de cada celda al imprimir

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


# ─────────────────────────────────────────────────────────────────────────
#  Descarga
# ─────────────────────────────────────────────────────────────────────────

def _get(url):
    """GET que devuelve bytes. Reintenta sin verificar el certificado, igual
    que el resto de los scripts del tablero."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/vnd.ms-excel,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read()


def links_de_planillas(html, base):
    """Saca los href a .xls/.xlsx de la pagina, con el texto del enlace.
    Devuelve [(url, etiqueta)] sin repetidos y en orden de aparicion."""
    encontrados = []
    vistos = set()
    patron = re.compile(
        r"""<a\b[^>]*href\s*=\s*["']([^"']+\.xlsx?)["'][^>]*>(.*?)</a>""",
        re.I | re.S)
    for m in patron.finditer(html):
        url = urljoin(base, m.group(1).strip())
        etiqueta = re.sub(r"<[^>]*>", " ", m.group(2))
        etiqueta = " ".join(etiqueta.split()) or "(sin texto)"
        if url in vistos:
            continue
        vistos.add(url)
        encontrados.append((url, etiqueta))
    return encontrados


def firma(datos):
    """Que es realmente el archivo, mas alla de la extension."""
    if datos[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "OLE2  -> .xls viejo (BIFF), necesita xlrd"
    if datos[:2] == b"PK":
        return "ZIP   -> .xlsx moderno, lo lee xlsx_lite"
    cabeza = datos[:200].lstrip().lower()
    if cabeza.startswith(b"<!") or cabeza.startswith(b"<html"):
        return "HTML  -> NO es una planilla (pagina de error o login)"
    return "desconocido, primeros bytes: " + repr(datos[:12])


# ─────────────────────────────────────────────────────────────────────────
#  Lectura
# ─────────────────────────────────────────────────────────────────────────

def _leer_xls(datos):
    """Formato viejo BIFF. Requiere xlrd (xlrd 2.x lee .xls, no .xlsx)."""
    import xlrd
    wb = xlrd.open_workbook(file_contents=datos)
    hojas = {}
    for nombre in wb.sheet_names():
        sh = wb.sheet_by_name(nombre)
        filas = []
        for i in range(sh.nrows):
            fila = []
            for j in range(sh.ncols):
                c = sh.cell(i, j)
                v = c.value
                if c.ctype == xlrd.XL_CELL_DATE:
                    try:
                        y, mo, d = xlrd.xldate_as_tuple(v, wb.datemode)[:3]
                        v = "%04d-%02d-%02d" % (y, mo, d)
                    except Exception:
                        pass
                elif c.ctype == xlrd.XL_CELL_EMPTY:
                    v = None
                fila.append(v)
            filas.append(fila)
        hojas[nombre] = filas
    return hojas, "xlrd"


def _leer_xlsx(datos):
    """Formato moderno. xlsx_lite.py ya esta en la carpeta y usa solo stdlib."""
    from xlsx_lite import leer_hoja, nombres_de_hojas
    return {n: leer_hoja(datos, n) for n in nombres_de_hojas(datos)}, "xlsx_lite"


def leer(datos):
    if datos[:2] == b"PK":
        return _leer_xlsx(datos)
    if datos[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return _leer_xls(datos)
    raise ValueError("El archivo no es .xls ni .xlsx")


# ─────────────────────────────────────────────────────────────────────────
#  Volcado
# ─────────────────────────────────────────────────────────────────────────

def celda(v):
    if v is None:
        return ""
    if isinstance(v, float):
        s = ("%.4f" % v).rstrip("0").rstrip(".")
    else:
        s = str(v)
    s = " ".join(s.split())
    return s[:ANCHO]


def volcar_hoja(nombre, filas):
    anchos = [len(f) for f in filas] or [0]
    print("")
    print("   HOJA '%s'  ->  %d filas x %d columnas (max)"
          % (nombre, len(filas), max(anchos)))
    print("   " + "-" * 70)

    if not filas:
        print("   (hoja vacia)")
        return

    def mostrar(i):
        fila = filas[i]
        llenas = [v for v in fila if v is not None and str(v).strip() != ""]
        # Fila de una sola celda: casi siempre es el titulo de la serie, la
        # unidad, o el pie con la fuente ("elaboracion IERIC en base a AFCP").
        # Eso es justo lo que hay que leer entero, no cortado a ANCHO.
        if len(llenas) == 1:
            print("   %4d: %s" % (i, " ".join(str(llenas[0]).split())[:100]))
            return
        txt = " | ".join(celda(v) for v in fila[:COLS])
        if len(fila) > COLS:
            txt += " | ..."
        print("   %4d: %s" % (i, txt))

    cabeza = min(FILAS_CABEZA, len(filas))
    for i in range(cabeza):
        mostrar(i)

    if len(filas) > cabeza + FILAS_COLA:
        print("   ....  (%d filas del medio omitidas)"
              % (len(filas) - cabeza - FILAS_COLA))
        for i in range(len(filas) - FILAS_COLA, len(filas)):
            mostrar(i)
    elif len(filas) > cabeza:
        for i in range(cabeza, len(filas)):
            mostrar(i)


# ─────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 74)
    print(" DIAGNOSTICO IERIC CORDOBA - series estadisticas provinciales")
    print(" " + PAGINA)
    print("=" * 74)
    print("")
    print(" Esto NO escribe ningun cache ni modifica el tablero.")
    print("")

    print("--- DEPENDENCIAS ---")
    try:
        import xlrd
        print("   [ok]    xlrd %s  (hace falta para los .xls viejos)"
              % getattr(xlrd, "__version__", "?"))
    except ImportError:
        print("   [FALTA] xlrd  ->  instalar con:  pip install xlrd")
        print("           Sin xlrd no se pueden abrir los .xls del IERIC.")
    try:
        from xlsx_lite import leer_hoja  # noqa: F401
        print("   [ok]    xlsx_lite (de la carpeta, solo libreria estandar)")
    except Exception as e:
        print("   [FALTA] xlsx_lite -> %s" % e)
    print("")

    print("--- PAGINA ---")
    try:
        html = _get(PAGINA).decode("utf-8", "replace")
    except Exception as e:
        print("   [ERROR] No se pudo abrir la pagina: %s" % e)
        print("   Si es un problema de red o proxy, probalo en el navegador.")
        return 1
    print("   [ok] %d caracteres" % len(html))

    planillas = links_de_planillas(html, PAGINA)
    if not planillas:
        print("   [ERROR] No se encontro ningun enlace a .xls/.xlsx.")
        print("   Puede que el IERIC haya cambiado la pagina. Guardando el")
        print("   HTML en _diagnostico_ieric\\pagina_cordoba.html para mirarlo.")
        os.makedirs(DEST_DIR, exist_ok=True)
        with open(os.path.join(DEST_DIR, "pagina_cordoba.html"), "w",
                  encoding="utf-8") as f:
            f.write(html)
        return 1

    print("")
    print("--- PLANILLAS ENCONTRADAS (%d) ---" % len(planillas))
    for i, (url, etiqueta) in enumerate(planillas, 1):
        print("   %2d. %s" % (i, etiqueta))
        print("       %s" % url)
    print("")
    print("   Ojo: el tramo AAAA/MM de la URL es la fecha de subida y cambia")
    print("   cuando el IERIC refresca el archivo. Por eso el script definitivo")
    print("   va a resolver el link leyendo la pagina, nunca hardcodeandolo.")

    os.makedirs(DEST_DIR, exist_ok=True)
    resumen = []

    for i, (url, etiqueta) in enumerate(planillas[:MAX_ARCHIVOS], 1):
        print("")
        print("=" * 74)
        print(" [%d/%d] %s" % (i, min(len(planillas), MAX_ARCHIVOS), etiqueta))
        print("=" * 74)

        try:
            datos = _get(url)
        except Exception as e:
            print("   [ERROR] No se pudo bajar: %s" % e)
            resumen.append((etiqueta, "no se pudo bajar", "", ""))
            continue

        if len(datos) > MAX_BYTES:
            print("   [AVISO] Pesa %.1f MB, se saltea." % (len(datos) / 1048576.0))
            resumen.append((etiqueta, "demasiado grande", "", ""))
            continue

        print("   Tamaño : %s bytes" % "{:,}".format(len(datos)).replace(",", "."))
        print("   Formato: %s" % firma(datos))

        destino = os.path.join(DEST_DIR, os.path.basename(url.split("?")[0]))
        try:
            with open(destino, "wb") as f:
                f.write(datos)
            print("   Guardado en _diagnostico_ieric\\%s"
                  % os.path.basename(destino))
        except Exception as e:
            print("   [AVISO] No se pudo guardar: %s" % e)

        try:
            hojas, motor = leer(datos)
        except ImportError:
            print("   [ERROR] Falta xlrd. Instalalo con:  pip install xlrd")
            resumen.append((etiqueta, "falta xlrd", "", ""))
            continue
        except Exception as e:
            print("   [ERROR] No se pudo leer: %s" % e)
            resumen.append((etiqueta, "no se pudo leer", "", ""))
            continue

        print("   Motor  : %s" % motor)
        print("   Hojas  : %s" % ", ".join("'%s'" % h for h in hojas))

        total_filas = 0
        for nombre, filas in hojas.items():
            volcar_hoja(nombre, filas)
            total_filas += len(filas)

        resumen.append((etiqueta, motor, "%d hoja(s)" % len(hojas),
                        "%d filas" % total_filas))

    print("")
    print("=" * 74)
    print(" RESUMEN")
    print("=" * 74)
    for etiqueta, a, b, c in resumen:
        print("   %-42s %-12s %-10s %s" % (etiqueta[:42], a, b, c))
    print("")
    print(" Listo. No se modifico nada del tablero.")
    print(" El detalle completo quedo en log_ieric_cordoba.txt: decile a Claude")
    print(" que ya lo corriste y lo lee solo.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
