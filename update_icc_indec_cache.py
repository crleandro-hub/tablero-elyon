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
import re
import ssl
import sys
import traceback
import urllib.request as req
from datetime import datetime

# pandas y xlrd no vienen con Python. update_cac_cache.py ya los usa, asi que
# normalmente estan; pero si esta PC tiene mas de un Python instalado, el .bat
# puede agarrar uno distinto al de la tarea programada. Por eso el aviso dice
# con que interprete hay que instalarlos.
try:
    import pandas as pd
except ImportError:
    raise SystemExit(
        "[ERROR] Falta pandas en este Python.\n"
        "        Interprete: %s\n"
        "        Instalalo con:  \"%s\" -m pip install pandas xlrd"
        % (sys.executable, sys.executable))

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
    """Devuelve {nombre: DataFrame sin encabezado}. Prueba xlrd (.xls viejo),
    openpyxl (por si el INDEC lo pasa a xlsx) y, como ultimo recurso, lo lee
    como tabla HTML: varios sitios oficiales publican .xls que en realidad son
    HTML con extension cambiada."""
    errores = []
    for motor in ("xlrd", "openpyxl", None):
        try:
            kw = {"engine": motor} if motor else {}
            return pd.read_excel(io.BytesIO(crudo), sheet_name=None, header=None, **kw)
        except Exception as e:
            errores.append("%s: %s" % (motor or "auto", e))

    try:
        tablas = pd.read_html(io.BytesIO(crudo), header=None)
        if tablas:
            print("   [AVISO] El archivo no es un Excel real: se leyo como HTML.")
            return {"html_%d" % i: t for i, t in enumerate(tablas)}
    except Exception as e:
        errores.append("html: %s" % e)

    raise SystemExit(
        "[ERROR] No se pudo abrir el archivo del INDEC.\n        "
        + "\n        ".join(errores)
        + "\n        Si falta xlrd:  \"%s\" -m pip install xlrd" % sys.executable)


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
    """Los valores de xlrd ya vienen como float. Si vienen como texto puede ser
    formato argentino ('1.234,56') o ingles ('1234.56'): solo se sacan los
    puntos de miles cuando ademas hay una coma decimal."""
    if isinstance(v, str):
        s = v.replace("%", "").replace(" ", "").strip()
        if not s:
            return None
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        v = s
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


MESES_NOM = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
             "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
             "noviembre": 11, "diciembre": 12}


def _anio(v):
    try:
        n = int(float(v))
        return n if 1990 <= n <= 2100 else None
    except (TypeError, ValueError):
        return None


def _mes(v):
    # Los meses provisorios vienen marcados con asterisco: "Enero*"
    return MESES_NOM.get(texto(v).replace("*", "").strip())


def mapa_columnas(df):
    """El Excel del INDEC viene TRANSPUESTO: los capitulos son filas y los
    meses son columnas, agrupados por año. Una fila trae los años (solo en la
    columna donde arranca cada uno) y la de abajo los nombres de mes.

    Devuelve {columna: 'aaaa-mm-01'} arrastrando el año hacia la derecha."""
    fa = fm = None
    for i in range(min(len(df), 15)):
        fila = df.iloc[i].tolist()
        if fa is None and sum(1 for v in fila if _anio(v)) >= 2:
            fa = i
        elif fa is not None and sum(1 for v in fila if _mes(v)) >= 6:
            fm = i
            break
    if fa is None or fm is None:
        return None, None

    cols, anio = {}, None
    for j in range(df.shape[1]):
        a = _anio(df.iat[fa, j])
        if a:
            anio = a
        mes = _mes(df.iat[fm, j])
        if anio and mes:
            cols[j] = "%04d-%02d-01" % (anio, mes)
    return (cols, fm) if cols else (None, None)


def _etiqueta(v):
    """Normaliza el rotulo de la fila para compararlo con el nombre del
    capitulo: saca la llamada al pie y los espacios sobrantes.
        'Mano de obra (1)'  ->  'mano de obra'
    Ojo: NO alcanza con buscar el nombre adentro del texto. La fila de titulo
    dice 'Nivel general y capitulos_var%', que contiene 'nivel general' y se
    colaba como si fuera la fila de datos."""
    return re.sub(r"\(.*?\)", "", texto(v)).strip(" .:*")


def leer_transpuesta(df):
    """Lee una hoja con el layout del INDEC (capitulos en filas)."""
    cols, fm = mapa_columnas(df)
    if not cols or len(cols) < 12:
        return None

    filas_cap = {}
    for i in range(fm + 1, len(df)):          # solo debajo de la fila de meses
        etiqueta = _etiqueta(df.iat[i, 0])
        if not etiqueta:
            continue
        for clave, alias in CAPITULOS:
            if clave not in filas_cap and etiqueta in alias:
                filas_cap[clave] = i
    if len(filas_cap) < 4:
        return None

    serie = []
    for j in sorted(cols, key=lambda c: cols[c]):
        vals = [a_num(df.iat[filas_cap[c], j]) for c, _ in CAPITULOS]
        if vals[0] is None:
            continue
        serie.append([cols[j]] + vals)
    serie.sort(key=lambda r: r[0])
    return serie or None


def es_indice(serie):
    """Los indices andan en cientos o miles; las variaciones, entre -20 y 30."""
    ult = [r[1] for r in serie[-12:] if r[1] is not None]
    return bool(ult) and max(abs(v) for v in ult) > 200


def extender_hacia_atras(niveles, variaciones):
    """La hoja de indices arranca en 2022, la de variaciones en 2015. Se
    reconstruyen los meses previos dividiendo el nivel por cada variacion:

        nivel(t-1) = nivel(t) / (1 + var(t)/100)

    Asi el grafico muestra la serie larga con una unica escala."""
    if not niveles or not variaciones:
        return niveles
    var = {r[0]: r for r in variaciones}
    fechas_var = sorted(var)
    primero = niveles[0][0]
    if primero not in var:
        return niveles
    corte = fechas_var.index(primero)
    if corte == 0:
        return niveles

    previos, actual = [], list(niveles[0][1:])
    for k in range(corte - 1, -1, -1):
        # var del mes siguiente = cuanto subio de fechas_var[k] a fechas_var[k+1]
        v = var[fechas_var[k + 1]]
        fila = []
        for c in range(4):
            pct = v[c + 1]
            fila.append(None if actual[c] is None or pct is None or pct <= -100
                        else actual[c] / (1 + pct / 100.0))
        if fila[0] is None:
            break
        previos.append([fechas_var[k]] + fila)
        actual = fila

    previos.reverse()
    return previos + niveles


def diagnostico(hs):
    """Vuelca las primeras filas y columnas de cada hoja. Se recorta a 14
    columnas: con eso alcanza para ver como esta armada la planilla y el log
    no queda ilegible (la hoja de variaciones tiene 140 columnas)."""
    print("\n--- ESTRUCTURA DEL EXCEL ---")
    for nombre, df in hs.items():
        print("\n[hoja] %r  filas=%d  columnas=%d" % (nombre, len(df), df.shape[1]))
        print(df.iloc[:14, :14].to_string(max_colwidth=24))
    print("\nPegale esta salida a Claude para que ajuste el parser.")


def num(v):
    return "null" if v is None else ("%.2f" % v).rstrip("0").rstrip(".")


def main():
    print("Actualizando ICC del INDEC (Gran Buenos Aires)...")
    hs = hojas(bajar())
    print("   Hojas: %s" % ", ".join(repr(h) for h in hs))

    if "--diagnostico" in sys.argv:
        return diagnostico(hs)

    # El archivo trae dos hojas: una con indices y otra con variaciones %.
    niveles = variaciones = None
    for nombre, df in hs.items():
        s = leer_transpuesta(df)
        if not s:
            continue
        if es_indice(s):
            if niveles is None or len(s) > len(niveles[1]):
                niveles = (nombre, s)
        else:
            if variaciones is None or len(s) > len(variaciones[1]):
                variaciones = (nombre, s)

    if not niveles and not variaciones:
        print("\n[ERROR] No se encontro ninguna hoja con Nivel general / Materiales /"
              " Mano de obra / Gastos generales.")
        diagnostico(hs)
        raise SystemExit("Se conserva el icc_indec_cache.js anterior.")

    if niveles:
        nombre, serie = niveles
        tipo = "indice"
        print("   Indices : hoja %r, %d meses (%s a %s)"
              % (nombre, len(serie), serie[0][0][:7], serie[-1][0][:7]))
        # La hoja de indices arranca en 2022; la de variaciones llega mas
        # atras. Se extiende el indice hacia el pasado dividiendo por cada
        # variacion mensual, para no perder esos años en el grafico.
        if variaciones:
            serie = extender_hacia_atras(serie, variaciones[1])
            print("   Empalme : con la hoja %r -> %d meses desde %s"
                  % (variaciones[0], len(serie), serie[0][0][:7]))
    else:
        nombre, serie = variaciones
        tipo = "variacion_mensual"
        print("   Solo hay variaciones: hoja %r, %d meses" % (nombre, len(serie)))

    hasta = serie[-1][0][:7]

    # ── Control contra el informe de junio 2026 ──
    mapa = {r[0][:7]: r for r in serie}
    ctrl = mapa.get(CONTROL["mes"])
    ok = "sin control (el mes de control no esta en la serie)"
    if ctrl:
        if tipo == "indice":
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
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Cualquier error inesperado se muestra completo: sin el traceback no
        # hay forma de saber que paso, y el cache anterior queda intacto.
        print("\n[ERROR] El script se cayo con una excepcion inesperada.")
        print("        Python: %s" % sys.version.split()[0])
        print("        Interprete: %s" % sys.executable)
        print("        Se conserva el icc_indec_cache.js anterior.\n")
        traceback.print_exc()
        sys.exit(1)
