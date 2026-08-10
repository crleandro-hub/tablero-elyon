#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_rofex_cache.py - Tablero Gestion Grupo Elyon
====================================================
Genera rofex_cache.js con la curva de dolar futuro de Matba Rofex (contratos
DLR), que es la misma que publica Rava Bursatil en su seccion de Futuros.

Para que sirve:
    El dolar futuro es el precio al que el mercado se compromete HOY a
    comprar o vender dolares en una fecha futura. Para nosotros es la
    referencia mas honesta de la devaluacion esperada: no es una encuesta
    como el REM, es plata puesta. Sirve para cotizar obra con componente
    importado y para decidir si conviene cubrirse.

    La tasa implicita (impliedRate) es lo que rinde en pesos hacer la
    "sintetica": comprar dolares hoy y venderlos a futuro. Comparada con la
    caucion y la TAMAR dice si conviene estar en pesos o en dolares.

Por que hace falta este script:
    Rava muestra los futuros dentro de un iframe de mercado.rava.com que arma
    JavaScript, asi que no hay HTML para leer. Y la API de Matba Rofex no
    habilita CORS. Python si puede: el tablero lee rofex_cache.js.

Fuente:
    apicem.matbarofex.com.ar - endpoint publico de precios de cierre.
    Se piden los ultimos dias habiles y se toma la rueda mas reciente.

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import json
import os
import ssl
import urllib.request as req
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "rofex_cache.js")

API = ("https://apicem.matbarofex.com.ar/api/v2/closing-prices"
       "?market=ROFX&product=DLR&from={desde}&to={hasta}&version=v2")

DIAS_ATRAS = 10          # margen por fines de semana y feriados
VENCIMIENTOS = 10        # cuantos contratos se guardan (el tablero muestra 8)
TIMEOUT = 30

MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
            "jul", "ago", "sep", "oct", "nov", "dic"]


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


def _etiqueta(symbol):
    """'DLR082026' -> ('2026-08', 'ago-26'). None si no es un futuro simple."""
    resto = symbol.replace("DLR", "").strip()
    # Las opciones vienen como 'DLR082026 Call 1520': no son futuros
    if len(resto) != 6 or not resto.isdigit():
        return None, None
    mes, anio = int(resto[:2]), int(resto[2:])
    if not 1 <= mes <= 12:
        return None, None
    return "%04d-%02d" % (anio, mes), "%s-%s" % (MESES_ES[mes - 1], str(anio)[2:])


def bajar_curva():
    """[{periodo, etiqueta, precio, varPct, tna}] ordenado por vencimiento."""
    hasta = datetime.now().date()
    desde = hasta - timedelta(days=DIAS_ATRAS)
    j = json.loads(_get(API.format(desde=desde.isoformat(), hasta=hasta.isoformat())))
    filas = j.get("data") or []
    if not filas:
        raise ValueError("la API no devolvio contratos")

    # Solo futuros (las opciones traen optionType) y de la rueda mas reciente
    futuros = [f for f in filas
               if not f.get("optionType") and f.get("symbol")]
    if not futuros:
        raise ValueError("la respuesta no traia futuros, solo opciones")

    rueda = max(str(f.get("dateTime") or "")[:10] for f in futuros)
    del_dia = [f for f in futuros if str(f.get("dateTime") or "")[:10] == rueda]

    out = []
    for f in del_dia:
        periodo, etiqueta = _etiqueta(str(f["symbol"]))
        if not periodo:
            continue
        # settlement es el precio de ajuste, que es el que usa el mercado para
        # marcar posiciones. close puede venir en 0 si el contrato no opero.
        precio = f.get("settlement") or f.get("close")
        if not precio:
            continue
        out.append({
            "periodo": periodo,
            "etiqueta": etiqueta,
            "precio": round(float(precio), 2),
            "varPct": round(float(f["changePercent"]), 2)
                      if f.get("changePercent") is not None else None,
            "tna": round(float(f["impliedRate"]), 2)
                   if f.get("impliedRate") is not None else None,
        })

    if not out:
        raise ValueError("no se pudo interpretar ningun contrato")
    out.sort(key=lambda d: d["periodo"])
    return rueda, out[:VENCIMIENTOS]


def main():
    print("Actualizando rofex_cache.js ...")

    try:
        rueda, curva = bajar_curva()
    except Exception as e:
        raise SystemExit("[ERROR] No se pudo obtener el dolar futuro (%s). "
                         "Se conserva el cache anterior." % e)

    print("[OK] Curva DLR de la rueda " + rueda
          + " (" + str(len(curva)) + " vencimientos)")

    def bloque(c):
        return (
            "    { periodo: \"%s\", etiqueta: \"%s\", precio: %s, varPct: %s, tna: %s }"
            % (c["periodo"], c["etiqueta"], c["precio"],
               c["varPct"] if c["varPct"] is not None else "null",
               c["tna"] if c["tna"] is not None else "null"))

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    js = (
        "/* -----------------------------------------------------------------\n"
        "   rofex_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + ts + "\n"
        "   Curva de dolar futuro (contratos DLR) de Matba Rofex.\n"
        "   precio = precio de ajuste (settlement) de la rueda\n"
        "   varPct = variacion % contra el ajuste anterior\n"
        "   tna    = tasa nominal anual implicita en el contrato\n"
        "----------------------------------------------------------------- */\n"
        "window.ROFEX_CACHE = {\n"
        '  rueda: "' + rueda + '",\n'
        "  curva: [\n" + ",\n".join(bloque(c) for c in curva) + "\n  ],\n"
        '  fuente: "Dólar futuro · Matba Rofex",\n'
        '  updated: "' + ts + '"\n'
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("[OK] rofex_cache.js  ->  " + " / ".join(
        c["etiqueta"] + " " + str(c["precio"]) for c in curva[:3]))


if __name__ == "__main__":
    main()
