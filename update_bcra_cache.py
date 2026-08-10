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
   1 -> Reservas internacionales del BCRA (en millones de US$)

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
    # Las reservas no son una tasa: se guarda ademas la variacion contra ~30
    # dias atras, porque el nivel suelto no dice nada. Se mueven fuerte dia a
    # dia por pagos de deuda y liquidacion del agro, asi que la lectura util
    # es la tendencia del mes, no la rueda.
    "reservas": {"id": 1, "dec": 0, "desc": "Reservas internacionales (US$ M)",
                 "var30": True},
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


def fetch_detalle(var_id, dias):
    """Devuelve [{fecha, valor}] descendente de los ultimos `dias`."""
    hasta = datetime.now().date()
    desde = hasta - timedelta(days=dias)
    url = API.format(id=var_id, desde=desde.isoformat(), hasta=hasta.isoformat())
    js = json.loads(_open(url))
    results = js.get("results") or []
    if not results:
        return []
    detalle = results[0].get("detalle") or []
    # La API devuelve orden descendente, pero ordenamos por las dudas.
    detalle.sort(key=lambda d: d["fecha"], reverse=True)
    return detalle


def fetch_serie(var_id):
    """Devuelve (valor, fecha_iso) del ultimo dato publicado de la serie."""
    detalle = fetch_detalle(var_id, DIAS_ATRAS)
    if not detalle:
        return None, None
    ult = detalle[0]
    return float(ult["valor"]), ult["fecha"]


def fetch_var30(var_id):
    """(valor, fecha, var % contra ~30 dias atras) de la serie.

    Se pide una ventana de 50 dias y se busca el dato publicado mas cercano a
    30 dias antes del ultimo: si ese dia fue feriado, sirve el habil previo."""
    detalle = fetch_detalle(var_id, 50)
    if not detalle:
        return None, None, None
    ult = detalle[0]
    valor, fecha = float(ult["valor"]), ult["fecha"]

    objetivo = datetime.strptime(fecha, "%Y-%m-%d").date() - timedelta(days=30)
    ref = None
    for d in detalle:
        f = datetime.strptime(d["fecha"], "%Y-%m-%d").date()
        if f <= objetivo:
            ref = float(d["valor"])
            break
    if ref is None and len(detalle) > 1:
        # La serie no llega a 30 dias: se usa el dato mas viejo que haya
        ref = float(detalle[-1]["valor"])

    var = round((valor / ref - 1) * 100, 2) if ref else None
    return valor, fecha, var


def write_cache(data):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    lines = [
        "/* -----------------------------------------------------------------",
        "   bcra_cache.js  -  Grupo Elyon  |  Actualizado automaticamente",
        f"   Generado: {ts}   Fuente: API BCRA Estadisticas Monetarias v4.0",
        "   tamar = serie 44 (TNA, bancos privados)",
        "   badlar = serie 7 (TNA, bancos privados)",
        "   uva = serie 31",
        "   reservas = serie 1 (millones de US$); var30 = % contra ~30 dias atras",
        "----------------------------------------------------------------- */",
        "window.BCRA_CACHE = {",
    ]
    for key, info in data.items():
        if info["valor"] is not None:
            dec = VARS[key]["dec"]
            valor = round(info["valor"], dec)
            if dec == 0:
                valor = int(valor)
            extra = ""
            if info.get("var30") is not None:
                extra = f', var30: {info["var30"]}'
            lines.append(
                f'  {key}: {{ valor: {valor}, fecha: "{info["fecha"]}"{extra} }},')
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
        var30 = None
        try:
            if cfg.get("var30"):
                valor, fecha, var30 = fetch_var30(cfg["id"])
            else:
                valor, fecha = fetch_serie(cfg["id"])
        except Exception as e:
            print(f"[ERROR] {key} (serie {cfg['id']}): {e}")
            valor, fecha = None, None
        if valor is None:
            print(f"[WARN] Sin dato para {key} - {cfg['desc']}")
        else:
            ok += 1
        data[key] = {"valor": valor, "fecha": fecha, "var30": var30}

    if ok == 0:
        print("[ABORTA] Ninguna serie pudo obtenerse. Se conserva el cache anterior.")
        return
    write_cache(data)


if __name__ == "__main__":
    main()
