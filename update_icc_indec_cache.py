#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_icc_indec_cache.py - Tablero Gestion Grupo Elyon
========================================================
Genera icc_indec_cache.js con el ICC del INDEC: indice del costo de la
construccion en el Gran Buenos Aires.

Que mide y por que no es el ICC de Cordoba
------------------------------------------
Construccion privada de edificios para vivienda en CABA y los 24 partidos del
conurbano. Se abre en Materiales, Mano de obra y Gastos generales, con
ponderaciones 46,0 / 45,6 / 8,4.

El ICC de Cordoba mide otra cosa: una vivienda social de 50,25 m2 en la
provincia, con apertura Materiales / Mano de obra / Varios. Y el CAC es un
tercer indicador, de la Camara Argentina de la Construccion. Los tres suelen
moverse parecido pero no son intercambiables, y cada contrato dice cual usa.

De donde sale
-------------
    https://www.indec.gob.ar/ftp/cuadros/economia/icc_variaciones_indices_2016.xls

Ese Excel tiene nombre estable (no lleva el mes ni un hash adentro), asi que se
puede automatizar. El informe mensual en PDF NO sirve: el nombre incluye un
hash distinto cada mes. Y en apis.datos.gob.ar las series del ICC quedaron
discontinuadas en 2015.

Como lee el Excel
-----------------
No se asume una posicion fija de filas ni columnas: se busca la fila de
encabezado que contenga "Nivel general", "Materiales", "Mano de obra" y
"Gastos generales", y la columna de periodos se detecta por el formato de las
fechas. Si el INDEC mueve las cosas de lugar, el script lo dice en vez de
escribir cualquier cosa.

Al final valida contra un control conocido (junio 2026) para no publicar una
serie mal parseada.

Salida: icc_indec_cache.js
    window.ICC_INDEC_CACHE = {
      updated, source, hasta, tipo,
      serie: [[fecha, nivelGeneral, materiales, manoObra, gastosGenerales], ...]
    }

Uso:
    python update_icc_indec_cache.py
    python update_icc_indec_cache.py --diagnostico   (vuelca la estructura del Excel)
"""

import io
import os
import ssl
import sys
import urllib.request as req
from datetime import datetime

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "icc_indec_cache.js")
XLS_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/icc_variaciones_indices_2016.xls"
TIMEOUT = 60

# Control: lo que dice el informe de junio 2026 (Cuadro 1). Si el parseo da
# otra cosa, algo se rompio y conviene no pisar el cache anterior.
CONTROL = {"mes": "2026-06", "m": 2.6, "ia": 32.1}

CAPITULOS = [
    ("ng",  ["nivel general"]),
    ("mat", ["materiales"]),
    ("mo",  ["mano de obra"]),
    ("gg",  ["gastos generales"]),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def bajar():
    r = req.Request(XLS_URL, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read()


def hojas(crudo):
    """Devuelve {nombre: DataFrame sin encabezado}. Prueba xlrd (.xls viejo) y,
    si el INDEC algun dia lo pasa a xlsx, openpyxl."""
    for motor in ("xlrd", "openpyxl", None):
        try:
            kw = {"engine": motor} if motor else {}
            return pd.read_excel(io.BytesIO(crudo), sheet_name=None, header=None, **kw)
        except Exception as e:
            ultimo = e
    raise SystemExit("[ERROR] No se pudo abrir el Excel: %s\n"
                     "        Si falta xlrd: pip install xlrd" % ultimo)


def texto(v):
    return "" if v is None else str(v).strip().lower()


def a_fecha(v):
    """Acepta datetime de Excel, 'jun-26', 'Junio 2026', '2026-06'."""
    if isinstance(v, (datetime, pd.Timestamp)):
        return "%04d-%02d-01" % (v.year, v.month)
    s = texto(v)
    if not s:
        return None
    meses = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
             "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}
    import re
    m = re.match(r"^(\d{4})-(\d{1,2})", s)
    if m:
        return "%04d-%02d-01" % (int(m.group(1)), int(m.group(2)))
    m = re.match(r"^([a-záéíóú]{3,10})[\s\-/\.]*(\d{2,4})$", s)
    if m:
        mes = meses.get(m.group(1)[:3])
        if mes:
            a = int(m.group(2))
            return "%04d-%02d-01" % (a + 2000 if a < 100 else a, mes)
    return None


def a_num(v):
    try:
        f = float(str(v).replace("%", "").replace(".", "").replace(",", ".")
                  if isinstance(v, str) else v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def buscar_bloque(df):
    """Encuentra la fila de encabezado y las columnas de cada capitulo."""
    for i in range(min(len(df), 40)):
        fila = [texto(v) for v in df.iloc[i].tolist()]
        cols = {}
        for clave, alias in CAPITULOS:
            for j, celda in enumerate(fila):
                if any(a in celda for a in alias) and j not in cols.values():
                    cols[clave] = j
                    break
        if len(cols) == 4:
            return i, cols
    return None, None


def columna_periodos(df, desde):
    """La columna con mas fechas validas por debajo del encabezado."""
    mejor, cuantas = None, 0
    for j in range(min(df.shape[1], 8)):
        n = sum(1 for i in range(desde + 1, len(df)) if a_fecha(df.iat[i, j]))
        if n > cuantas:
            mejor, cuantas = j, n
    return mejor, cuantas


def leer_serie(df):
    enc, cols = buscar_bloque(df)
    if enc is None:
        return None
    colper, n = columna_periodos(df, enc)
    if colper is None or n < 12:
        return None

    filas = []
    for i in range(enc + 1, len(df)):
        f = a_fecha(df.iat[i, colper])
        if not f:
            continue
        vals = [a_num(df.iat[i, cols[c]]) for c, _ in CAPITULOS]
        if vals[0] is None:
            continue
        filas.append([f] + vals)
    filas.sort(key=lambda r: r[0])
    # Puede haber filas repetidas si el Excel trae indices y variaciones juntos
    unicas, vistos = [], set()
    for r in filas:
        if r[0] not in vistos:
            vistos.add(r[0])
            unicas.append(r)
    return unicas or None


def es_indice(serie):
    """Los indices base 1993 andan en miles; las variaciones, entre -20 y 30."""
    ult = [r[1] for r in serie[-12:] if r[1] is not None]
    return bool(ult) and max(abs(v) for v in ult) > 200


def diagnostico(hs):
    print("\n--- ESTRUCTURA DEL EXCEL ---")
    for nombre, df in hs.items():
        print("\n[hoja] %r  filas=%d  columnas=%d" % (nombre, len(df), df.shape[1]))
        print(df.head(12).to_string(max_colwidth=22))
    print("\nPegale esta salida a Claude para que ajuste el parser.")


def num(v):
    return "null" if v is None else ("%.2f" % v).rstrip("0").rstrip(".")


def main():
    print("Actualizando ICC del INDEC (Gran Buenos Aires)...")
    hs = hojas(bajar())
    print("   Hojas: %s" % ", ".join(repr(h) for h in hs))

    if "--diagnostico" in sys.argv:
        return diagnostico(hs)

    # Se prefiere la hoja con indices (niveles): con eso el tablero calcula
    # mensual, interanual y acumulada por su cuenta, sin depender del Excel.
    candidatas = []
    for nombre, df in hs.items():
        s = leer_serie(df)
        if s:
            candidatas.append((nombre, s, es_indice(s)))
    if not candidatas:
        print("\n[ERROR] No se encontro ninguna hoja con Nivel general / Materiales /"
              " Mano de obra / Gastos generales.")
        diagnostico(hs)
        raise SystemExit("Se conserva el icc_indec_cache.js anterior.")

    candidatas.sort(key=lambda c: (not c[2], -len(c[1])))
    nombre, serie, indices = candidatas[0]
    tipo = "indice" if indices else "variacion_mensual"
    print("   Hoja elegida: %r  (%d meses, %s)" % (nombre, len(serie), tipo))

    hasta = serie[-1][0][:7]

    # ── Control contra el informe de junio 2026 ──
    mapa = {r[0][:7]: r for r in serie}
    ctrl = mapa.get(CONTROL["mes"])
    ok = "sin control (el mes de control no esta en la serie)"
    if ctrl:
        if indices:
            prev = mapa.get("2026-05")
            calc = (ctrl[1] / prev[1] - 1) * 100 if prev and prev[1] else None
        else:
            calc = ctrl[1]
        if calc is not None:
            dif = abs(calc - CONTROL["m"])
            ok = "jun-2026 %+.2f%% mensual vs. %+.1f%% del informe -> %s" % (
                calc, CONTROL["m"], "OK" if dif <= 0.15 else "NO COINCIDE")
            if dif > 0.15:
                print("\n[ERROR] " + ok)
                diagnostico(hs)
                raise SystemExit("Se conserva el icc_indec_cache.js anterior.")
    print("   Control: %s" % ok)

    fuente = "INDEC - ICC Gran Buenos Aires"
    cuerpo = ",\n".join(
        '    ["%s",%s,%s,%s,%s]' % (r[0], num(r[1]), num(r[2]), num(r[3]), num(r[4]))
        for r in serie)

    js = (
        "/* ═══════════════════════════\n"
        "   icc_indec_cache.js  -  Grupo Elyon\n"
        "   Generado por update_icc_indec_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + "\n"
        "   " + XLS_URL + "\n"
        "   tipo: " + tipo + "  (indice = niveles; variacion_mensual = % mes a mes)\n"
        "   Columnas: fecha, nivel general, materiales, mano de obra, gastos generales\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.ICC_INDEC_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  tipo: "' + tipo + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  serie: [\n" + cuerpo + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("\n[OK] icc_indec_cache.js")
    print("     %d meses, de %s a %s" % (len(serie), serie[0][0][:7], hasta))


if __name__ == "__main__":
    main()
