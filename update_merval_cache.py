#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_merval_cache.py - Tablero Gestion Grupo Elyon
====================================================
Genera merval_cache.js con el indice S&P Merval en pesos y en dolares.

Por que hace falta este script:
    Los proveedores de cotizaciones de indices no habilitan CORS, asi que el
    navegador no puede pedirles los datos directamente. Python si puede: no
    tiene esa restriccion. El tablero lee merval_cache.js y, si ademas el
    navegador logra el pedido en vivo, lo pisa con el valor mas fresco.

Merval en dolares:
    Es la convencion de mercado: indice en pesos dividido el contado con
    liquidacion (punta vendedora) de la misma rueda. La serie de CCL sale de
    api.argentinadatos.com, la misma que ya usa el resto del tablero.

Fuentes, en orden de intento:
    1. Yahoo Finance  - chart de ^MERV (query1 y query2)
    2. Rava Bursatil  - API publica de historicos (token tomado de la pagina)
    3. Rava clasico   - CSV de precios historicos
    4. Stooq          - CSV historico de ^mrv

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import csv
import io
import json
import os
import re
import ssl
import urllib.parse
import urllib.request as req
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "merval_cache.js")

YAHOO = "{host}/v8/finance/chart/%5EMERV?range=5y&interval=1d"
YAHOO_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]
STOOQ = "https://stooq.com/q/d/l/?s=%5Emrv&i=d"
RAVA_PERFIL = "https://clasico.rava.com/perfil/MERVAL"
RAVA_API = "https://clasico.rava.com/lib/restapi/v3/publico/cotizaciones/historicos"
RAVA_CSV = "https://clasico.rava.com/empresas/precioshistoricos.php?e=MERVAL&csv=1"
CCL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui"

ANIOS_SERIE = 5          # cuantos años de historia se guardan en el cache
TIMEOUT = 30


def _get(url):
    """GET con reintento sin verificacion SSL (algunas instalaciones Windows
    no traen la cadena de certificados completa)."""
    r = req.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/csv, */*",
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


# ─────────────────────────────────────────────────────────────
#  Fuentes del indice en pesos
# ─────────────────────────────────────────────────────────────
def serie_yahoo():
    """[(fecha ISO, cierre)] ascendente desde el chart de Yahoo Finance."""
    for host in YAHOO_HOSTS:
        try:
            j = json.loads(_get(YAHOO.format(host=host)))
            res = (j.get("chart") or {}).get("result") or []
            if not res:
                continue
            r = res[0]
            ts = r.get("timestamp") or []
            quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
            close = quote.get("close") or []
            out = {}
            for i, t in enumerate(ts):
                v = close[i] if i < len(close) else None
                if v is None:
                    continue
                out[datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")] = float(v)
            if out:
                print("[OK] Merval desde " + host)
                return sorted(out.items())
        except Exception as e:
            print("[AVISO] Yahoo " + host + ": " + str(e))
    return []


def _post(url, campos):
    body = urllib.parse.urlencode(campos).encode()
    r = req.Request(url, data=body, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, */*",
        "Referer": RAVA_PERFIL,
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


def serie_rava_api():
    """[(fecha ISO, cierre)] desde la API publica de Rava Bursatil.

    La API pide un access_token que la propia pagina del perfil deja embebido
    en el HTML, asi que primero se lo lee de ahi."""
    try:
        html = _get(RAVA_PERFIL).decode("utf-8", "replace")
        m = re.search(r'access[_-]?token["\']?\s*[:=]\s*["\']([A-Za-z0-9._-]{10,})["\']',
                      html, re.I)
        if not m:
            raise ValueError("no se encontro el access_token en la pagina")
        token = m.group(1)

        hasta = datetime.now()
        desde = hasta - timedelta(days=365 * ANIOS_SERIE)
        crudo = _post(RAVA_API, {
            "access_token": token,
            "especie": "MERVAL",
            "fecha_inicio": desde.strftime("%Y-%m-%d"),
            "fecha_fin": hasta.strftime("%Y-%m-%d"),
        })
        j = json.loads(crudo)
        filas = j.get("body") or j.get("data") or j.get("datos") or []

        out = {}
        for f in filas:
            if not isinstance(f, dict):
                continue
            fecha = str(f.get("fecha") or f.get("Fecha") or "")[:10]
            cierre = f.get("cierre", f.get("Cierre", f.get("close")))
            if len(fecha) == 10 and cierre not in (None, ""):
                try:
                    out[fecha] = float(cierre)
                except (TypeError, ValueError):
                    pass
        if out:
            print("[OK] Merval desde Rava Bursatil (API)")
            return sorted(out.items())
        raise ValueError("la API no devolvio cotizaciones")
    except Exception as e:
        print("[AVISO] Rava API: " + str(e))
    return []


def _serie_csv(url, etiqueta, cols_fecha, cols_cierre):
    """Parser generico de CSV con columnas de fecha y cierre por nombre."""
    try:
        txt = _get(url).decode("utf-8", "replace")
        # Algunas fuentes usan punto y coma como separador
        sep = ";" if txt.count(";") > txt.count(",") else ","
        filas = list(csv.DictReader(io.StringIO(txt), delimiter=sep))
        if not filas:
            raise ValueError("CSV vacio")

        campos = {str(k).strip().lower(): k for k in filas[0].keys() if k}
        kf = next((campos[c] for c in cols_fecha if c in campos), None)
        kc = next((campos[c] for c in cols_cierre if c in campos), None)
        if not kf or not kc:
            raise ValueError("no se reconocieron las columnas: " + ", ".join(campos))

        out = {}
        for f in filas:
            fecha = str(f.get(kf) or "").strip()[:10]
            crudo = str(f.get(kc) or "").strip().replace(".", "").replace(",", ".") \
                if sep == ";" else str(f.get(kc) or "").strip()
            if len(fecha) == 10 and crudo:
                try:
                    out[fecha] = float(crudo)
                except ValueError:
                    pass
        if out:
            print("[OK] Merval desde " + etiqueta)
            return sorted(out.items())
        raise ValueError("sin filas utilizables")
    except Exception as e:
        print("[AVISO] " + etiqueta + ": " + str(e))
    return []


def serie_rava_csv():
    return _serie_csv(RAVA_CSV, "Rava clasico (CSV)",
                      ("fecha", "date"), ("cierre", "close", "ultimo"))


def serie_stooq():
    return _serie_csv(STOOQ, "Stooq", ("date", "fecha"), ("close", "cierre"))


def serie_ccl():
    """{fecha ISO: venta} del contado con liquidacion."""
    try:
        arr = json.loads(_get(CCL))
        out = {}
        for r in arr:
            f = str(r.get("fecha") or "")[:10]
            v = r.get("venta")
            if len(f) == 10 and v is not None:
                out[f] = float(v)
        print("[OK] CCL: " + str(len(out)) + " ruedas")
        return out
    except Exception as e:
        print("[AVISO] CCL: " + str(e))
        return {}


def ccl_en(ccl, fecha):
    """CCL de esa fecha o, si no cotizo, el habil anterior mas cercano."""
    v = ccl_en2(ccl, fecha)
    return v[0] if v else None


def ccl_en2(ccl, fecha):
    """(valor, fecha_efectiva) del CCL de esa rueda o del habil anterior.

    Devolver tambien la fecha importa: si el CCL no es de la misma rueda que
    el indice, el 'Merval en dolares' no es comparable con el que publica el
    broker y el tablero tiene que poder aclararlo."""
    from datetime import date, timedelta
    d = date.fromisoformat(fecha)
    for _ in range(11):
        f = d.isoformat()
        if f in ccl:
            return (ccl[f], f)
        d -= timedelta(days=1)
    return None


def main():
    print("Actualizando merval_cache.js ...")

    serie = (serie_yahoo() or serie_rava_api() or serie_rava_csv()
             or serie_stooq())
    if not serie:
        raise SystemExit("[ERROR] Ninguna fuente devolvio el Merval. "
                         "Se conserva el cache anterior.")

    corte = str(datetime.now().year - ANIOS_SERIE) + "-01-01"
    serie = [(f, v) for f, v in serie if f >= corte]

    ccl = serie_ccl()

    hoy = serie[-1]
    prev = serie[-2] if len(serie) > 1 else None

    ars = round(hoy[1], 2)
    ars_var = round((hoy[1] / prev[1] - 1) * 100, 4) if prev and prev[1] else None

    r_hoy = ccl_en2(ccl, hoy[0]) if ccl else None
    r_prev = ccl_en2(ccl, prev[0]) if (ccl and prev) else None
    c_hoy, f_hoy = r_hoy if r_hoy else (None, None)
    c_prev, f_prev = r_prev if r_prev else (None, None)

    usd = round(hoy[1] / c_hoy, 2) if c_hoy else None

    # La variacion en dolares solo tiene sentido si los dos CCL son de ruedas
    # distintas. Cuando falta el CCL del dia y se arrastra el anterior, el
    # divisor es el mismo arriba y abajo y la "variacion en dolares" terminaba
    # dando identica a la variacion en pesos, que es un dato falso.
    usd_var = None
    if usd is not None and prev and c_prev and f_prev != f_hoy:
        usd_var = round((usd / (prev[1] / c_prev) - 1) * 100, 4)

    # Serie diaria [fecha, merval_ars, merval_usd] para uso futuro del tablero.
    # Si a una rueda le falta el CCL (ArgentinaDatos tiene huecos) se arrastra
    # el ultimo disponible en vez de dejar null, que cortaba el grafico.
    filas = []
    for f, v in serie:
        c = ccl.get(f)
        if c is None:
            r = ccl_en2(ccl, f) if ccl else None
            c = r[0] if r else None
        filas.append('["%s",%s,%s]' % (f, round(v, 2),
                                       round(v / c, 2) if c else "null"))

    js = (
        "/* -----------------------------------------------------------------\n"
        "   merval_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n"
        "   ars = indice S&P Merval en pesos (cierre diario)\n"
        "   usd = indice en pesos dividido el CCL de la misma rueda\n"
        "   serie = [fecha, merval_ars, merval_usd] de los ultimos "
        + str(ANIOS_SERIE) + " años\n"
        "----------------------------------------------------------------- */\n"
        "window.MERVAL_CACHE = {\n"
        '  fecha: "' + hoy[0] + '",\n'
        "  ars: " + str(ars) + ",\n"
        "  arsVar: " + (str(ars_var) if ars_var is not None else "null") + ",\n"
        "  usd: " + (str(usd) if usd is not None else "null") + ",\n"
        "  usdVar: " + (str(usd_var) if usd_var is not None else "null") + ",\n"
        "  ccl: " + (str(round(c_hoy, 2)) if c_hoy else "null") + ",\n"
        '  cclFecha: ' + ('"' + f_hoy + '"' if f_hoy else "null") + ",\n"
        '  fuente: "S&P Merval · BYMA · merval_cache.js",\n'
        '  updated: "' + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + '",\n'
        "  serie: [\n    " + ",\n    ".join(filas) + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("[OK] merval_cache.js  ->  " + hoy[0]
          + "  ARS " + str(ars)
          + ("  USD " + str(usd) if usd is not None else "  USD sin CCL")
          + "  (" + str(len(serie)) + " ruedas)")


if __name__ == "__main__":
    main()
