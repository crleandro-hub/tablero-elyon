#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_isac_cache.py - Tablero Gestion Grupo Elyon
===================================================
Genera isac_cache.js con el ISAC (Indicador Sintetico de la Actividad de la
Construccion) del INDEC y sus 13 insumos.

De donde salen los datos
------------------------
El INDEC publica el informe "Indicadores de coyuntura de la actividad de la
construccion" en PDF una vez por mes, con unas 5 semanas de rezago. Ese PDF no
sirve para automatizar. Las mismas series salen limpias por la API de series de
tiempo de la Subsecretaria de Programacion Macroeconomica:

    https://apis.datos.gob.ar/series/api/series

que ademas suele adelantarse un mes al PDF (cuando este script se escribio, el
PDF llegaba hasta mayo-2026 y la API ya tenia junio-2026).

Lo que la API NO publica son los puestos de trabajo registrados ni la superficie
autorizada por permisos de edificacion. Esos dos cuadros se cargan a mano en
isac_manual.json (cuadros 3 y 4 del informe) y este script los embebe tal cual.

Salida: isac_cache.js
    window.ISAC_CACHE = {
      updated, source, hasta,
      serie:    [[fecha, original, desestacionalizada], ...]   desde 2012-01
      insumos:  { clave: [[fecha, indice], ...], ... }          ultimos 30 meses
      empleo:   { hasta, serie: [[fecha, puestos], ...] }
      permisos: { hasta, municipios, serie: [[fecha, m2, permisos], ...] }
    }

Uso:
    python update_isac_cache.py
"""

import json
import os
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "isac_cache.js")
MANUAL_PATH = os.path.join(BASE_DIR, "isac_manual.json")

API = "https://apis.datos.gob.ar/series/api/series"
TIMEOUT = 30
MESES_INSUMOS = 30        # alcanza para interanual y acumulado del año

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Nivel general: serie original y serie desestacionalizada
ID_NIVEL_ORIG = "33.2_ISAC_NIVELRAL_0_M_18_63"
ID_NIVEL_DESEST = "33.2_ISAC_SIN_EDAD_0_M_23_56"

# Insumos, serie original (distribucion 33.3). El orden es el del informe.
INSUMOS = [
    ("cemento",   "33.3_ISAC_CEMENAND_0_0_21_29"),
    ("hormigon",  "33.3_ISAC_HORMIADO_0_0_23_36"),
    ("hierro",    "33.3_ISAC_HIERRION_0_0_49_36"),
    ("ladrillos", "33.3_ISAC_LADRICOS_0_0_21_27"),
    ("cales",     "33.3_ISAC_CALESLES_0_0_10_7"),
    ("yeso",      "33.3_ISAC_YESOESO_0_0_9_54"),
    ("placas",    "33.3_ISAC_PLACAESO_0_0_19_5"),
    ("pisos",     "33.3_ISAC_PISOSCOS_0_0_37_22"),
    ("mosaicos",  "33.3_ISAC_MOSAIEOS_0_0_36_91"),
    ("sanitarios", "33.3_ISAC_ARTICICA_0_0_37_38"),
    ("pinturas",  "33.3_ISAC_PINTUION_0_0_31_13"),
    ("asfalto",   "33.3_ISAC_ASFALLTO_0_0_12_97"),
    ("resto",     "33.3_ISAC_RESTOSTO_0_0_10_50"),
]


def _get(url):
    """GET con reintento sin verificar certificado (algunas PC corporativas
    tienen el store de certificados desactualizado y falla el handshake)."""
    r = req.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read().decode("utf-8", "replace")


def bajar_csv(ids, limit, sort="asc"):
    """Devuelve [[fecha, v1, v2, ...], ...] para una lista de ids.
    La API corta las URLs largas, asi que se pide de a pocos ids."""
    url = "%s/?ids=%s&limit=%d&sort=%s&format=csv" % (API, ",".join(ids), limit, sort)
    txt = _get(url).strip()
    filas = []
    for linea in txt.splitlines()[1:]:          # se saltea el encabezado
        partes = linea.split(",")
        if len(partes) < 2:
            continue
        fila = [partes[0]]
        for p in partes[1:]:
            p = p.strip()
            fila.append(round(float(p), 4) if p else None)
        filas.append(fila)
    return filas


def num(v):
    return "null" if v is None else ("%g" % v)


def main():
    print("Actualizando ISAC desde apis.datos.gob.ar (INDEC / SSPM)...")

    # 1) Nivel general: original + desestacionalizada, serie completa
    serie = bajar_csv([ID_NIVEL_ORIG, ID_NIVEL_DESEST], 1000, "asc")
    if not serie:
        raise SystemExit("[ERROR] La API no devolvio el nivel general. "
                         "Se conserva el isac_cache.js anterior.")
    hasta = serie[-1][0][:7]
    print("   Nivel general : %d meses, hasta %s" % (len(serie), hasta))

    # 2) Insumos, de a 3 ids por request (URLs mas largas fallan)
    insumos = {}
    for i in range(0, len(INSUMOS), 3):
        grupo = INSUMOS[i:i + 3]
        filas = bajar_csv([sid for _, sid in grupo], MESES_INSUMOS, "desc")
        if not filas:
            print("   [AVISO] sin datos para: %s" % ", ".join(k for k, _ in grupo))
            continue
        for j, (clave, _) in enumerate(grupo):
            insumos[clave] = [[f[0], f[j + 1]] for f in filas if len(f) > j + 1]
    print("   Insumos       : %d de %d" % (len(insumos), len(INSUMOS)))

    # 3) Empleo y permisos: cuadros que la API no publica
    manual = {}
    if os.path.exists(MANUAL_PATH):
        with open(MANUAL_PATH, encoding="utf-8") as f:
            manual = json.load(f)
        print("   Empleo/permisos: isac_manual.json (%s)" %
              manual.get("informe", "sin fecha"))
    else:
        print("   [AVISO] falta isac_manual.json: sin empleo ni permisos.")

    # 4) Armar el .js
    fuente = "INDEC via apis.datos.gob.ar (SSPM)"
    filas_serie = ",\n".join(
        '    ["%s",%s,%s]' % (f[0], num(f[1]), num(f[2] if len(f) > 2 else None))
        for f in serie)

    bloques = []
    for clave, _ in INSUMOS:
        datos = insumos.get(clave)
        if not datos:
            continue
        cuerpo = ",".join('["%s",%s]' % (f[0], num(f[1])) for f in datos)
        bloques.append('    %s: [%s]' % (clave, cuerpo))

    js = (
        "/* ═══════════════════════════\n"
        "   isac_cache.js  -  Grupo Elyon\n"
        "   Generado por update_isac_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + "\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "   (Empleo y permisos se editan en isac_manual.json)\n"
        "═══════════════════════════ */\n"
        "window.ISAC_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  serie: [\n" + filas_serie + "\n  ],\n"
        "  insumos: {\n" + ",\n".join(bloques) + "\n  },\n"
        "  empleo: " + json.dumps(manual.get("empleo", {}), ensure_ascii=False) + ",\n"
        "  permisos: " + json.dumps(manual.get("permisos", {}), ensure_ascii=False) + ",\n"
        '  informe: ' + json.dumps(manual.get("informe", ""), ensure_ascii=False) + "\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    ult = serie[-1]
    print("\n[OK] isac_cache.js")
    print("     ISAC %s = %.1f (original) / %.1f (desest.)"
          % (hasta, ult[1] or 0, ult[2] or 0))


if __name__ == "__main__":
    main()
