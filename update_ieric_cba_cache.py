#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_ieric_cba_cache.py - Tablero Gestion Grupo Elyon
=======================================================
Genera ieric_cba_cache.js con tres series de la industria de la construccion
de la PROVINCIA DE CORDOBA que publica el IERIC:

    puestos   Puestos de trabajo registrados        desde jun-2007
    salario   Salario promedio mensual pagado       desde jun-2007
    empresas  Empresas constructoras en actividad   desde ene-2005

Las tres traen Cordoba y Total Pais lado a lado, y las variaciones ya
calculadas por la fuente. El tablero no recalcula nada: muestra lo publicado.

Por que estas tres
------------------
El tablero ya tiene empleo de la construccion del INDEC, pero es total pais y
sale de SIPA. Estas son de Cordoba y salen de OSPECON + Seguro de Vida
Obligatorio, o sea del padron de la propia industria. Son universos distintos:
para mayo de 2026 el INDEC da 377.438 puestos y el IERIC 355.962 a nivel pais.
NO se pueden encadenar ni comparar en niveles. Van como bloques separados.

El salario promedio es el efectivamente pagado, no el basico de convenio.
Contra la escala UOCRA que ya esta en el tablero, muestra la brecha entre lo
que dice el convenio y lo que se liquida.

De donde sale
-------------
    https://www.ieric.org.ar/series_estadisticas/cordoba/

OJO CON LAS URLs: el IERIC sirve los archivos desde /wp-content/uploads/AAAA/MM/
donde AAAA/MM es la fecha en que subieron el archivo, y ESE TRAMO CAMBIA cuando
lo refrescan (hoy puestos y salario estan en 2026/07 y hubo archivos en 2020/01).
Si se hardcodea la URL, el dia que actualicen el script sigue bajando la version
vieja SIN DAR ERROR, que es la peor forma de romperse. Por eso los links se
resuelven leyendo la pagina en cada corrida.

Formato de los .xls
-------------------
Son BIFF viejo (OLE2), hacen falta xlrd. Las tres planillas comparten formato:

    fila 0-1   titulo y subtitulo (ahi esta la unidad)
    fila 2     vacia
    fila 3-5   encabezado en varios niveles
    fila 6+    datos, con la fecha como fecha de Excel en la columna 0
    al pie     filas "Nota: ..." y una fila "Fuente: ..."

Las variaciones que todavia no se pueden calcular (los primeros 12 meses de
cada serie) vienen con el texto "..." en vez de vacias.

Control de integridad
---------------------
Antes de escribir, recalcula la variacion interanual a partir de los niveles y
la compara contra la publicada. Si no coinciden, el parseo se corrio de columna:
aborta y deja el cache anterior intacto. Mismo criterio que update_construya.

Tambien aborta si la serie nueva tiene menos meses que la que ya esta cacheada,
para que una descarga a medias no pise datos buenos.

Salida: ieric_cba_cache.js

Uso:
    python update_ieric_cba_cache.py
    python update_ieric_cba_cache.py --diagnostico   (muestra y no escribe)
"""

import os
import re
import ssl
import sys
import urllib.request as req
from datetime import datetime
from urllib.parse import urljoin

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "ieric_cba_cache.js")

PAGINA = "https://www.ieric.org.ar/series_estadisticas/cordoba/"
TIMEOUT = 60

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Que archivo alimenta cada bloque. El patron se busca en el nombre del
# archivo, no en la ruta, justamente porque la ruta lleva la fecha de subida.
SERIES = [
    {
        "clave": "puestos",
        "patron": r"Puestos-de-trabajo-Cordoba",
        "titulo": "Puestos de trabajo registrados",
        "unidad": "puestos",
        "cols": 9,   # fecha + 2 niveles + 3 var Cba + 3 var pais
    },
    {
        "clave": "salario",
        "patron": r"Salario-Promedio-Cordoba",
        "titulo": "Salario promedio de la construccion",
        "unidad": "pesos por mes",
        "cols": 9,
    },
    {
        "clave": "empresas",
        "patron": r"Empresas-al-dia-Cordoba",
        "titulo": "Empresas constructoras en actividad",
        "unidad": "empresas",
        "cols": 5,   # fecha + 2 niveles + 2 var interanual
    },
]

# Tolerancia al comparar la variacion interanual publicada contra la
# recalculada. La fuente redondea, asi que no dan identicas.
TOLERANCIA_PP = 0.6
MIN_MESES = 100


# ─────────────────────────────────────────────────────────────────────────
#  Descarga
# ─────────────────────────────────────────────────────────────────────────

def _get(url):
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/vnd.ms-excel,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
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


def resolver_links(html):
    """{clave: url} resolviendo por el nombre del archivo."""
    hrefs = re.findall(r"""href\s*=\s*["']([^"']+\.xlsx?)["']""", html, re.I)
    hrefs = [urljoin(PAGINA, h.strip()) for h in hrefs]

    encontrados = {}
    for spec in SERIES:
        rx = re.compile(spec["patron"], re.I)
        for h in hrefs:
            nombre = h.rsplit("/", 1)[-1]
            if rx.search(nombre):
                encontrados[spec["clave"]] = h
                break
    return encontrados


# ─────────────────────────────────────────────────────────────────────────
#  Lectura del .xls
# ─────────────────────────────────────────────────────────────────────────

def leer_hoja_xls(datos):
    """Primera hoja con datos -> (filas, nombre). Cada celda: str, float,
    'AAAA-MM-DD' o None. El IERIC deja una hoja 'ESRI_MAPINFO_SHEET' vacia
    al final de cada archivo, asi que hay que elegir la que tenga filas."""
    import xlrd
    wb = xlrd.open_workbook(file_contents=datos)

    mejor, mejor_nombre = None, None
    for nombre in wb.sheet_names():
        sh = wb.sheet_by_name(nombre)
        if sh.nrows == 0:
            continue
        filas = []
        for i in range(sh.nrows):
            fila = []
            for j in range(sh.ncols):
                c = sh.cell(i, j)
                v = c.value
                if c.ctype == xlrd.XL_CELL_DATE:
                    y, mo, d = xlrd.xldate_as_tuple(v, wb.datemode)[:3]
                    v = "%04d-%02d-%02d" % (y, mo, d)
                elif c.ctype == xlrd.XL_CELL_EMPTY:
                    v = None
                elif isinstance(v, str):
                    v = v.strip()
                    # "..." es como la fuente marca "todavia no calculable"
                    if v in ("", "...", "-", "s/d"):
                        v = None
                fila.append(v)
            filas.append(fila)
        if mejor is None or len(filas) > len(mejor):
            mejor, mejor_nombre = filas, nombre
    if mejor is None:
        raise ValueError("El archivo no tiene ninguna hoja con datos")
    return mejor, mejor_nombre


def _es_fecha(v):
    return isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", v)


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    try:
        return float(s)
    except ValueError:
        pass
    try:                                    # por si alguna vez viene es-AR
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def parsear(filas, cols):
    """Devuelve (serie, titulo, notas, fuente).

    serie: [[AAAA-MM-01, valor Cba, valor pais, ...variaciones...], ...]

    El titulo son las filas de arriba de todo que ocupan UNA sola celda. Ese
    test es el que separa el titulo del encabezado de la tabla: la fila
    'Periodo | Provincia de Cordoba | Total Pais | ...' tiene varias celdas
    llenas y no se confunde con el titulo.
    """
    serie, notas, fuente, titulo = [], [], "", ""

    for fila in filas:
        if not fila:
            continue
        c0 = fila[0]

        if _es_fecha(c0):
            fila = list(fila) + [None] * (cols - len(fila))
            valores = [_num(v) for v in fila[1:cols]]
            if valores[0] is None:          # sin nivel para Cordoba no sirve
                continue
            serie.append([c0[:8] + "01"] + valores)
            continue

        if not isinstance(c0, str) or not c0.strip():
            continue
        txt = " ".join(c0.split())
        llenas = [v for v in fila if v is not None and str(v).strip() != ""]

        if txt.lower().startswith("fuente:"):
            fuente = txt[7:].strip()
        elif txt.lower().startswith("nota:"):
            notas.append(txt[5:].strip())
        elif not serie and len(llenas) == 1 and len(titulo) < 200:
            titulo = (titulo + " " + txt).strip()

    serie.sort(key=lambda r: r[0])
    return serie, titulo, notas, fuente


# ─────────────────────────────────────────────────────────────────────────
#  Control de integridad
# ─────────────────────────────────────────────────────────────────────────

def col_interanual(cols):
    """Indice, dentro de la fila de la serie, de la var. interanual de Cordoba.
    Con 9 columnas el orden es nivel Cba, nivel pais, mensual, interanual,
    acumulada; con 5 es nivel Cba, nivel pais, interanual."""
    return 4 if cols == 9 else 3


def control_interanual(serie, cols, clave):
    """Recalcula la interanual desde los niveles y la compara con la publicada.
    Si no cierran, el parseo se corrio de columna."""
    idx = col_interanual(cols)
    comparados = malos = 0
    peor = (0.0, None)

    for i in range(12, len(serie)):
        publicada = serie[i][idx]
        hoy, hace12 = serie[i][1], serie[i - 12][1]
        if publicada is None or not hoy or not hace12:
            continue
        # Los meses tienen que estar a 12 de distancia, no solo a 12 filas
        if serie[i][0][:4] != "%04d" % (int(serie[i - 12][0][:4]) + 1) \
                or serie[i][0][5:7] != serie[i - 12][0][5:7]:
            continue
        calculada = (hoy / hace12 - 1.0) * 100.0
        dif = abs(calculada - publicada)
        comparados += 1
        if dif > peor[0]:
            peor = (dif, serie[i][0])
        if dif > TOLERANCIA_PP:
            malos += 1

    if comparados < 12:
        raise SystemExit(
            "[ERROR] %s: no se pudo controlar la interanual (%d comparaciones). "
            "Se conserva el cache anterior." % (clave, comparados))

    if malos > max(2, comparados * 0.02):
        raise SystemExit(
            "[ERROR] %s: la variacion interanual publicada no coincide con la "
            "que sale de los niveles en %d de %d meses (peor: %.2f pp en %s). "
            "Lo mas probable es que el IERIC haya cambiado el orden de las "
            "columnas. Se conserva el cache anterior."
            % (clave, malos, comparados, peor[0], peor[1]))

    return comparados, peor


def meses_cacheados(clave):
    """Cuantos meses tiene hoy el cache para esa serie, para no pisarlo con
    menos. Si no se puede leer, devuelve 0 y el control simplemente no aplica."""
    if not os.path.exists(CACHE_PATH):
        return 0
    try:
        txt = open(CACHE_PATH, encoding="utf-8").read()
    except Exception:
        return 0

    arranque = re.search(r"\n  %s:\s*\{" % re.escape(clave), txt)
    if not arranque:
        return 0
    resto = txt[arranque.end():]
    # El bloque termina donde arranca el siguiente, o al final del archivo.
    siguiente = re.search(r"\n  [a-zA-Z_]+:\s*\{", resto)
    if siguiente:
        resto = resto[:siguiente.start()]
    return len(re.findall(r'\["\d{4}-\d{2}-01"', resto))


# ─────────────────────────────────────────────────────────────────────────
#  Salida
# ─────────────────────────────────────────────────────────────────────────

def num(v):
    if v is None:
        return "null"
    return ("%.4f" % v).rstrip("0").rstrip(".")


def js_str(s):
    return '"' + (s or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


def bloque_js(clave, d):
    filas = ",\n".join(
        "      [%s,%s]" % (js_str(r[0]), ",".join(num(v) for v in r[1:]))
        for r in d["serie"])
    notas = ", ".join(js_str(n) for n in d["notas"])
    return (
        "  %s: {\n"
        "    titulo: %s,\n"
        "    unidad: %s,\n"
        "    hasta: %s,\n"
        "    provisorio: %s,\n"
        "    fuente: %s,\n"
        "    archivo: %s,\n"
        "    notas: [%s],\n"
        "    serie: [\n%s\n    ]\n"
        "  }"
    ) % (clave, js_str(d["titulo"]), js_str(d["unidad"]), js_str(d["hasta"]),
         "true" if d["provisorio"] else "false",
         js_str(d["fuente"]), js_str(d["archivo"]), notas, filas)


# ─────────────────────────────────────────────────────────────────────────

def main():
    diagnostico = "--diagnostico" in sys.argv

    print("Actualizando series de Cordoba del IERIC...")

    try:
        import xlrd  # noqa: F401
    except ImportError:
        raise SystemExit("[ERROR] Falta xlrd, que hace falta para los .xls "
                         "viejos del IERIC. Instalalo con: pip install xlrd")

    html = _get(PAGINA).decode("utf-8", "replace")
    links = resolver_links(html)

    faltan = [s["clave"] for s in SERIES if s["clave"] not in links]
    if faltan:
        raise SystemExit(
            "[ERROR] No se encontro el link de: %s. El IERIC pudo haber "
            "cambiado el nombre de los archivos o la pagina. Corre "
            "probar_ieric_cordoba.py para ver que hay publicado hoy. "
            "Se conserva el cache anterior." % ", ".join(faltan))

    datos = {}
    for spec in SERIES:
        clave = spec["clave"]
        url = links[clave]
        print("   %-9s %s" % (clave, url.rsplit("/", 1)[-1]))

        filas, hoja = leer_hoja_xls(_get(url))
        serie, titulo, notas, fuente = parsear(filas, spec["cols"])

        if len(serie) < MIN_MESES:
            raise SystemExit(
                "[ERROR] %s: solo %d meses, se esperaban al menos %d. "
                "Se conserva el cache anterior." % (clave, len(serie), MIN_MESES))

        previos = meses_cacheados(clave)
        if previos and len(serie) < previos - 1:
            raise SystemExit(
                "[ERROR] %s: la descarga trajo %d meses y el cache ya tiene %d. "
                "No se pisa. Se conserva el cache anterior."
                % (clave, len(serie), previos))

        comparados, peor = control_interanual(serie, spec["cols"], clave)

        datos[clave] = {
            "titulo": titulo or spec["titulo"],
            "unidad": spec["unidad"],
            "hasta": serie[-1][0][:7],
            "provisorio": any("provisorio" in n.lower() for n in notas),
            "fuente": fuente or "IERIC",
            "archivo": url,
            "notas": notas,
            "serie": serie,
            "_hoja": hoja,
            "_control": (comparados, peor),
        }

    for clave, d in datos.items():
        comparados, peor = d["_control"]
        u = d["serie"][-1]
        print("")
        print("   [%s] hoja '%s'" % (clave, d["_hoja"]))
        print("      %d meses, de %s a %s" % (len(d["serie"]),
                                              d["serie"][0][0][:7], d["hasta"]))
        print("      ultimo: Cordoba %s | Total Pais %s"
              % (("%.1f" % u[1]), ("%.1f" % u[2]) if u[2] is not None else "s/d"))
        print("      control i.a.: %d meses comparados, peor desvio %.2f pp%s"
              % (comparados, peor[0], (" (%s)" % peor[1]) if peor[1] else ""))
        print("      fuente: %s" % d["fuente"])
        if d["provisorio"]:
            print("      el ultimo mes es provisorio segun la fuente")

    if diagnostico:
        print("\n[DIAGNOSTICO] No se escribio ieric_cba_cache.js.")
        return

    bloques = ",\n".join(bloque_js(s["clave"], datos[s["clave"]]) for s in SERIES)
    js = (
        "/* ═══════════════════════════\n"
        "   ieric_cba_cache.js  -  Grupo Elyon\n"
        "   Generado por update_ieric_cba_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: IERIC - series estadisticas de la provincia de Cordoba\n"
        "   " + PAGINA + "\n"
        "\n"
        "   puestos  [fecha, Cba, pais, CbaMens, CbaIa, CbaAcum, paisMens, paisIa, paisAcum]\n"
        "   salario  idem, en pesos por mes\n"
        "   empresas [fecha, Cba, pais, CbaIa, paisIa]\n"
        "\n"
        "   Las variaciones son las que publica el IERIC, no se recalculan.\n"
        "   El empleo del IERIC (OSPECON + Seguro de Vida) NO es el mismo\n"
        "   universo que el del INDEC (SIPA): no se pueden encadenar.\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.IERIC_CBA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "IERIC - Instituto de Estadistica y Registro de la Industria de la Construccion",\n'
        '  pagina: "' + PAGINA + '",\n'
        + bloques + "\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("\n[OK] ieric_cba_cache.js")
    print("     puestos hasta %s | salario hasta %s | empresas hasta %s"
          % (datos["puestos"]["hasta"], datos["salario"]["hasta"],
             datos["empresas"]["hasta"]))


if __name__ == "__main__":
    main()
