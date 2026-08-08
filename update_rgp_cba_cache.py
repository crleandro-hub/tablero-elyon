#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_rgp_cba_cache.py - Tablero Gestion Grupo Elyon
======================================================
Genera rgp_cba_cache.js con los ingresos mensuales al Registro General de la
Provincia de Cordoba: transferencias de dominio e hipotecas inscriptas.

Para que sirve
--------------
Es el termometro de DEMANDA que al tablero le faltaba. Los permisos de
edificacion del INDEC miden oferta futura (lo que se va a construir); esto
mide operaciones cerradas: cuantas propiedades cambiaron de manos y cuantas
se compraron con hipoteca.

Ojo con la lectura: son documentos INGRESADOS al Registro, no escrituras
firmadas. Entre la escritura y la inscripcion hay semanas de desfasaje, y
diciembre siempre pega un salto por cierre de ejercicio.

De donde sale
-------------
Portal de datos abiertos de Cordoba (CKAN), dataset "Sector Inmobiliario".
Igual que el ICC: el link de descarga redirige a un S3 firmado que vence en
una hora, asi que no sirve para leer en vivo desde el navegador.

El CSV es un informe completo con 13 tablas apiladas, en latin-1 y con punto
y coma. Nos quedamos con dos: la 10 (transferencias mensuales) y la 11
(hipotecas mensuales). Se ubican buscando su fila de encabezado, no por
numero de linea, asi que si el INDEC de Cordoba agrega o saca tablas el
script sigue funcionando.

Salida: rgp_cba_cache.js
    window.RGP_CBA_CACHE = {
      updated, source, hasta,
      transferencias: [[fecha, cantidad], ...],
      hipotecas:      [[fecha, cantidad], ...]
    }

Uso:
    python update_rgp_cba_cache.py
"""

import json
import os
import re
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "rgp_cba_cache.js")
TIMEOUT = 40

DATASET = "sector-inmobiliario"
PACKAGE_API = "https://datosestadistica.cba.gov.ar/api/3/action/package_show?id=" + DATASET
CSV_URL = ("https://datosestadistica.cba.gov.ar/dataset/"
           "17ecb998-53c0-426e-8834-05610fd848d8/resource/"
           "0c2b854f-e35c-4438-87fd-96bc65404bba/download/"
           "registro-general-de-la-propiedad_-junio-2026.csv")

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _get(url):
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/csv,application/json,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.read().decode("latin-1", "replace")
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read().decode("latin-1", "replace")


def url_del_recurso():
    """El nombre del archivo lleva el mes adentro (…_-junio-2026.csv), asi que
    el link directo se pincha cuando publican un mes nuevo. Por eso se intenta
    primero resolverlo por la API de CKAN, que devuelve siempre el vigente."""
    try:
        j = json.loads(_get(PACKAGE_API))
        for rec in j.get("result", {}).get("resources", []):
            if (rec.get("format") or "").upper() == "CSV":
                print("   Recurso resuelto por la API de CKAN.")
                return rec["url"]
    except Exception:
        pass
    print("   [AVISO] La API de CKAN no respondio: se usa el link directo.")
    return CSV_URL


def _fecha(txt):
    """'jun-26' -> '2026-06-01'"""
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


def _entero(txt):
    """'5.878' -> 5878   |   '' -> None"""
    txt = (txt or "").strip()
    if not txt:
        return None
    try:
        return int(float(txt.replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def tabla_mensual(lineas, titulo):
    """Busca la fila de encabezado cuyo segundo campo sea `titulo` y devuelve
    las filas mensuales que siguen. Los meses futuros vienen vacios: se cortan."""
    inicio = None
    for i, l in enumerate(lineas):
        campos = [c.strip() for c in l.split(";")]
        if len(campos) > 1 and campos[0].lower().startswith("per") and campos[1] == titulo:
            inicio = i + 1
            break
    if inicio is None:
        return []

    filas = []
    for l in lineas[inicio:]:
        campos = l.split(";")
        f = _fecha(campos[0] if campos else "")
        if not f:
            break                       # se termino el bloque mensual
        v = _entero(campos[1] if len(campos) > 1 else "")
        if v is not None:
            filas.append([f, v])
    return filas


def main():
    print("Actualizando Registro General de la Propiedad de Cordoba...")

    lineas = _get(url_del_recurso()).splitlines()
    transf = tabla_mensual(lineas, "Transferencias")
    hipo = tabla_mensual(lineas, "Hipotecas")

    if len(transf) < 12 or len(hipo) < 12:
        raise SystemExit("[ERROR] No se encontraron las tablas mensuales "
                         "(transferencias: %d, hipotecas: %d). "
                         "Se conserva el rgp_cba_cache.js anterior."
                         % (len(transf), len(hipo)))

    hasta = max(transf[-1][0], hipo[-1][0])[:7]
    fuente = "Registro General de la Provincia de Cordoba"

    def bloque(filas):
        return ",\n".join('    ["%s",%d]' % (f, v) for f, v in filas)

    js = (
        "/* ═══════════════════════════\n"
        "   rgp_cba_cache.js  -  Grupo Elyon\n"
        "   Generado por update_rgp_cba_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + " (via datos abiertos de Cordoba)\n"
        "   Documentos INGRESADOS al Registro, no escrituras firmadas.\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.RGP_CBA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  transferencias: [\n" + bloque(transf) + "\n  ],\n"
        "  hipotecas: [\n" + bloque(hipo) + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("\n[OK] rgp_cba_cache.js")
    print("     Transferencias: %d meses, ultimo %s = %s"
          % (len(transf), transf[-1][0][:7], "{:,}".format(transf[-1][1]).replace(",", ".")))
    print("     Hipotecas     : %d meses, ultimo %s = %s"
          % (len(hipo), hipo[-1][0][:7], "{:,}".format(hipo[-1][1]).replace(",", ".")))


if __name__ == "__main__":
    main()
