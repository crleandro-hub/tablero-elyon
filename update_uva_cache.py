#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_uva_cache.py - Tablero Gestion Grupo Elyon
Genera uva_cache.js con la SERIE HISTORICA COMPLETA del indice UVA.

Por que existe este script:
  El tablero tomaba la serie UVA del endpoint v3.0 (monetarias/7913) desde
  el navegador. Ese endpoint es legacy y dejo de actualizarse: en agosto de
  2026 su ultimo dato seguia siendo el 19/07. El valor del dia, en cambio,
  sale de la v4.0 (serie 31) que si esta al dia, y por eso el KPI y el
  consultor mostraban fechas distintas.

  Ademas el BCRA publica la UVA con varios dias de anticipacion (se calcula
  a partir del CER ya conocido), asi que la serie llega mas alla de hoy.
  Pedir "hasta hoy" perdia esos valores futuros, que son justamente los que
  se necesitan para indexar cuotas y certificados de obra.

Se ejecuta a diario junto con update_bcra_cache.py.

Salida: uva_cache.js  ->  window.UVA_CACHE = { updated, desde, hasta, serie }
        serie = [["aaaa-mm-dd", valor], ...] en orden ascendente.
"""

import json
import re
import os
import ssl
import urllib.request as req
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "uva_cache.js")

API = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/31?desde={desde}&hasta={hasta}"

INICIO_SERIE = "2016-03-31"   # primer dato publicado de la UVA ($14,05)
DIAS_ADELANTE = 120           # margen para capturar los valores ya publicados a futuro


def _open(url):
    """GET con reintento sin verificacion SSL (algunas instalaciones Windows
    no tienen la cadena de certificados del BCRA)."""
    r = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    try:
        return req.urlopen(r, timeout=30).read().decode("utf-8")
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return req.urlopen(r, timeout=30, context=ctx).read().decode("utf-8")


def fetch_tramo(desde, hasta):
    """Devuelve [(fecha, valor)] de un tramo. Lista vacia si no hay datos."""
    js = json.loads(_open(API.format(desde=desde, hasta=hasta)))
    results = js.get("results") or []
    if not results:
        return []
    detalle = results[0].get("detalle") or []
    out = []
    for d in detalle:
        f = str(d.get("fecha") or "")[:10]
        v = d.get("valor")
        if len(f) == 10 and v is not None:
            try:
                out.append((f, float(v)))
            except (TypeError, ValueError):
                pass
    return out


def fetch_serie_completa():
    """Recorre la serie por tramos anuales. La API limita la cantidad de
    registros por pedido, y un año (max 366 filas) entra siempre holgado."""
    hasta_final = datetime.now().date() + timedelta(days=DIAS_ADELANTE)
    anio_ini = int(INICIO_SERIE[:4])
    anio_fin = hasta_final.year

    serie = {}
    fallos = 0
    for anio in range(anio_ini, anio_fin + 1):
        desde = INICIO_SERIE if anio == anio_ini else f"{anio}-01-01"
        hasta = min(datetime(anio, 12, 31).date(), hasta_final).isoformat()
        try:
            tramo = fetch_tramo(desde, hasta)
            for f, v in tramo:
                serie[f] = v
            print(f"     {anio}: {len(tramo):4d} registros")
        except Exception as e:
            fallos += 1
            print(f"     {anio}: [ERROR] {e}")
    return serie, fallos


def leer_cache_previo():
    """Cantidad de registros y ultima fecha del cache actual, para comparar."""
    if not os.path.exists(CACHE_PATH):
        return 0, None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            txt = f.read()
        fechas = re.findall(r'\["(\d{4}-\d{2}-\d{2})",', txt)
        return len(fechas), (max(fechas) if fechas else None)
    except Exception:
        return 0, None


def escribir_cache(serie):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    items = sorted(serie.items())
    desde, hasta = items[0][0], items[-1][0]

    pares = ", ".join(f'["{f}", {round(v, 2)}]' for f, v in items)
    contenido = (
        "/* -----------------------------------------------------------------\n"
        "   uva_cache.js  -  Grupo Elyon  |  Generado automaticamente\n"
        f"   Generado: {ts}\n"
        "   Fuente: API BCRA Estadisticas Monetarias v4.0 - serie 31 (UVA en pesos)\n"
        f"   Registros: {len(items)}  ({desde} a {hasta})\n"
        "   Formato por registro: [fecha, valor en pesos]\n"
        "----------------------------------------------------------------- */\n"
        "window.UVA_CACHE = {\n"
        f'  updated: "{ts}",\n'
        f'  desde: "{desde}",\n'
        f'  hasta: "{hasta}",\n'
        f"  serie: [{pares}]\n"
        "};\n"
    )
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(contenido)
    return len(items), desde, hasta


def main():
    print("Actualizando uva_cache.js desde api.bcra.gob.ar (serie 31, v4.0) ...")
    prev_n, prev_ult = leer_cache_previo()

    serie, fallos = fetch_serie_completa()

    if not serie:
        print("[ABORTA] No se obtuvo ningun dato. Se conserva el cache anterior.")
        return 1

    # Guarda de seguridad: no pisar un cache bueno con uno claramente incompleto.
    if prev_n and len(serie) < prev_n * 0.9:
        print(f"[ABORTA] La descarga trajo {len(serie)} registros contra "
              f"{prev_n} del cache actual. Parece incompleta; no se pisa nada.")
        return 1

    n, desde, hasta = escribir_cache(serie)
    print(f"[OK] uva_cache.js actualizado - {n} registros ({desde} a {hasta})")

    if prev_ult and hasta > prev_ult:
        print(f"[CAMBIO] Se sumaron datos: el cache anterior llegaba al {prev_ult}.")
    elif prev_ult == hasta:
        print("[SIN CAMBIOS] Misma ultima fecha que la corrida anterior.")

    hoy = datetime.now().date().isoformat()
    if hasta > hoy:
        print(f"[ADELANTADO] La serie llega al {hasta}, mas alla de hoy ({hoy}), "
              "como corresponde: el BCRA publica la UVA por anticipado.")
    else:
        print(f"[ATENCION] La serie termina el {hasta} y hoy es {hoy}. "
              "El BCRA suele publicar con anticipacion; revisar la fuente.")

    if fallos:
        print(f"[AVISO] {fallos} tramo(s) anual(es) fallaron; la serie puede tener huecos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
