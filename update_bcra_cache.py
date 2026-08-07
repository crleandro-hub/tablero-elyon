#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_bcra_cache.py - Tablero Gestion Grupo Elyon
Actualiza bcra_cache.js con TAMAR, BADLAR y UVA desde la API OFICIAL del BCRA
(Estadisticas Monetarias v4.0), consultando cada serie por id con rango de fechas.

Por que asi:
  - El endpoint /monetarias (listado general) devuelve 'ultValorInformado' con
    hasta un dia de atraso respecto de la serie individual. Consultando
    /monetarias/{id}?desde=&hasta= se obtiene siempre el ultimo dato publicado.
  - Se elimina el scraping de lamacro.ar (regex fragil, valores desfasados).

Series utilizadas (TNA, bancos privados):
  44 -> TAMAR  bancos privados - En porcentaje nominal anual
   7 -> BADLAR bancos privados - En porcentaje nominal anual
  31 -> UVA (en pesos)

Ejecutar diariamente via tarea programada.
"""

import json
import ssl
import urllib.request as req
from datetime import datetime, timedelta

CACHE_PATH = r"C:\Users\LMoreno\Dropbox\CLAUDE\Tablero General Grupo Elyon\bcra_cache.js"

API = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/{id}?desde={desde}&hasta={hasta}"

VARS = {
    "tamar":  {"id": 44, "dec": 4, "desc": "TAMAR bancos privados - TNA"},
    "badlar": {"id": 7,  "dec": 4, "desc": "BADLAR bancos privados - TNA"},
    "uva":    {"id": 31, "dec": 2, "desc": "UVA en pesos"},
}

DIAS_ATRAS = 20  # margen por feriados / fines de semana largos


def _open(url):
    """GET con reintento sin verificacion SSL (algunas instalaciones Windows
    no tienen la cadena de certificados del BCRA)."""
    r = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    try:
        return req.urlopen(r, timeout=20).read().decode("utf-8")
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return req.urlopen(r, timeout=20, context=ctx).read().decode("utf-8")


def fetch_serie(var_id):
    """Devuelve (valor, fecha_iso) del ultimo dato publicado de la serie."""
    hasta = datetime.now().date()
    desde = hasta - timedelta(days=DIAS_ATRAS)
    url = API.format(id=var_id, desde=desde.isoformat(), hasta=hasta.isoformat())
    js = json.loads(_open(url))
    results = js.get("results") or []
    if not results:
        return None, None
    detalle = results[0].get("detalle") or []
    if not detalle:
        return None, None
    # La API devuelve orden descendente, pero ordenamos por las dudas.
    detalle.sort(key=lambda d: d["fecha"], reverse=True)
    ult = detalle[0]
    return float(ult["valor"]), ult["fecha"]


def write_cache(data):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    lines = [
        "/* -----------------------------------------------------------------",
        "   bcra_cache.js  -  Grupo Elyon  |  Actualizado automaticamente",
        f"   Generado: {ts}   Fuente: API BCRA Estadisticas Monetarias v4.0",
        "   tamar = serie 44 (TNA, bancos privados)",
        "   badlar = serie 7 (TNA, bancos privados)",
        "   uva = serie 31",
        "----------------------------------------------------------------- */",
        "window.BCRA_CACHE = {",
    ]
    for key, info in data.items():
        if info["valor"] is not None:
            dec = VARS[key]["dec"]
            valor = round(info["valor"], dec)
            lines.append(f'  {key}: {{ valor: {valor}, fecha: "{info["fecha"]}" }},')
        else:
            lines.append(f"  {key}: null,")
    lines.append(f'  updated: "{ts}"')
    lines.append("};")
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] bcra_cache.js actualizado - {ts}")
    for k, v in data.items():
        f_ = v["fecha"]
        if f_ and len(f_) == 10:
            f_ = f"{f_[8:10]}/{f_[5:7]}/{f_[0:4]}"
        print(f"     {k:7s}: {v['valor']}  ({f_})")


def main():
    print("Actualizando bcra_cache.js desde api.bcra.gob.ar ...")
    data = {}
    ok = 0
    for key, cfg in VARS.items():
        try:
            valor, fecha = fetch_serie(cfg["id"])
        except Exception as e:
            print(f"[ERROR] {key} (serie {cfg['id']}): {e}")
            valor, fecha = None, None
        if valor is None:
            print(f"[WARN] Sin dato para {key} - {cfg['desc']}")
        else:
            ok += 1
        data[key] = {"valor": valor, "fecha": fecha}

    if ok == 0:
        print("[ABORTA] Ninguna serie pudo obtenerse. Se conserva el cache anterior.")
        return
    write_cache(data)


if __name__ == "__main__":
    main()
