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
import html as htmllib
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
RAVA_WWW = "https://www.rava.com/perfil/MERVAL"
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


def serie_rava_perfil():
    """[(fecha ISO, cierre)] de la tabla de www.rava.com/perfil/MERVAL.

    Es la misma lectura que ya usan caucion y riesgo pais. El dominio
    clasico.rava.com (API y CSV) timeoutea desde la maquina del tablero, pero
    www.rava.com sirve la tabla de cotizaciones historicas dentro del HTML, sin
    JavaScript. Trae pocas ruedas, no sirve de serie larga: sirve para empalmar
    los dias que a Yahoo le faltan."""
    doc = _get(RAVA_WWW).decode("utf-8", "replace")
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", doc, re.S | re.I):
        celdas = [htmllib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                  for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(celdas) < 5:
            continue
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", celdas[0])
        if not m:
            continue
        s = celdas[4].strip().replace(".", "").replace(",", ".")
        s = re.sub(r"[^0-9.\-]", "", s)
        try:
            cierre = float(s)
        except ValueError:
            continue
        if cierre > 0:
            out["%s-%s-%s" % (m.group(3), m.group(2), m.group(1))] = cierre
    if not out:
        raise ValueError("no se encontraron filas en la tabla del perfil")
    return sorted(out.items())


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


def serie_del_cache():
    """La serie que ya tiene merval_cache.js.

    Es la memoria larga del tablero y, sobre todo, la que FIJA LA ESCALA. El
    Merval se publica en escalas distintas segun la fuente (www.rava.com lo da
    28,4894 veces mas chico que Yahoo) y eso no puede depender de cual fuente
    conteste mejor ese dia."""
    if not os.path.exists(CACHE_PATH):
        return []
    try:
        txt = open(CACHE_PATH, encoding="utf-8").read()
    except Exception:
        return []
    filas = re.findall(r'\["(\d{4}-\d{2}-\d{2})",([0-9.]+)', txt)
    return sorted((f, float(v)) for f, v in filas)


def alinear(serie, patron, nombre):
    """serie reexpresada en la escala de patron, o None si no se puede.

    La relacion se mide con la mediana y se juzga por el grueso de las ruedas,
    no por la peor: dos fuentes distintas siempre tienen algun dia que no
    cierra igual (un cierre corregido, una rueda a medias)."""
    mapa = dict(patron)
    comunes = [(v, mapa[f]) for f, v in serie if f in mapa and mapa[f] and v]
    if len(comunes) < 10:
        print("     [AVISO] %s comparte solo %d rueda(s) con la serie del "
              "tablero: no se puede alinear." % (nombre, len(comunes)))
        return None

    razones = sorted(b / a for a, b in comunes)
    n = len(razones)
    k = razones[n // 2]
    p10, p90 = razones[int(n * 0.10)], razones[min(n - 1, int(n * 0.90))]
    cuerpo = max(abs(p10 / k - 1), abs(p90 / k - 1))
    if cuerpo > 0.005:
        print("     [AVISO] la relacion de %s con la serie del tablero no es "
              "estable (el 80%% central se mueve %.2f%% en %d ruedas): se descarta."
              % (nombre, cuerpo * 100, n))
        return None

    if abs(k - 1) > 0.005:
        print("     %-18s se reexpresa por %.6f (publica el indice en otra escala)"
              % (nombre, k))
    return [(f, v * k) for f, v in serie]


def elegir_serie():
    """Devuelve la serie del Merval, en la escala historica del tablero.

    Como se llego a esto. Primero era una cascada y ganaba la primera fuente
    que contestara: en octubre de 2026 Yahoo dejo de actualizar el ^MERV pero
    seguia respondiendo, y el tablero se quedo una semana clavado. Se cambio a
    "gana la que llega mas lejos", con la mas LARGA de base y las demas
    empalmadas encima, reexpresadas si venian en otra escala.

    Eso fallo el 7 de noviembre de 2026 y hay que dejarlo escrito. Yahoo se
    degrado del todo: paso de devolver 1.216 ruedas a devolver 64. La serie
    mas larga paso a ser la de www.rava.com, que se volvio la BASE, y una base
    no se reexpresa contra nada: el tablero se quedo con la escala de Rava.
    El Merval paso de 2.394.592 a 81.932 puntos, el valor en dolares de 1.700
    a 48, y el grafico perdio cinco años de historia de un dia para el otro.
    Doce dias asi.

    El error de fondo era tomar la escala y la historia de una fuente que
    puede cambiar. Ahora las dos salen del cache: la serie que ya esta en
    merval_cache.js es el patron, toda fuente se reexpresa contra ella antes
    de tocar nada, y lo unico que las fuentes aportan son las ruedas nuevas.
    Asi el tablero no puede cambiar de escala ni perder historia porque una
    fuente se rompa."""
    candidatas = [
        ("Yahoo Finance", serie_yahoo),
        ("Rava (API)", serie_rava_api),
        ("Rava (CSV)", serie_rava_csv),
        ("Rava (perfil web)", serie_rava_perfil),
        ("Stooq", serie_stooq),
    ]
    vivas = []
    for nombre, fn in candidatas:
        try:
            serie = fn()
        except Exception as e:
            print("     [AVISO] %s fallo: %s" % (nombre, e))
            continue
        if not serie:
            continue
        print("     %-18s hasta %s (%d ruedas)" % (nombre, serie[-1][0], len(serie)))
        vivas.append((nombre, serie))

    historico = serie_del_cache()

    if not historico:
        # Primera corrida: no hay patron, manda la mas larga y se avisa.
        if not vivas:
            return None
        nombre, serie = max(vivas, key=lambda x: len(x[1]))
        print("   No hay cache previo: se arranca con %s (%d ruedas). La escala "
              "de esta corrida queda como patron." % (nombre, len(serie)))
        return serie

    if not vivas:
        print("   Ninguna fuente contesto: se conserva la serie del cache "
              "(%d ruedas, hasta %s)." % (len(historico), historico[-1][0]))
        return historico

    ultimo = historico[-1][0]
    mejor = None
    for nombre, serie in vivas:
        alineada = alinear(serie, historico, nombre)
        if not alineada:
            continue
        nuevas = [f for f in alineada if f[0] > ultimo]
        if nuevas and (mejor is None or nuevas[-1][0] > mejor[1][-1][0]):
            mejor = (nombre, nuevas)

    if not mejor:
        print("   Ninguna fuente aporta ruedas nuevas: la serie queda en %s "
              "(%d ruedas)." % (ultimo, len(historico)))
        return historico

    nombre, nuevas = mejor
    print("   Se agregan %d rueda(s) de %s, hasta %s. La escala y los %d dias "
          "de historia los pone el cache."
          % (len(nuevas), nombre, nuevas[-1][0], len(historico)))
    return historico + nuevas


def main():
    print("Actualizando merval_cache.js ...")

    previo = serie_del_cache()
    serie = elegir_serie()
    if not serie:
        raise SystemExit("[ERROR] Ninguna fuente devolvio el Merval. "
                         "Se conserva el cache anterior.")

    # Doble llave sobre lo que fallo el 7 de noviembre de 2026: el cache no
    # puede encoger ni cambiar de escala de una corrida a la otra. elegir_serie
    # ya lo garantiza, pero esto queda por si alguien la toca mas adelante.
    if previo:
        if len(serie) < len(previo):
            raise SystemExit(
                "[ERROR] la serie nueva tiene %d ruedas y el cache tenia %d. "
                "No se escribe: algo perdio historia." % (len(serie), len(previo)))
        nuevo = dict(serie).get(previo[-1][0])
        if nuevo and previo[-1][1] and abs(nuevo / previo[-1][1] - 1) > 0.02:
            raise SystemExit(
                "[ERROR] el %s el cache decia %.1f y ahora da %.1f. No se "
                "escribe: parece un cambio de escala, no una revision."
                % (previo[-1][0], previo[-1][1], nuevo))

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

    with open(CACHE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)

    print("[OK] merval_cache.js  ->  " + hoy[0]
          + "  ARS " + str(ars)
          + ("  USD " + str(usd) if usd is not None else "  USD sin CCL")
          + "  (" + str(len(serie)) + " ruedas)")


if __name__ == "__main__":
    main()
