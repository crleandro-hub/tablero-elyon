#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_ceduc_cache.py - Tablero Gestion Grupo Elyon
====================================================
Genera ceduc_cache.js con el Indice de Ventas de Inmuebles en Cordoba, que
elabora Economic Trends S.A. para la CEDUC.

Que mide
--------
Volumen de ventas, NO precios. Base octubre 2011 = 100, en unidades
homogeneas de metros cuadrados. Lo reportan mes a mes las empresas socias de
la camara, y cuenta operaciones efectivamente realizadas esten escrituradas o
no: no tiene el rezago de los indices basados en escrituras.

Es el mejor termometro de demanda del mercado en el que trabaja Elyon. Se
abre en no financiadas y financiadas, y dentro de cada una en departamentos y
casas, cocheras y lotes.

De donde sale
-------------
Del EXCEL que manda la camara junto al informe:
    "CEDUC - Indice de ventas de inmuebles AAAA MM version CEDUC.xlsx"
Se deja en la carpeta ceduc y el script toma el mas reciente.

Hasta octubre de 2026 esto se hacia a mano: el PDF del informe viene
escaneado, sin capa de texto, asi que las tablas se transcribian leyendo las
imagenes. El Excel tiene exactamente los mismos numeros (se comparo mes a mes:
las 195 filas de la serie original coinciden sin una sola diferencia) y ademas
trae la serie desestacionalizada reestimada, que en el PDF obligaba a congelar
la historia vieja porque transcribir 180 filas a ojo metia mas error del que
corregia.

Si en la carpeta solo hay un .txt (el formato viejo, pegado del PDF), el
script lo lee igual. El Excel manda si estan los dos.

Un detalle que importa
----------------------
El cuadro de sintesis del informe dice "Series desestacionalizadas" en el
encabezado, pero el interanual esta calculado sobre la serie ORIGINAL. Solo
la comparacion de los ultimos 3 meses contra los 3 previos usa la ajustada.
Por eso el cache guarda las dos series y el tablero calcula cada variacion
con la que corresponde.

El control
----------
El Excel trae al pie una fila "% a/a" con la variacion interanual de cada
columna, calculada por Economic Trends. El script la usa para controlarse:
recalcula el interanual del ultimo mes sobre lo que acaba de leer y lo compara
contra esa fila. Si no coincide, no pisa el cache. Es un control que no hay
que mantener: viaja dentro del archivo.

Salida: ceduc_cache.js
    window.CEDUC_CACHE = {
      updated, source, hasta, informe,
      original:  [[fecha, nf_dep, nf_coch, nf_lot, nf_idx,
                          f_dep,  f_coch,  f_lot,  f_idx,
                          t_dep,  t_coch,  t_lot,  t_idx], ...]
      desest:    [[...igual...], ...]
    }

Uso:
    python update_ceduc_cache.py
"""

import os
import re
import sys
import glob
import traceback
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE_DIR, "ceduc")
CACHE_PATH = os.path.join(BASE_DIR, "ceduc_cache.js")

sys.path.insert(0, BASE_DIR)
from xlsx_lite import leer_hoja           # noqa: E402

MESES = {"jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4,
         "may": 5, "jun": 6, "jul": 7, "aug": 8, "ago": 8,
         "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12, "dec": 12}

COLUMNAS = 12                 # las tres aperturas por tres tipologias + indice
TOLERANCIA_AA = 0.2           # puntos porcentuales


def a_fecha(mes_txt, anio_txt):
    m = MESES.get(mes_txt.lower())
    if not m:
        return None
    return "%04d-%02d-01" % (2000 + int(anio_txt), m)


# ─────────────────────────────────────────────────────────────
#  Lectura del Excel
# ─────────────────────────────────────────────────────────────
def _celda(fila, i):
    return fila[i] if i < len(fila) else None


def _ubicar_bloques(filas):
    """{'original': (col_mes, col_primera), 'desest': (...)}.

    Las columnas no se clavan a mano: se buscan por el titulo del bloque, que
    esta en la segunda fila de la planilla, y la columna "Mes" es la anterior.
    Asi un bloque nuevo intercalado no corre todo lo demas."""
    bloques = {}
    for fila in filas[:6]:
        for i, celda in enumerate(fila):
            if not isinstance(celda, str):
                continue
            txt = celda.strip().lower()
            if txt.startswith("series originales"):
                bloques["original"] = (i - 1, i)
            elif txt.startswith("series desestacionalizadas"):
                bloques["desest"] = (i - 1, i)
    return bloques


FILA_MES = re.compile(r"^([A-Za-z]{3})-(\d{2})$")


def _tabla(filas, col_mes, col0):
    """[[fecha, v1..v12], ...] de un bloque, ordenada por fecha."""
    out = []
    for fila in filas:
        etiqueta = _celda(fila, col_mes)
        if not isinstance(etiqueta, str):
            continue
        m = FILA_MES.match(etiqueta.strip())
        if not m:
            continue
        fecha = a_fecha(m.group(1), m.group(2))
        if not fecha:
            continue
        vals = []
        for i in range(col0, col0 + COLUMNAS):
            v = _celda(fila, i)
            vals.append(round(float(v), 2) if isinstance(v, (int, float)) else None)
        if all(v is None for v in vals):
            continue
        out.append([fecha] + vals)
    out.sort(key=lambda r: r[0])
    return out


def _fila_aa(filas, col_mes, col0):
    """La fila '% a/a' que el propio informe trae al pie del bloque."""
    for fila in filas:
        etiqueta = _celda(fila, col_mes)
        if isinstance(etiqueta, str) and "a/a" in etiqueta.lower():
            return [float(_celda(fila, i)) if isinstance(_celda(fila, i), (int, float))
                    else None for i in range(col0, col0 + COLUMNAS)]
    return None


def _controlar(tabla, aa):
    """Recalcula el interanual del ultimo mes y lo compara con la fila '% a/a'.

    Devuelve (cuantas columnas se controlaron, lista de fallas)."""
    if not aa or len(tabla) < 13:
        return 0, []
    ult = tabla[-1]
    a, m = int(ult[0][:4]), int(ult[0][5:7])
    previo = next((r for r in tabla if r[0][:7] == "%04d-%02d" % (a - 1, m)), None)
    if not previo:
        return 0, []

    controladas, fallas = 0, []
    for i in range(COLUMNAS):
        ahora, antes, esperado = ult[i + 1], previo[i + 1], aa[i]
        if ahora is None or not antes or esperado is None:
            continue
        calculado = (ahora / antes - 1) * 100
        controladas += 1
        if abs(calculado - esperado) > TOLERANCIA_AA:
            fallas.append("columna %d: calculado %+.1f%%, el informe dice %+.1f%%"
                          % (i + 1, calculado, esperado))
    return controladas, fallas


def leer_excel(ruta):
    filas = leer_hoja(ruta)
    bloques = _ubicar_bloques(filas)
    if "original" not in bloques:
        raise SystemExit(
            "[ERROR] No se encontro el bloque 'Series originales' en la planilla.\n"
            "        Puede que la camara haya cambiado el formato del Excel.")

    tablas = {}
    for clave, (col_mes, col0) in bloques.items():
        tablas[clave] = _tabla(filas, col_mes, col0)
    tablas.setdefault("desest", [])

    col_mes, col0 = bloques["original"]
    controladas, fallas = _controlar(tablas["original"], _fila_aa(filas, col_mes, col0))
    if fallas:
        print("\n[ERROR] El control contra la fila '%% a/a' del informe fallo en "
              "%d columna(s):" % len(fallas))
        for f in fallas:
            print("        " + f)
        raise SystemExit("Se conserva el ceduc_cache.js anterior.")
    if controladas:
        print("   Control: las %d columnas del interanual de %s coinciden con la "
              "fila '%% a/a' del informe." % (controladas, tablas["original"][-1][0][:7]))
    else:
        print("   [AVISO] La planilla no trae la fila '% a/a': se publica sin ese control.")
    return tablas


# ─────────────────────────────────────────────────────────────
#  Lectura del .txt (formato viejo, pegado del PDF)
# ─────────────────────────────────────────────────────────────
FILA_TXT = re.compile(r"^\s*([A-Za-z]{3})-(\d{2})\s+(.+?)\s*$")


def _num_txt(tok):
    if tok in ("-", "", "n/d", "N/D"):
        return None
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


def leer_txt(ruta):
    texto = open(ruta, encoding="utf-8", errors="replace").read()
    tablas = {"original": [], "desest": []}
    actual = None
    for linea in texto.splitlines():
        bajo = linea.lower()
        if bajo.startswith("series originales"):
            actual = "original"
            continue
        if bajo.startswith("series desestacionalizadas"):
            actual = "desest"
            continue
        if actual is None:
            continue
        m = FILA_TXT.match(linea)
        if not m:
            continue
        fecha = a_fecha(m.group(1), m.group(2))
        if not fecha:
            continue
        vals = [_num_txt(t) for t in m.group(3).split()]
        vals = (vals + [None] * COLUMNAS)[:COLUMNAS]
        if all(v is None for v in vals):
            continue
        tablas[actual].append([fecha] + vals)

    for k in tablas:
        tablas[k].sort(key=lambda r: r[0])
        unicas, vistos = [], set()
        for r in reversed(tablas[k]):
            if r[0] not in vistos:
                vistos.add(r[0])
                unicas.append(r)
        tablas[k] = list(reversed(unicas))
    return tablas


def _utiles(patron):
    """Los archivos de la carpeta que son informes de verdad.

    Se saltean dos cosas que aparecen solas y envenenarian la eleccion:
      - "~$nombre.xlsx": el archivo de bloqueo que deja Excel mientras la
        planilla esta ABIERTA. Como la ~ ordena despues de las letras, era
        justo el que ganaba el sorted() y el script se caia tratando de
        parsear 165 bytes. Pasa cada vez que se corre la tarea con el Excel
        abierto en pantalla, que es lo mas probable el dia que lo cargas.
      - las copias en conflicto de Dropbox, que son un duplicado viejo o
        vacio con el mismo contenido a medias."""
    salida = []
    for ruta in glob.glob(os.path.join(CARPETA, patron)):
        nombre = os.path.basename(ruta).lower()
        if nombre.startswith("~$"):
            continue
        if "conflicto" in nombre or "conflicted copy" in nombre:
            continue
        if os.path.getsize(ruta) < 1024:
            continue
        salida.append(ruta)
    return sorted(salida)


def ultimo_informe():
    """El archivo mas reciente de la carpeta. El Excel manda sobre el .txt."""
    xlsx = _utiles("*.xlsx")
    if xlsx:
        return xlsx[-1], "xlsx"
    txt = _utiles("*.txt")
    if txt:
        return txt[-1], "txt"
    raise SystemExit(
        "[ERROR] No hay ningun informe en la carpeta ceduc.\n"
        "        Deja ahi el Excel que manda la camara:\n"
        "        'CEDUC - Indice de ventas de inmuebles AAAA MM version CEDUC.xlsx'")


def num(v):
    if v is None:
        return "null"
    return ("%.2f" % v).rstrip("0").rstrip(".")


def main():
    print("Actualizando el indice de ventas CEDUC...")

    ruta, tipo = ultimo_informe()
    print("   Archivo: %s (%s)" % (os.path.basename(ruta), tipo))

    tablas = leer_excel(ruta) if tipo == "xlsx" else leer_txt(ruta)
    orig, des = tablas["original"], tablas["desest"]

    if len(orig) < 24:
        print("\n[ERROR] La serie original salio con %d meses, muy poco." % len(orig))
        raise SystemExit("Se conserva el ceduc_cache.js anterior.")

    print("   Original       : %d meses (%s a %s)"
          % (len(orig), orig[0][0][:7], orig[-1][0][:7]))
    if des:
        print("   Desestacionaliz: %d meses (%s a %s)"
              % (len(des), des[0][0][:7], des[-1][0][:7]))

    hasta = orig[-1][0][:7]

    def bloque(f):
        return ",\n".join('    ["%s",%s]' % (r[0], ",".join(num(v) for v in r[1:]))
                          for r in f)

    fuente = "CEDUC - Economic Trends S.A."
    js = (
        "/* ═══════════════════════════\n"
        "   ceduc_cache.js  -  Grupo Elyon\n"
        "   Generado por update_ceduc_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + "\n"
        "   Indice de Ventas de Inmuebles en Cordoba, base oct-2011 = 100.\n"
        "   Mide VOLUMEN de ventas en unidades homogeneas de m2, no precios.\n"
        "   Columnas: fecha | no financiado: deptos, cocheras, lotes, indice\n"
        "                   | financiado:    deptos, cocheras, lotes, indice\n"
        "                   | total:         deptos, cocheras, lotes, indice\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.CEDUC_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        '  informe: "' + os.path.basename(ruta) + '",\n'
        "  original: [\n" + bloque(orig) + "\n  ],\n"
        "  desest: [\n" + bloque(des) + "\n  ]\n"
        "};\n"
    )

    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(js)
    os.replace(tmp, CACHE_PATH)

    print("\n[OK] ceduc_cache.js")
    print("     %d meses de serie original, hasta %s" % (len(orig), hasta))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print("\n[ERROR] El script se cayo con una excepcion inesperada.")
        print("        Se conserva el ceduc_cache.js anterior.\n")
        traceback.print_exc()
        sys.exit(1)
