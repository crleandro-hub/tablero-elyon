#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_rem_cache.py - Tablero Gestion Grupo Elyon
=================================================
Genera rem_cache.js con la inflacion esperada del REM (Relevamiento de
Expectativas de Mercado) que publica el BCRA todos los meses.

Fuente principal: la planilla oficial del BCRA
    https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/
    tablas-relevamiento-expectativas-mercado-<mes>-<anio>.xlsx
Se prueba el mes corriente y se va hacia atras hasta encontrar la ultima
publicada (el REM de un mes sale a principios del mes siguiente).

Se lee con xlsx_lite.py, que usa solo la libreria estandar: asi el script no
depende de que la PC tenga openpyxl ni pandas instalados.

Fuente de respaldo: bcra-rem-api, un servicio abierto que normaliza la misma
planilla. Puede quedar desactualizado, por eso va segundo.

Que guarda:
    m12     -> mediana esperada para los proximos 12 meses (var. % i.a.)
                 es el numero que el BCRA destaca como "inflacion esperada"
    anual   -> mediana esperada para diciembre del año en curso (var. % i.a.)
    mensual -> mediana del primer mes proyectado (var. % mensual)
    relev   -> mes del relevamiento, para mostrar la antiguedad del dato

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import json
import os
import ssl
import sys
import unicodedata
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from xlsx_lite import leer_hoja  # noqa: E402

CACHE_PATH = os.path.join(BASE_DIR, "rem_cache.js")

BCRA_URL = ("https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/"
            "informes/tablas-relevamiento-expectativas-mercado-{mes}-{anio}.xlsx")
MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_ALT = {"sep": "set"}          # el BCRA alterno esta abreviatura alguna vez
HOJA = "Cuadros de resultados"
MESES_ATRAS = 6                     # cuantos relevamientos hacia atras probar

API = "https://bcra-rem-api.facujallia.workers.dev/api"
TIMEOUT = 45


def _get(url, binario=False):
    r = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            data = resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            data = resp.read()
    return data if binario else json.loads(data)


def sin_tildes(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# ─────────────────────────────────────────────────────────────
#  Fuente 1: planilla oficial del BCRA
# ─────────────────────────────────────────────────────────────
def _bloque_ipc_general(filas):
    """Ubica el cuadro del IPC nivel general y devuelve (header, filas_datos)."""
    inicio = None
    for i, fila in enumerate(filas):
        texto = " ".join(sin_tildes(c) for c in fila if c is not None)
        if "ipc nivel general" in texto and "nucleo" not in texto:
            inicio = i
            break
    if inicio is None:
        return None, []

    # El encabezado es la primera fila siguiente que menciona "periodo"
    header = hdr_idx = None
    for j in range(inicio + 1, min(inicio + 8, len(filas))):
        texto = " ".join(sin_tildes(c) for c in filas[j] if c is not None)
        if "periodo" in texto or "referencia" in texto:
            header, hdr_idx = filas[j], j
            break
    if header is None:
        return None, []

    # Los datos van hasta el titulo del cuadro siguiente o una fila vacia doble
    datos, vacias = [], 0
    for k in range(hdr_idx + 1, len(filas)):
        fila = filas[k]
        texto = " ".join(sin_tildes(c) for c in fila if c is not None)
        if not texto:
            vacias += 1
            if vacias >= 2:
                break
            continue
        vacias = 0
        if "precios minoristas" in texto or "tasa de interes" in texto \
           or "tipo de cambio" in texto:
            break
        datos.append(fila)
    return header, datos


def _col_mediana(header):
    for i, c in enumerate(header):
        if c is not None and "mediana" in sin_tildes(c):
            return i
    return 2   # en la planilla del BCRA la mediana es la tercera columna


def parsear_xlsx(contenido, anio):
    filas = leer_hoja(contenido, HOJA)
    header, datos = _bloque_ipc_general(filas)
    if not datos:
        raise ValueError("No se encontro el cuadro de IPC nivel general")

    col = _col_mediana(header)

    def valor(fila):
        v = fila[col] if col < len(fila) else None
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return None

    res = {"m12": None, "anual": None, "mensual": None}
    for fila in datos:
        per = sin_tildes(fila[0]) if fila and fila[0] is not None else ""
        if not per:
            continue
        if "12 meses" in per and res["m12"] is None:
            res["m12"] = valor(fila)
        elif per in (str(anio), str(anio) + ".0", "%s.0" % anio) and res["anual"] is None:
            res["anual"] = valor(fila)
        elif per[:4].isdigit() and "-" in per and res["mensual"] is None:
            res["mensual"] = valor(fila)
    return res


def desde_bcra():
    """Prueba los ultimos relevamientos hasta encontrar uno publicado."""
    hoy = datetime.now()
    anio, mes = hoy.year, hoy.month

    for _ in range(MESES_ATRAS):
        # El REM de un mes se publica al mes siguiente: empezamos por el previo
        mes -= 1
        if mes == 0:
            mes, anio = 12, anio - 1

        abrevs = [MESES[mes - 1]]
        if MESES[mes - 1] in MESES_ALT:
            abrevs.append(MESES_ALT[MESES[mes - 1]])

        for ab in abrevs:
            url = BCRA_URL.format(mes=ab, anio=anio)
            try:
                contenido = _get(url, binario=True)
            except Exception:
                continue
            if not contenido[:2] == b"PK":     # no es un xlsx valido
                continue
            try:
                res = parsear_xlsx(contenido, datetime.now().year)
            except Exception as e:
                print("[AVISO] No se pudo parsear %s-%s: %s" % (ab, anio, e))
                continue
            if res["m12"] is None and res["anual"] is None:
                continue
            res["relev"] = "%04d-%02d" % (anio, mes)
            res["fuente"] = "BCRA (planilla oficial)"
            print("[OK] REM %s-%s desde la planilla del BCRA" % (ab, anio))
            return res
    return None


# ─────────────────────────────────────────────────────────────
#  Fuente 2: API abierta que normaliza la misma planilla
# ─────────────────────────────────────────────────────────────
def desde_api():
    try:
        datos = (_get(API + "/ipc_general") or {}).get("datos") or []
    except Exception as e:
        print("[AVISO] API REM: " + str(e))
        return None
    if not datos:
        return None

    try:
        meta = _get(API + "/metadata") or {}
    except Exception:
        meta = {}

    anio = datetime.now().year

    def mediana(pred):
        for f in datos:
            per = str(f.get("período", f.get("periodo", "")))
            if pred(per) and f.get("mediana") is not None:
                return round(float(f["mediana"]), 4)
        return None

    res = {
        "m12":     mediana(lambda p: "12 meses" in p.lower()),
        "anual":   mediana(lambda p: p == str(anio)),
        "mensual": mediana(lambda p: p[:4].isdigit() and len(p) >= 7),
        "relev":   meta.get("periodo"),
        "fuente":  "bcra-rem-api",
    }
    if res["m12"] is None and res["anual"] is None:
        return None
    print("[OK] REM desde la API abierta (relevamiento %s)" % res["relev"])
    return res


def main():
    print("Actualizando rem_cache.js ...")

    res = desde_bcra() or desde_api()
    if not res:
        raise SystemExit("[ERROR] No se pudo obtener el REM. "
                         "Se conserva el cache anterior.")

    anio = datetime.now().year

    def js(v):
        if v is None:
            return "null"
        return '"%s"' % v if isinstance(v, str) else str(v)

    contenido = (
        "/* -----------------------------------------------------------------\n"
        "   rem_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n"
        "   Fuente: " + res["fuente"] + "\n"
        "   m12   = var. % i.a. esperada para los proximos 12 meses\n"
        "   anual = var. % i.a. esperada a diciembre del año en curso\n"
        "----------------------------------------------------------------- */\n"
        "window.REM_CACHE = {\n"
        "  m12: " + js(res["m12"]) + ",\n"
        "  anual: " + js(res["anual"]) + ",\n"
        "  mensual: " + js(res["mensual"]) + ",\n"
        "  relev: " + js(res["relev"]) + ",\n"
        "  anio: " + str(anio) + ",\n"
        "  fuente: " + js(res["fuente"]) + ",\n"
        '  updated: "' + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + '"\n'
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(contenido)

    print("[OK] rem_cache.js  ->  relevamiento %s  |  prox. 12 meses: %s%%"
          "  |  dic-%s: %s%%"
          % (res["relev"], res["m12"], str(anio)[2:], res["anual"]))


if __name__ == "__main__":
    main()
