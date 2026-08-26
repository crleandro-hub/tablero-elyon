#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_icc_cba_cache.py - Tablero Gestion Grupo Elyon
======================================================
Genera icc_cba_cache.js con el Indice del Costo de la Construccion de la
provincia de Cordoba (ICC-Cba), de la Direccion General de Estadistica y
Censos de Cordoba.

Que mide
--------
El costo de construir una vivienda social tipo de 50,25 m2 (cocina-comedor,
dos dormitorios y baño), con la metodologia vigente desde octubre de 2013.
Base 2012 = 100. Publica nivel general, tres rubros (materiales, mano de obra
y varios) y el valor del m2 en pesos.

Es el complemento local del CAC: el CAC es nacional y sobre un edificio tipo
de Buenos Aires; este es Cordoba y vivienda. Para obra en la provincia suele
ser la referencia que piden los comitentes.

De donde sale
-------------
Portal de datos abiertos de Cordoba (CKAN). El link de descarga redirige a un
S3 con firma que vence en una hora, asi que no sirve para leer en vivo desde
el navegador: hay que bajarlo desde aca y dejarlo cacheado.

    https://datosestadistica.cba.gov.ar/dataset/indice-de-costo-de-la-construccion

El CSV viene en latin-1, con punto y coma de separador, coma decimal y punto
de miles. Las primeras filas son titulos y la ultima es la firma de la fuente.

Salida: icc_cba_cache.js
    window.ICC_CBA_CACHE = {
      updated, source, hasta,
      serie: [[fecha, nivelGeneral, materiales, manoObra, varios, valorM2], ...]
    }

Uso:
    python update_icc_cba_cache.py
"""

import csv
import io
import json
import os
import re
import ssl
import sys
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from marca_cache import marcar, guardar_diagnostico, limpiar_diagnostico  # noqa: E402
CACHE_PATH = os.path.join(BASE_DIR, "icc_cba_cache.js")
TIMEOUT = 40

DATASET = "indice-de-costo-de-la-construccion"
PACKAGE_API = ("https://datosestadistica.cba.gov.ar/api/3/action/package_show?id=" + DATASET)

# Link directo al recurso "Indice general y rubros - valor m2" (CSV).
CSV_URL = ("https://datosestadistica.cba.gov.ar/dataset/"
           "14329433-faaf-48fb-90a0-3c141288622d/resource/"
           "afbec0bb-f309-4c09-947a-cd38e6b67867/download/"
           "icc-cba-indice-general-y-rubros-valor-m2.csv")

MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
         "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _get(url, binario=False):
    """GET con reintento sin verificar certificado."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/csv,application/json,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            crudo = resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            crudo = resp.read()
    return crudo if binario else crudo.decode("latin-1", "replace")


def url_del_recurso():
    """Resuelve el link del CSV por la API de CKAN. Si no responde, se usa el
    link directo: el id del recurso viene estable desde hace años, pero si
    algun dia lo cambian esto lo encuentra solo."""
    try:
        j = json.loads(_get(PACKAGE_API))
        for rec in j.get("result", {}).get("resources", []):
            fmt = (rec.get("format") or "").upper()
            desc = (rec.get("description") or "").lower()
            if fmt == "CSV" and "general" in desc and "rubro" in desc:
                print("   Recurso resuelto por la API de CKAN.")
                return rec["url"]
    except Exception:
        pass
    return CSV_URL


def _num(txt, sep=None):
    """'4.583,74' -> 4583.74   |   '28691,52' -> 28691.52   |   '' -> None

    NO se decide por el separador de columnas. Se decidia asi y salio caro: el
    portal paso a publicar el CSV separado por comas y con los numeros entre
    comillas ("28691,52"), el separador elegido fue "," y cada numero quedo
    partido al medio. El valor del m2 de junio, que son $971.978,35, quedo
    guardado como 4.

    Ahora se mira el contenido, que es lo unico confiable:
      · si hay coma, la coma es el decimal (convencion local) y el punto separa
        miles -> "4.583,74" y "28691,52";
      · si solo hay puntos y el ultimo grupo tiene 3 digitos, son miles
        -> "971.978" es 971978, no 971,978;
      · cualquier otro punto es decimal -> "28691.52".
    El separador se sigue recibiendo por compatibilidad, pero no se usa."""
    txt = (txt or "").strip().strip('"').replace("%", "").replace("\xa0", "")
    txt = txt.replace(" ", "")
    if not txt:
        return None
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    elif txt.count(".") >= 1:
        entero, _, ultimo = txt.rpartition(".")
        if len(ultimo) == 3 and entero.replace(".", "").replace("-", "").isdigit():
            txt = txt.replace(".", "")          # 971.978 -> 971978
    try:
        return float(txt)
    except ValueError:
        return None


def _fecha(txt):
    """'oct-13' -> '2013-10-01'. Devuelve None si no es un periodo.

    Se aceptan tambien los formatos que aparecen cuando el portal rehace el
    dataset: '2026-06', '2026-06-01', '06/2026' y 'junio 2026'."""
    txt = (txt or "").strip().strip('"')

    m = re.match(r"^\s*(\d{4})-(\d{1,2})(?:-\d{1,2})?\s*$", txt)
    if m:
        return "%04d-%02d-01" % (int(m.group(1)), int(m.group(2)))

    m = re.match(r"^\s*(\d{1,2})/(\d{4})\s*$", txt)
    if m:
        return "%04d-%02d-01" % (int(m.group(2)), int(m.group(1)))

    m = re.match(r"^\s*([a-zA-Z]{3,10})[\s\-/]*(\d{2,4})\s*$", txt)
    if not m:
        return None
    mes = MESES.get(m.group(1)[:3].lower())
    if not mes:
        return None
    anio = int(m.group(2))
    if anio < 100:
        anio += 2000
    return "%04d-%02d-01" % (anio, mes)


def _parsear_con(csv_txt, sep):
    """Columnas: Periodo | NG | Materiales | Mano de obra | Varios |
                 4 columnas de variacion mensual | Valor del m2

    Se usa el modulo csv y no un split() a mano porque el portal ahora
    entrecomilla los valores: con "28691,52" como campo, partir por comas lo
    corta al medio. csv.reader respeta las comillas y devuelve el numero
    entero, tal como esta publicado."""
    try:
        lector = csv.reader(io.StringIO(csv_txt), delimiter=sep, quotechar='"')
        lineas = list(lector)
    except Exception:
        lineas = [l.split(sep) for l in csv_txt.splitlines()]

    filas = []
    for partes in lineas:
        if len(partes) < 6:
            continue
        f = _fecha(partes[0])
        if not f:
            continue
        ng = _num(partes[1])
        if ng is None:
            continue
        filas.append([
            f, ng, _num(partes[2]), _num(partes[3]), _num(partes[4]),
            _num(partes[9]) if len(partes) > 9 else None,
        ])
    filas.sort(key=lambda r: r[0])
    return filas


def parsear(csv_txt):
    """El portal ya cambio de maqueta otras veces, asi que no se da por sentado
    el separador: se prueban los tres habituales y gana el que devuelve mas
    meses. Con 0 filas en los tres, el CSV cambio de verdad y hay que mirarlo."""
    mejor, mejor_sep = [], ";"
    for sep in (";", ",", "\t"):
        filas = _parsear_con(csv_txt, sep)
        if len(filas) > len(mejor):
            mejor, mejor_sep = filas, sep
    if mejor and mejor_sep != ";":
        print("   El CSV vino separado por %r (antes era ';')."
              % mejor_sep)
    return mejor


def num(v):
    """2 decimales sin ceros al pedo. %g no sirve: corta a 6 cifras
    significativas y el valor del m2 ya pasa el millon de pesos."""
    if v is None:
        return "null"
    return ("%.2f" % v).rstrip("0").rstrip(".")


def _serie_del_cache():
    """Lo que ya esta guardado: {fecha: [ng, mat, mo, varios, m2]}."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return {}
    out = {}
    for f_, resto in re.findall(r'\["(\d{4}-\d{2}-\d{2})",([^\]]*)\]', txt):
        vals = []
        for t in resto.split(","):
            t = t.strip()
            vals.append(None if t in ("null", "") else float(t))
        out[f_] = vals
    return out


def controlar(serie, crudo):
    """Aborta si lo parseado no tiene sentido, conservando el cache anterior.

    El control que importa es el ultimo: un mes que YA estaba guardado tiene
    que volver a dar el mismo numero. Si no da, no cambiaron los datos sino la
    forma de leerlos, y eso es exactamente lo que paso cuando el portal empezo
    a entrecomillar los valores: el nivel general de junio siguio pareciendo
    razonable (28691) pero el valor del m2 se desplomo de $971.978,35 a $4 y
    nadie se entero hasta mirar el tablero.

    Es el control mas barato y el mas potente que hay para un scraper: el
    pasado no cambia."""
    ult = serie[-1]
    if not ult[1] or ult[1] < 100:
        guardar_diagnostico(BASE_DIR, "icc_cba", crudo, ".csv")
        raise SystemExit("[ERROR] El nivel general de %s dio %s, que no puede ser "
                         "(la serie va por los 28.000). Quedo _icc_cba_diagnostico.csv. "
                         "Se conserva el cache anterior." % (ult[0][:7], ult[1]))

    if ult[5] is not None and ult[5] < 100000:
        guardar_diagnostico(BASE_DIR, "icc_cba", crudo, ".csv")
        raise SystemExit("[ERROR] El valor del m2 de %s dio $%s y ya viene arriba del "
                         "millon: el CSV cambio de formato. Quedo "
                         "_icc_cba_diagnostico.csv. Se conserva el cache anterior."
                         % (ult[0][:7], ult[5]))

    previo = _serie_del_cache()
    nombres = ["nivel general", "materiales", "mano de obra", "varios", "valor del m2"]
    difs = []
    for fila in serie:
        viejo = previo.get(fila[0])
        if not viejo:
            continue
        for i in range(5):
            a_, b_ = viejo[i] if i < len(viejo) else None, fila[i + 1]
            if a_ is None or b_ is None or a_ == 0:
                continue
            if abs(b_ / a_ - 1) > 0.01:
                difs.append((fila[0][:7], nombres[i], a_, b_))
    if difs:
        guardar_diagnostico(BASE_DIR, "icc_cba", crudo, ".csv")
        detalle = "; ".join("%s %s: %s -> %s" % d for d in difs[:4])
        raise SystemExit(
            "[ERROR] %d valor(es) de meses YA guardados cambiaron al releer el CSV. "
            "El pasado no cambia: lo que cambio es el formato del archivo. %s. "
            "Quedo _icc_cba_diagnostico.csv. Se conserva el cache anterior."
            % (len(difs), detalle))


def main():
    print("Actualizando ICC de Cordoba (Estadistica y Censos de Cordoba)...")

    url = url_del_recurso()
    crudo = _get(url)
    serie = parsear(crudo)

    if len(serie) < 12:
        guardar_diagnostico(BASE_DIR, "icc_cba", crudo, ".csv")
        raise SystemExit("[ERROR] El CSV no trajo una serie usable (%d filas). "
                         "Quedo _icc_cba_diagnostico.csv con lo que llego. "
                         "Se conserva el icc_cba_cache.js anterior." % len(serie))

    controlar(serie, crudo)
    limpiar_diagnostico(BASE_DIR, "icc_cba")
    hasta = serie[-1][0][:7]
    fuente = "Direccion General de Estadistica y Censos de Cordoba"

    cuerpo = ",\n".join(
        '    ["%s",%s,%s,%s,%s,%s]' % (r[0], num(r[1]), num(r[2]), num(r[3]),
                                       num(r[4]), num(r[5]))
        for r in serie)

    js = (
        "/* ═══════════════════════════\n"
        "   icc_cba_cache.js  -  Grupo Elyon\n"
        "   Generado por update_icc_cba_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + " (datos abiertos, CKAN)\n"
        "   Vivienda social tipo de 50,25 m2 - base 2012 = 100\n"
        "   Columnas: fecha, nivel general, materiales, mano de obra, varios, valor m2\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.ICC_CBA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  serie: [\n" + cuerpo + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    u = serie[-1]
    print("\n[OK] icc_cba_cache.js")
    print("     %d meses, de %s a %s" % (len(serie), serie[0][0][:7], hasta))
    print("     Nivel general %s = %s  |  valor m2 $%s"
          % (hasta, ("%.2f" % u[1]), ("{:,.0f}".format(u[5] or 0).replace(",", "."))))


if __name__ == "__main__":
    try:
        main()
        marcar(CACHE_PATH)
    except SystemExit as e:
        if e.code:
            marcar(CACHE_PATH, e.code)
        raise
