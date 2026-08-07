#!/usr/bin/env python3
"""
update_cac_cache.py - Tablero Gestion Grupo Elyon
=====================================================
Lee el Excel local del Indice CAC (Camara Argentina de la Construccion /
INDEC, serie "Indicador de la variacion del costo de un edificio tipo en
Capital Federal") y regenera cac_cache.js con la serie completa correcta,
para que tablero_elyon.html la cargue automaticamente sin depender del
arrastrar-y-soltar manual ni de datos embebidos desactualizados.

COMO EJECUTAR
-------------
  1. Descarga / actualiza el Excel del CAC en la carpeta del tablero
     (podes pisar el archivo existente o dejar uno nuevo con "CAC" en
     el nombre).
  2. Corre:
        python update_cac_cache.py
  3. Refresca tablero_elyon.html en el navegador (Ctrl+F5).

Que hace distinto de la carga manual anterior
----------------------------------------------
El array de datos embebidos que traia el tablero (CAC_EMBEDDED) tenia un
error sistematico: el valor de "CAC General" (Costo de Construccion)
estaba desplazado UN MES hacia adelante respecto de Materiales y Mano de
Obra (por ejemplo, marzo mostraba el General de abril). Este script arma
cada registro mensual leyendo, dentro del mismo bloque de 3 filas del
Excel del INDEC, la fila que esta INMEDIATAMENTE ANTES de la fecha
("Costo de Construccion") y la que esta INMEDIATAMENTE DESPUES
("Mano de Obra") -- que es la estructura real verificada sobre el
archivo fuente.

Tambien limpia valores mal cargados en el Excel original (por ejemplo,
celdas de texto tipo "f58,3" en lugar de 58.3) en vez de descartarlos
como N/D.

ESTRUCTURA DEL EXCEL CAC (INDEC/CAMARCO) -- verificada sobre el archivo real
----------------------------------------------------------------------------
Cada mes ocupa 3 filas consecutivas:
    fila i   : [D="Costo de Construccion"] [F=indice General del mes]
    fila i+1 : [B=fecha (1er dia del mes)] [D="Materiales"] [F=indice Materiales]
    fila i+2 : [D="Mano de Obra"]          [F=indice Mano de Obra]

Columnas (0-based, segun pandas/openpyxl con header=None):
    A=0  B=1(fecha)  C=2  D=3(denominacion)  E=4  F=5(indice)  G=6(var. %)
"""

import json
import os
import re
import sys
from datetime import datetime

import pandas as pd

# -- CONFIGURACION ------------------------------------------------------
# Carpeta del tablero (donde vive este script, tablero_elyon.html y el Excel)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Nombre exacto conocido del archivo. Si no existe, se busca automaticamente
# cualquier .xls/.xlsx que contenga "cac" o "indicador" en el nombre dentro
# de esta carpeta (por si el usuario lo re-descarga con otro nombre cada mes).
CAC_XLS_DEFAULT = os.path.join(BASE_DIR, "Indicador CAC_serie histórica.xls")

CACHE_JS_PATH = os.path.join(BASE_DIR, "cac_cache.js")

COL_FECHA = 1   # B
COL_DEN = 3     # D
COL_IDX = 5     # F


# -- LOCALIZAR EL ARCHIVO EXCEL ------------------------------------------
def find_cac_excel():
    if os.path.exists(CAC_XLS_DEFAULT):
        return CAC_XLS_DEFAULT

    candidates = []
    try:
        for name in os.listdir(BASE_DIR):
            low = name.lower()
            if not (low.endswith(".xls") or low.endswith(".xlsx")):
                continue
            if "cac" in low or "indicador" in low:
                candidates.append(os.path.join(BASE_DIR, name))
    except FileNotFoundError:
        pass

    candidates = sorted(set(candidates), key=os.path.getmtime, reverse=True)
    return candidates[0] if candidates else None


# -- LECTURA DEL EXCEL (.xls o .xlsx) ------------------------------------
def read_raw(path):
    ext = os.path.splitext(path)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"
    try:
        df = pd.read_excel(path, header=None, engine=engine)
    except ImportError as e:
        sys.exit(
            "[ERROR] Falta el paquete '" + engine + "' para leer archivos " + ext + ".\n"
            "        Instalalo con:  pip install " + engine + "\n"
            "        Detalle: " + str(e)
        )
    return df.values.tolist()


# -- LIMPIEZA / PARSEO NUMERICO ROBUSTO -----------------------------------
NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def to_num(v):
    """Convierte celdas numericas o con errores de tipeo (ej: 'f58,3') a float."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if pd.isna(v) else float(v)
    s = str(v).strip().strip("'").strip('"')
    if not s:
        return None
    m = NUM_RE.search(s)
    if not m:
        return None
    raw = m.group(0).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def norm(v):
    return str(v if v is not None else "").strip().lower()


def to_month_start(v):
    """Convierte fecha (datetime, string o serial Excel) al 1er dia del mes."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return datetime(v.year, v.month, 1)
    if isinstance(v, (int, float)):
        try:
            d = pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))
            return datetime(d.year, d.month, 1)
        except Exception:
            return None
    try:
        d = pd.to_datetime(v, dayfirst=True)
        return datetime(d.year, d.month, 1)
    except Exception:
        return None


# -- PARSEO DEL BLOQUE DE 3 FILAS POR MES ---------------------------------
def parse_cac(raw_rows):
    """
    Detecta filas de 'Materiales' con fecha en col B, y arma cada registro
    mensual usando la fila INMEDIATA ANTERIOR ('Costo de Construccion') y
    la fila INMEDIATA POSTERIOR ('Mano de Obra') dentro del mismo bloque.
    """
    n = len(raw_rows)
    mat_rows = []
    for i, row in enumerate(raw_rows):
        if len(row) <= COL_DEN:
            continue
        den = norm(row[COL_DEN])
        fecha_cell = row[COL_FECHA] if len(row) > COL_FECHA else None
        fecha = to_month_start(fecha_cell)
        if "material" in den and fecha is not None:
            mat_rows.append((i, fecha))

    if len(mat_rows) < 3:
        sys.exit(
            "[ERROR] Estructura no reconocida en el Excel. "
            "Filas de 'Materiales' con fecha detectadas: " + str(len(mat_rows)) + ". "
            "Verifica que sea el archivo del CAC del INDEC/CAMARCO sin modificar."
        )

    registros = []
    warnings = []
    for i, fecha in mat_rows:
        mat_row = raw_rows[i]
        gen_row = raw_rows[i - 1] if i - 1 >= 0 else []
        mo_row = raw_rows[i + 1] if i + 1 < n else []

        gen_ok = "costo" in norm(gen_row[COL_DEN]) if len(gen_row) > COL_DEN else False
        mo_ok = "mano" in norm(mo_row[COL_DEN]) if len(mo_row) > COL_DEN else False

        mat = to_num(mat_row[COL_IDX]) if len(mat_row) > COL_IDX else None
        gen = to_num(gen_row[COL_IDX]) if gen_ok and len(gen_row) > COL_IDX else None
        mo = to_num(mo_row[COL_IDX]) if mo_ok and len(mo_row) > COL_IDX else None

        if not gen_ok:
            warnings.append("  - " + fecha.strftime("%Y-%m") + ": no se encontro 'Costo de Construccion' inmediatamente antes de la fila de fecha.")
        if not mo_ok:
            warnings.append("  - " + fecha.strftime("%Y-%m") + ": no se encontro 'Mano de Obra' inmediatamente despues de la fila de fecha.")

        checks = (
            ("General", gen_row[COL_IDX] if len(gen_row) > COL_IDX else None),
            ("Materiales", mat_row[COL_IDX] if len(mat_row) > COL_IDX else None),
            ("Mano de Obra", mo_row[COL_IDX] if len(mo_row) > COL_IDX else None),
        )
        for label, cell in checks:
            is_num = isinstance(cell, (int, float)) and not (isinstance(cell, float) and pd.isna(cell))
            if cell is not None and not is_num:
                warnings.append("  - " + fecha.strftime("%Y-%m") + ": valor '" + str(cell) + "' en " + label + " no es numerico puro, se limpio automaticamente.")

        registros.append({"fecha": fecha, "gen": gen, "mat": mat, "mo": mo})

    registros.sort(key=lambda r: r["fecha"])

    faltantes = []
    for a, b in zip(registros, registros[1:]):
        meses_dif = (b["fecha"].year - a["fecha"].year) * 12 + (b["fecha"].month - a["fecha"].month)
        if meses_dif > 1:
            faltantes.append(
                "  - Salto entre " + a["fecha"].strftime("%Y-%m") + " y " + b["fecha"].strftime("%Y-%m")
                + " (" + str(meses_dif - 1) + " mes/es sin datos)."
            )

    return registros, warnings, faltantes


# -- ESCRITURA DEL CACHE JS ------------------------------------------------
def write_cache(registros, source_path):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    serie = [
        [
            r["fecha"].strftime("%Y-%m-%d"),
            r["gen"] if r["gen"] is not None else None,
            r["mat"] if r["mat"] is not None else None,
            r["mo"] if r["mo"] is not None else None,
        ]
        for r in registros
    ]

    lines = [
        "/* -----------------------------------------------------------------",
        "   cac_cache.js  -  Grupo Elyon  |  Generado automaticamente",
        "   Generado: " + ts,
        "   Fuente: " + os.path.basename(source_path),
        "   Registros: " + str(len(serie)) + "  (" + serie[0][0] + " a " + serie[-1][0] + ")",
        "   Formato por registro: [fecha, CAC General, Materiales, Mano de Obra]",
        "----------------------------------------------------------------- */",
        "window.CAC_CACHE = {",
        "  updated: \"" + ts + "\",",
        "  source: " + json.dumps(os.path.basename(source_path), ensure_ascii=False) + ",",
        "  serie: " + json.dumps(serie, ensure_ascii=False),
        "};",
    ]
    content = "\n".join(lines) + "\n"
    with open(CACHE_JS_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def leer_ultimo_mes_cache():
    """Ultimo mes ya registrado en cac_cache.js (para detectar si hubo cambios)."""
    try:
        with open(CACHE_JS_PATH, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None
    fechas = re.findall(r'\["(\d{4}-\d{2}-\d{2})"', txt)
    return fechas[-1] if fechas else None


def main():
    print("Actualizando cac_cache.js desde el Excel local del CAC...")
    mes_previo = leer_ultimo_mes_cache()
    path = find_cac_excel()
    if not path:
        sys.exit(
            "[ERROR] No se encontro ningun archivo .xls/.xlsx del CAC en la carpeta.\n"
            "        Buscado en: " + BASE_DIR + "\n"
            "        Coloca ahi el Excel descargado de CAMARCO/INDEC (nombre con "
            "'CAC' o 'Indicador')."
        )

    print("[OK] Archivo detectado: " + os.path.basename(path))
    raw_rows = read_raw(path)
    registros, warnings, faltantes = parse_cac(raw_rows)

    write_cache(registros, path)

    print(
        "[OK] cac_cache.js actualizado -- " + str(len(registros)) + " meses ("
        + registros[0]["fecha"].strftime("%Y-%m") + " a " + registros[-1]["fecha"].strftime("%Y-%m") + ")"
    )
    ultimo = registros[-1]
    print(
        "     Ultimo mes: " + ultimo["fecha"].strftime("%Y-%m")
        + "  General=" + str(ultimo["gen"])
        + "  Materiales=" + str(ultimo["mat"])
        + "  Mano de Obra=" + str(ultimo["mo"])
    )

    if warnings:
        print("\n[AVISO] " + str(len(warnings)) + " observacion(es) durante el parseo:")
        for w in warnings:
            print(w)
    if faltantes:
        print("\n[AVISO] Huecos detectados en la serie:")
        for w in faltantes:
            print(w)
    if not warnings and not faltantes:
        print("[OK] Sin observaciones: estructura y datos consistentes.")

    # -- Estado: hubo cambios? el Excel esta atrasado? -------------------
    mes_nuevo = ultimo["fecha"].strftime("%Y-%m-%d")
    if mes_previo is None:
        print("\n[CAMBIO] Cache generado por primera vez. Ultimo mes: " + mes_nuevo)
    elif mes_previo != mes_nuevo:
        print("\n[CAMBIO] Se incorporaron datos nuevos: " + mes_previo + " -> " + mes_nuevo)
    else:
        print("\n[SIN CAMBIOS] El Excel no trae meses nuevos (ultimo: " + mes_nuevo + ").")

    dias = (datetime.now() - ultimo["fecha"]).days
    mes_legible = ultimo["fecha"].strftime("%m/%Y")
    if dias > 70:
        print("[EXCEL DESACTUALIZADO] El ultimo dato del Excel es de " + mes_legible
              + " (" + str(dias) + " dias). Descarga la serie historica actualizada "
              "desde camarco.org.ar/indicadores y pisa el archivo en esta carpeta.")
    else:
        print("[EXCEL AL DIA] Ultimo dato: " + mes_legible + " (" + str(dias) + " dias).")


if __name__ == "__main__":
    main()
