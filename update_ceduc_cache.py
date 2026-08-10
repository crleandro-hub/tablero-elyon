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
Del informe mensual en PDF. La pagina publica de CEDUC va un año atrasada
(al 8/8/2026 el ultimo publicado era agosto 2025), asi que los informes
recientes se consiguen por la camara.

Como el PDF no se puede automatizar desde aca, el circuito es:

    1. Abrir el PDF, Ctrl+A, Ctrl+C
    2. Pegarlo en el Bloc de notas
    3. Guardarlo en la carpeta ceduc como  ceduc-AAAA-MM.txt
    4. Correr este script

El script toma SIEMPRE el archivo mas reciente de la carpeta. Como cada
informe trae la serie completa desde 2010, con el ultimo alcanza: no hace
falta conservar los anteriores, aunque tampoco molestan.

Un detalle que importa
----------------------
El cuadro de sintesis del informe dice "Series desestacionalizadas" en el
encabezado, pero el interanual esta calculado sobre la serie ORIGINAL. Solo
la comparacion de los ultimos 3 meses contra los 3 previos usa la ajustada.
Por eso el cache guarda las dos series y el tablero calcula cada variacion
con la que corresponde.

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

MESES = {"jan": 1, "ene": 1, "feb": 2, "mar": 3, "apr": 4, "abr": 4,
         "may": 5, "jun": 6, "jul": 7, "aug": 8, "ago": 8,
         "sep": 9, "set": 9, "oct": 10, "nov": 11, "dec": 12, "dic": 12}

# Control: lo que dice el cuadro de sintesis del informe de junio 2026.
# Si el parseo no lo reproduce, algo se rompio y no se pisa el cache.
CONTROL = {"mes": "2026-06", "indice_total_original": 17.24, "ia_total": -39.1}

# Una fila de datos: mes en ingles abreviado, guion, año de dos digitos,
# y despues hasta doce numeros o guiones (los primeros años no tienen
# apertura por tipologia y el informe los deja en blanco con un "-").
FILA = re.compile(r"^\s*([A-Za-z]{3})-(\d{2})\s+(.+?)\s*$")


def a_fecha(mes_txt, anio_txt):
    m = MESES.get(mes_txt.lower())
    if not m:
        return None
    a = int(anio_txt)
    # La serie arranca en 2010: dos digitos siempre son 20xx
    return "%04d-%02d-01" % (2000 + a, m)


def a_num(tok):
    if tok in ("-", "", "n/d", "N/D"):
        return None
    try:
        return float(tok.replace(",", "."))
    except ValueError:
        return None


def parsear(texto):
    """Devuelve {'original': [...], 'desest': [...]}.

    Se recorre el texto de arriba abajo cambiando de tabla cuando aparece el
    titulo de cada seccion. No se asume en que linea empieza cada una."""
    tablas = {"original": [], "desest": []}
    actual = None

    for linea in texto.splitlines():
        bajo = linea.lower()

        if "series originales" in bajo:
            actual = "original"
            continue
        if "series desestacionalizadas" in bajo:
            actual = "desest"
            continue
        if actual is None:
            continue

        m = FILA.match(linea)
        if not m:
            continue
        fecha = a_fecha(m.group(1), m.group(2))
        if not fecha:
            continue

        vals = [a_num(t) for t in m.group(3).split()]
        if len(vals) < 12:
            vals += [None] * (12 - len(vals))
        vals = vals[:12]
        if all(v is None for v in vals):
            continue
        tablas[actual].append([fecha] + vals)

    for k in tablas:
        tablas[k].sort(key=lambda r: r[0])
        # Si un informe repitiera un mes, gana el ultimo que aparece
        unicas, vistos = [], set()
        for r in reversed(tablas[k]):
            if r[0] not in vistos:
                vistos.add(r[0])
                unicas.append(r)
        tablas[k] = list(reversed(unicas))
    return tablas


def ultimo_txt():
    archivos = sorted(glob.glob(os.path.join(CARPETA, "*.txt")))
    if not archivos:
        raise SystemExit(
            "[ERROR] No hay ningun .txt en la carpeta ceduc.\n"
            "        Abri el PDF del informe, Ctrl+A, Ctrl+C, pegalo en el\n"
            "        Bloc de notas y guardalo ahi como ceduc-AAAA-MM.txt")
    return archivos[-1]


def num(v):
    if v is None:
        return "null"
    return ("%.2f" % v).rstrip("0").rstrip(".")


def main():
    print("Actualizando el indice de ventas CEDUC...")

    ruta = ultimo_txt()
    print("   Archivo: %s" % os.path.basename(ruta))

    texto = open(ruta, encoding="utf-8", errors="replace").read()
    tablas = parsear(texto)

    orig, des = tablas["original"], tablas["desest"]
    if len(orig) < 24:
        print("\n[ERROR] La serie original salio con %d meses, muy poco." % len(orig))
        print("        Puede que el pegado haya perdido las tablas.")
        raise SystemExit("Se conserva el ceduc_cache.js anterior.")

    print("   Original       : %d meses (%s a %s)"
          % (len(orig), orig[0][0][:7], orig[-1][0][:7]))
    print("   Desestacionaliz: %d meses (%s a %s)"
          % (len(des), des[0][0][:7], des[-1][0][:7]) if des else "   Desestacionaliz: —")

    hasta = orig[-1][0][:7]

    # ── Control contra el cuadro de sintesis ──
    mapa = {r[0][:7]: r for r in orig}
    ctrl = mapa.get(CONTROL["mes"])
    if ctrl:
        idx = ctrl[12]                      # ultima columna = indice total
        esperado = CONTROL["indice_total_original"]
        if idx is None or abs(idx - esperado) > 0.05:
            print("\n[ERROR] Control fallado: junio 2026 deberia dar un indice total de "
                  "%.2f y dio %s." % (esperado, idx))
            print("        Revisa que el pegado tenga las columnas completas.")
            raise SystemExit("Se conserva el ceduc_cache.js anterior.")
        prev = mapa.get("2025-06")
        if prev and prev[12]:
            ia = (idx / prev[12] - 1) * 100
            print("   Control: jun-2026 indice %.2f, %+.1f%% i.a. (informe: %+.1f%%) -> %s"
                  % (idx, ia, CONTROL["ia_total"],
                     "OK" if abs(ia - CONTROL["ia_total"]) <= 0.2 else "NO COINCIDE"))
    else:
        print("   [AVISO] El mes de control no esta en la serie; se publica sin verificar.")

    def bloque(filas):
        return ",\n".join(
            "    [\"%s\",%s]" % (r[0], ",".join(num(v) for v in r[1:]))
            for r in filas)

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

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

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
