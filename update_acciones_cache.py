#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_acciones_cache.py - Tablero Gestion Grupo Elyon
=======================================================
Genera acciones_cache.js con las 3 acciones que mas subieron y las 3 que mas
bajaron del PANEL LIDER del Merval en la rueda.

Por que solo el panel lider:
    Es donde esta el volumen. En el panel general aparecen todos los dias
    papeles ilfquidos que "suben 15%" con dos operaciones de $50.000: no
    dicen nada del mercado y ensucian el ranking.

Por que hace falta este script:
    Rava muestra las acciones dentro de un iframe de mercado.rava.com que
    arma JavaScript, asi que no hay HTML para leer. Se usa data912, que
    publica el panel completo de BYMA en un solo pedido.

MANTENIMIENTO:
    BYMA revisa la nomina del panel lider TRIMESTRALMENTE (marzo, junio,
    septiembre y diciembre). Cuando entra o sale un papel hay que tocar
    PANEL_LIDER de aca abajo. La nomina vigente se consulta en
    byma.com.ar o en el perfil del indice en Rava.

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import json
import os
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "acciones_cache.js")

API = "https://data912.com/live/arg_stocks"
TIMEOUT = 30
TOP = 3

# Nomina del panel lider (S&P Merval). Revisar cada trimestre.
PANEL_LIDER = {
    "ALUA": "Aluar",
    "BBAR": "Banco Francés",
    "BMA":  "Banco Macro",
    "BYMA": "BYMA",
    "CEPU": "Central Puerto",
    "COME": "Sociedad Comercial del Plata",
    "CRES": "Cresud",
    "CVH":  "Cablevisión Holding",
    "EDN":  "Edenor",
    "GGAL": "Grupo Galicia",
    "IRSA": "IRSA",
    "LOMA": "Loma Negra",
    "METR": "Metrogas",
    "MIRG": "Mirgor",
    "PAMP": "Pampa Energía",
    "SUPV": "Grupo Supervielle",
    "TECO2": "Telecom",
    "TGNO4": "Transportadora Gas del Norte",
    "TGSU2": "Transportadora Gas del Sur",
    "TRAN": "Transener",
    "TXAR": "Ternium Argentina",
    "VALO": "Grupo Financiero Valores",
    "YPFD": "YPF",
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


def panel_lider():
    """[{symbol, nombre, precio, pct}] de los papeles del panel lider."""
    filas = json.loads(_get(API))
    if not isinstance(filas, list) or not filas:
        raise ValueError("la API no devolvio acciones")

    out = []
    for f in filas:
        sym = str(f.get("symbol") or "").strip().upper()
        if sym not in PANEL_LIDER:
            continue
        pct = f.get("pct_change")
        precio = f.get("c")
        if pct is None or precio is None:
            continue
        out.append({
            "symbol": sym,
            "nombre": PANEL_LIDER[sym],
            "precio": round(float(precio), 2),
            "pct": round(float(pct), 2),
        })

    if not out:
        raise ValueError("ningun papel del panel lider vino en la respuesta")
    return out


def main():
    print("Actualizando acciones_cache.js ...")

    try:
        papeles = panel_lider()
    except Exception as e:
        raise SystemExit("[ERROR] No se pudieron obtener las acciones (%s). "
                         "Se conserva el cache anterior." % e)

    faltan = sorted(set(PANEL_LIDER) - {p["symbol"] for p in papeles})
    if faltan:
        print("[AVISO] Sin dato para: " + ", ".join(faltan)
              + " (revisar si siguen en el panel lider)")

    # Los papeles que no operaron quedan en 0,00% y taparian el ranking de
    # subas o de bajas segun el dia. Se los deja afuera del top.
    con_mov = [p for p in papeles if p["pct"] != 0]
    ordenados = sorted(con_mov, key=lambda p: p["pct"], reverse=True)

    mejores = ordenados[:TOP]
    peores = list(reversed(ordenados[-TOP:])) if len(ordenados) >= TOP else []

    def bloque(lista):
        if not lista:
            return "[]"
        filas = ", ".join(
            '{ symbol: "%s", nombre: "%s", precio: %s, pct: %s }'
            % (p["symbol"], p["nombre"], p["precio"], p["pct"]) for p in lista)
        return "[\n    " + filas.replace(", {", ",\n    {") + "\n  ]"

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    js = (
        "/* -----------------------------------------------------------------\n"
        "   acciones_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + ts + "\n"
        "   Las 3 mayores subas y las 3 mayores bajas del PANEL LIDER del\n"
        "   Merval en la rueda. Fuente: data912 (panel de BYMA).\n"
        "   pct = variacion % contra el cierre anterior\n"
        "   Los papeles que no operaron (0,00%) quedan fuera del ranking.\n"
        "----------------------------------------------------------------- */\n"
        "window.ACCIONES_CACHE = {\n"
        "  mejores: " + bloque(mejores) + ",\n"
        "  peores: " + bloque(peores) + ",\n"
        "  panel: " + str(len(papeles)) + ",\n"
        '  fuente: "Panel líder · BYMA vía data912",\n'
        '  updated: "' + ts + '"\n'
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("[OK] acciones_cache.js  ->  " + str(len(papeles)) + " papeles del panel")
    print("     Suben : " + " / ".join("%s %+.2f%%" % (p["symbol"], p["pct"]) for p in mejores))
    print("     Bajan : " + " / ".join("%s %+.2f%%" % (p["symbol"], p["pct"]) for p in peores))


if __name__ == "__main__":
    main()
