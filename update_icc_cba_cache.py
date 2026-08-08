#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_icc_cba_cache.py - Tablero Gestion Grupo Elyon
======================================================
Genera icc_cba_cache.js con el Indice del Costo de la Construccion de la
provincia de Cordoba (ICC-Cba), de la Direccion General de Estadistica y
Censos de Cordoba.

Que mide
--------
El costo de construir una vivienda social tipo de 50,25 m2 (cocina-comedor,
dos dormitorios y baño), con la metodologia vigente desde octubre de 2013.
Base 2012 = 100. Publica nivel general, tres rubros (materiales, mano de obra
y varios) y el valor del m2 en pesos.

Es el complemento local del CAC: el CAC es nacional y sobre un edificio tipo
de Buenos Aires; este es Cordoba y vivienda. Para obra en la provincia suele
ser la referencia que piden los comitentes.

De donde sale
-------------
Portal de datos abiertos de Cordoba (CKAN). El link de descarga redirige a un
S3 con firma que vence en una hora, asi que no sirve para leer en vivo desde
el navegador: hay que bajarlo desde aca y dejarlo cacheado.

    https://datosestadistica.cba.gov.ar/dataset/indice-de-costo-de-la-construccion

El CSV viene en latin-1, con punto y coma de separador, coma decimal y punto
de miles. Las primeras filas son titulos y la ultima es la firma de la fuente.

Salida: icc_cba_cache.js
    window.ICC_CBA_CACHE = {
      updated, source, hasta,
      serie: [[fecha, nivelGeneral, materiales, manoObra, varios, valorM2], ...]
    }

Uso:
    python update_icc_cba_cache.py
"""

import json
import os
import re
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "icc_cba_cache.js")
TIMEOUT = 40

DATASET = "indice-de-costo-de-la-construccion"
PACKAGE_API = ("https://datosestadistica.cba.gov.ar/api/3/action/package_show?id=" + DATASET)

# Link directo al recurso "Indice general y rubros - valor m2" (CSV).
CSV_URL = ("https://datosestadistica.cba.gov.ar/dataset/"
           "14329433-faaf-48fb-90a0-3c141288622d/resource/"
           "afbec0bb-f309-4c09-947a-cd38e6b67867/download/"
           "icc-cba-indice-general-y-rubros-valor-m2.csv")

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _get(url, binario=False):
    """GET con reintento sin verificar certificado."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/csv,application/json,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            crudo = resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            crudo = resp.read()
    return crudo if binario else crudo.decode("latin-1", "replace")


def url_del_recurso():
    """Resuelve el link del CSV por la API de CKAN. Si no responde, se usa el
    link directo: el id del recurso viene estable desde hace años, pero si
    algun dia lo cambian esto lo encuentra solo."""
    try:
        j = json.loads(_get(PACKAGE_API))
        for rec in j.get("result", {}).get("resources", []):
            fmt = (rec.get("format") or "").upper()
            desc = (rec.get("description") or "").lower()
            if fmt == "CSV" and "general" in desc and "rubro" in desc:
                print("   Recurso resuelto por la API de CKAN.")
                return rec["url"]
    except Exception:
        pass
    return CSV_URL


def _num(txt):
    """'4.583,74' -> 4583.74   |   '133,22' -> 133.22   |   '' -> None"""
    txt = (txt or "").strip().replace("%", "")
    if not txt:
        return None
    try:
        return float(txt.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _fecha(txt):
    """'oct-13' -> '2013-10-01'. Devuelve None si no es un periodo."""
    m = re.match(r"^\s*([a-zA-Z]{3})[\s\-/]*(\d{2,4})\s*$", txt or "")
    if not m:
        return None
    mes = MESES.get(m.group(1)[:3].lower())
    if not mes:
        return None
    anio = int(m.group(2))
    if anio < 100:
        anio += 2000
    return "%04d-%02d-01" % (anio, mes)


def parsear(csv_txt):
    """Columnas: Periodo ; NG ; Materiales ; Mano de obra ; Varios ;
                 4 columnas de variacion mensual ; Valor del m2"""
    filas = []
    for linea in csv_txt.splitlines():
        partes = linea.split(";")
        if len(partes) < 6:
            continue
        f = _fecha(partes[0])
        if not f:
            continue
        ng = _num(partes[1])
        if ng is None:
            continue
        filas.append([
            f, ng, _num(partes[2]), _num(partes[3]), _num(partes[4]),
            _num(partes[9]) if len(partes) > 9 else None,
        ])
    filas.sort(key=lambda r: r[0])
    return filas


def num(v):
    """2 decimales sin ceros al pedo. %g no sirve: corta a 6 cifras
    significativas y el valor del m2 ya pasa el millon de pesos."""
    if v is None:
        return "null"
    return ("%.2f" % v).rstrip("0").rstrip(".")


def main():
    print("Actualizando ICC de Cordoba (Estadistica y Censos de Cordoba)...")

    url = url_del_recurso()
    serie = parsear(_get(url))

    if len(serie) < 12:
        raise SystemExit("[ERROR] El CSV no trajo una serie usable (%d filas). "
                         "Se conserva el icc_cba_cache.js anterior." % len(serie))

    hasta = serie[-1][0][:7]
    fuente = "Direccion General de Estadistica y Censos de Cordoba"

    cuerpo = ",\n".join(
        '    ["%s",%s,%s,%s,%s,%s]' % (r[0], num(r[1]), num(r[2]), num(r[3]),
                                       num(r[4]), num(r[5]))
        for r in serie)

    js = (
        "/* ═══════════════════════════\n"
        "   icc_cba_cache.js  -  Grupo Elyon\n"
        "   Generado por update_icc_cba_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + " (datos abiertos, CKAN)\n"
        "   Vivienda social tipo de 50,25 m2 - base 2012 = 100\n"
        "   Columnas: fecha, nivel general, materiales, mano de obra, varios, valor m2\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.ICC_CBA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  serie: [\n" + cuerpo + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    u = serie[-1]
    print("\n[OK] icc_cba_cache.js")
    print("     %d meses, de %s a %s" % (len(serie), serie[0][0][:7], hasta))
    print("     Nivel general %s = %s  |  valor m2 $%s"
          % (hasta, ("%.2f" % u[1]), ("{:,.0f}".format(u[5] or 0).replace(",", "."))))


if __name__ == "__main__":
    main()
