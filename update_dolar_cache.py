#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_dolar_cache.py - Tablero Gestion Grupo Elyon
====================================================
Genera dolar_cache.js con la ultima cotizacion de cada tipo de cambio:
oficial, blue, MEP, CCL, cripto, mayorista y los dos euros.

Por que hace falta si el tablero ya las pide en vivo:
    El navegador consulta dolarapi.com en cada carga, asi que en condiciones
    normales muestra el valor del momento y este cache ni se usa. El problema
    es cuando la API no responde: sin respaldo las tarjetas quedan en N/D y
    el tablero no muestra NINGUN numero, que es peor que mostrar el ultimo
    conocido con su fecha. Todos los demas indicadores tienen ese respaldo;
    el tipo de cambio era el unico que no.

    El orden de precedencia en el tablero es: valor en vivo si lo consigue,
    y si no este cache, siempre aclarando de cuando es el dato.

Fuentes:
    dolarapi.com    - los siete dolares
    bluelytics      - euro oficial y euro blue (dolarapi no publica euro blue)

Ejecutar en cada corrida de la tarea programada.
"""

import json
import os
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "dolar_cache.js")

API_DOLAR = "https://dolarapi.com/v1/dolares"
API_EURO = "https://api.bluelytics.com.ar/v2/latest"
TIMEOUT = 30

# casa en dolarapi -> clave en el cache (la misma que usa el tablero)
CASAS = {
    "oficial": "oficial",
    "blue": "blue",
    "bolsa": "mep",
    "contadoconliqui": "ccl",
    "cripto": "cripto",
    "mayorista": "mayorista",
}


def _get(url):
    """GET con reintento sin verificacion SSL (algunas instalaciones Windows
    no traen la cadena de certificados completa)."""
    r = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
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


def dolares():
    """{clave: {compra, venta, fecha}} de dolarapi."""
    filas = json.loads(_get(API_DOLAR))
    out = {}
    for f in filas:
        k = CASAS.get(str(f.get("casa") or "").lower())
        if not k:
            continue
        try:
            out[k] = {
                "compra": round(float(f["compra"]), 2),
                "venta": round(float(f["venta"]), 2),
                "fecha": str(f.get("fechaActualizacion") or "")[:10],
            }
        except (TypeError, ValueError, KeyError):
            continue
    if not out:
        raise ValueError("dolarapi no devolvio cotizaciones utilizables")
    return out


def euros():
    """{euroOficial, euroBlue} de bluelytics. Devuelve {} si no responde."""
    try:
        j = json.loads(_get(API_EURO))
    except Exception as e:
        print("[AVISO] Euro (bluelytics): " + str(e))
        return {}

    fecha = str(j.get("last_update") or "")[:10]
    out = {}
    for origen, destino in (("oficial_euro", "euroOficial"), ("blue_euro", "euroBlue")):
        d = j.get(origen)
        if not d:
            continue
        try:
            out[destino] = {
                "compra": round(float(d["value_buy"]), 2),
                "venta": round(float(d["value_sell"]), 2),
                "fecha": fecha,
            }
        except (TypeError, ValueError, KeyError):
            continue
    return out


def main():
    print("Actualizando dolar_cache.js ...")

    try:
        datos = dolares()
    except Exception as e:
        raise SystemExit("[ERROR] No se pudo obtener el tipo de cambio (%s). "
                         "Se conserva el cache anterior." % e)

    datos.update(euros())

    faltan = sorted(set(CASAS.values()) - set(datos))
    if faltan:
        print("[AVISO] Sin dato para: " + ", ".join(faltan))

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    filas = ",\n".join(
        '  %s: { compra: %s, venta: %s, fecha: "%s" }'
        % (k, v["compra"], v["venta"], v["fecha"])
        for k, v in sorted(datos.items()))

    js = (
        "/* -----------------------------------------------------------------\n"
        "   dolar_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + ts + "\n"
        "   Respaldo del tipo de cambio. El tablero pide los valores EN VIVO a\n"
        "   dolarapi.com en cada carga; esto se usa solo si esa consulta falla,\n"
        "   para no dejar las tarjetas en N/D.\n"
        "   fecha = corte de la cotizacion segun la fuente, no de la descarga\n"
        "----------------------------------------------------------------- */\n"
        "window.DOLAR_CACHE = {\n" + filas + ",\n"
        '  fuente: "dolarapi.com · bluelytics",\n'
        '  updated: "' + ts + '"\n'
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("[OK] dolar_cache.js  ->  " + " / ".join(
        "%s %s" % (k, datos[k]["venta"]) for k in sorted(datos))[:200])


if __name__ == "__main__":
    main()
