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
import re
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

BCRA_PORTADA = "https://www.bcra.gob.ar/relevamiento-expectativas-mercado-rem/"
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
    # Encabezados de navegador: el sitio del BCRA rechaza pedidos "pelados"
    r = req.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet,*/*;q=0.8"),
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Referer": "https://www.bcra.gob.ar/",
        "Connection": "close",
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


def _mes_de_url(url):
    """'...-jul-2026.xlsx' -> '2026-07'."""
    m = re.search(r"-([a-z]{3})-(\d{4})\.xlsx", url, re.I)
    if not m:
        return None
    ab = m.group(1).lower()
    if ab == "set":
        ab = "sep"
    if ab not in MESES:
        return None
    return "%s-%02d" % (m.group(2), MESES.index(ab) + 1)


def _intentar_xlsx(url, etiqueta):
    """Baja y parsea una planilla. Devuelve el dict de resultados o None."""
    try:
        contenido = _get(url, binario=True)
    except Exception as e:
        print("   [%s] no se pudo bajar: %s" % (etiqueta, e))
        return None
    if contenido[:2] != b"PK":
        print("   [%s] la respuesta no es un xlsx (%d bytes)" % (etiqueta, len(contenido)))
        return None
    try:
        res = parsear_xlsx(contenido, datetime.now().year)
    except Exception as e:
        print("   [%s] no se pudo parsear: %s" % (etiqueta, e))
        return None
    if res["m12"] is None and res["anual"] is None:
        print("   [%s] la planilla no trae medianas de IPC" % etiqueta)
        return None
    return res


def desde_portada():
    """Lee el link a la planilla desde la pagina del REM.

    Es el camino mas confiable: no depende de adivinar el nombre del archivo
    ni de que el BCRA mantenga la convencion mes-anio."""
    try:
        html = _get(BCRA_PORTADA, binario=True).decode("utf-8", "replace")
    except Exception as e:
        print("   [portada] no se pudo abrir la pagina del REM: %s" % e)
        return None

    links = re.findall(
        r'href="([^"]*tablas-relevamiento-expectativas-mercado[^"]*\.xlsx)"',
        html, re.I)
    if not links:
        print("   [portada] la pagina no lista ninguna planilla .xlsx")
        return None

    for href in links[:3]:
        url = href if href.startswith("http") else "https://www.bcra.gob.ar" + href
        res = _intentar_xlsx(url, "portada")
        if res:
            res["relev"] = _mes_de_url(url)
            res["fuente"] = "BCRA (planilla oficial)"
            print("[OK] REM desde la planilla enlazada en la pagina del BCRA (%s)"
                  % res["relev"])
            return res
    return None


def desde_bcra():
    """Prueba los ultimos relevamientos hasta encontrar uno publicado."""
    print("Buscando la planilla del REM en bcra.gob.ar ...")

    res = desde_portada()
    if res:
        return res

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
            except Exception as e:
                print("   [%s-%s] no se pudo bajar: %s" % (ab, anio, e))
                continue
            if contenido[:2] != b"PK":     # no es un xlsx valido
                print("   [%s-%s] la respuesta no es un xlsx (%d bytes)"
                      % (ab, anio, len(contenido)))
                continue
            try:
                res = parsear_xlsx(contenido, datetime.now().year)
            except Exception as e:
                print("   [%s-%s] no se pudo parsear: %s" % (ab, anio, e))
                continue
            if res["m12"] is None and res["anual"] is None:
                print("   [%s-%s] la planilla no trae medianas de IPC" % (ab, anio))
                continue
            res["relev"] = "%04d-%02d" % (anio, mes)
            res["fuente"] = "BCRA (planilla oficial)"
            print("[OK] REM %s-%s desde la planilla del BCRA" % (ab, anio))
            return res
    return None


# ─────────────────────────────────────────────────────────────
#  Fuente 2: API abierta que normaliza la misma planilla
# ─────────────────────────────────────────────────────────────
def _relev_desde_referencia(datos):
    """Deduce el mes del relevamiento de la fila 'proximos 12 meses'.

    Su columna 'referencia' dice, por ejemplo, 'var. % i.a.; abr-27': el
    horizonte es 12 meses despues del relevamiento, asi que restando un año
    sale abr-26. Se usa para no gastar un segundo pedido en /metadata, que el
    servicio rechaza por limitar a 1 llamada por minuto y por IP."""
    abrev = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
             "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}
    for f in datos:
        per = sin_tildes(f.get("período", f.get("periodo", "")))
        if "12 meses" not in per:
            continue
        ref = sin_tildes(f.get("referencia", ""))
        m = re.search(r"([a-z]{3})-(\d{2})", ref)
        if m and m.group(1) in abrev:
            return "%04d-%02d" % (2000 + int(m.group(2)) - 1, abrev[m.group(1)])
    return None


def desde_api():
    print("Probando la API abierta de respaldo ...")
    try:
        datos = (_get(API + "/ipc_general") or {}).get("datos") or []
    except Exception as e:
        print("   API REM: " + str(e))
        return None
    if not datos:
        return None

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
        "relev":   _relev_desde_referencia(datos),
        "fuente":  "bcra-rem-api",
    }
    if res["m12"] is None and res["anual"] is None:
        return None
    print("[OK] REM desde la API abierta (relevamiento %s)" % res["relev"])
    return res


def relev_actual():
    """Relevamiento que ya esta guardado en rem_cache.js, si lo hay."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            m = re.search(r'relev:\s*"(\d{4}-\d{2})"', f.read())
        return m.group(1) if m else None
    except Exception:
        return None


def main():
    print("Actualizando rem_cache.js ...")

    res = desde_bcra() or desde_api()
    if not res:
        raise SystemExit("[ERROR] No se pudo obtener el REM. "
                         "Se conserva el cache anterior.")

    # No pisar un relevamiento nuevo con uno mas viejo. La API de respaldo
    # suele quedar atrasada varios meses; si el cache ya tiene algo mas
    # reciente, se lo deja como esta.
    previo = relev_actual()
    if previo and res.get("relev") and res["relev"] < previo:
        print("[SIN CAMBIOS] El cache ya tiene el relevamiento %s, mas nuevo "
              "que el %s que devolvio %s." % (previo, res["relev"], res["fuente"]))
        return

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
