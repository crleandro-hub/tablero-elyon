#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_apymeco_cache.py - Tablero Gestion Grupo Elyon
=====================================================
Genera apymeco_cache.js con el Indice General de la Construccion y el precio
por metro cuadrado que publica APYMECO (Asociacion de Pymes de la Construccion,
con sede en La Plata).

Por que esta en el tablero
--------------------------
Es el unico dato del tablero que da un PRECIO ABSOLUTO por m2 de una vivienda
de estandar de mercado. Los otros indices de costo son numeros base 100:

  · CAC        -> indice, base dic-2014 = 100. No dice cuanto sale el m2.
  · ICC INDEC  -> indice, base 2004 = 100. Tampoco.
  · ICC Cordoba-> indice base 2012 = 100, y SI publica valor del m2, pero de
                  una VIVIENDA SOCIAL de 50,25 m2. Es un piso, no un
                  presupuesto de obra de mercado.

APYMECO mide una vivienda de estandar comun construida por pymes y el numero
corre alrededor de 2,3 veces el m2 de la vivienda social de Cordoba. Sirve como
segunda referencia de nivel, no como reemplazo de ninguno de los otros.

Que NO incluye el numero de APYMECO (importante al usarlo):
    IVA, impuestos, compra del terreno, honorarios y gastos legales, y
    utilidad del desarrollador. Es costo directo de obra.

El dato es del Gran La Plata / Buenos Aires: no es un indice cordobes. Se lo
lee como contraste con el ICC Cordoba, no como sustituto.

De donde salen los datos
------------------------
    https://www.apymeco.com.ar/001.php?id=3

No hay API ni archivo descargable: la serie esta en una tabla HTML generada por
el sitio. Este script la parsea guiandose por los ENCABEZADOS, no por el orden
de las columnas, igual que el de Construya.

LA PAGINA SOLO MUESTRA LOS ULTIMOS 13 MESES.
Por eso este script NO pisa la serie: la MEZCLA con la que ya esta en
apymeco_cache.js. Asi el historico se va acumulando corrida tras corrida y no
se pierde lo que la pagina ya dejo de mostrar. Es la unica fuente del tablero
que funciona de este modo.

Salida: apymeco_cache.js
    window.APYMECO_CACHE = {
      updated, source, hasta, ratio,
      serie: [[fecha, precioM2, indice, varMensualPub], ...]   ascendente
    }
`ratio` es precioM2 / indice, que en esta fuente es una constante (el precio
y el indice son la misma serie a distinta escala). Se guarda porque es el
control de integridad mas barato que tiene el parseo.

Uso:
    python update_apymeco_cache.py
    python update_apymeco_cache.py --diagnostico   # vuelca lo que parseo y no escribe
"""

import html as _html
import os
import re
import ssl
import sys
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "apymeco_cache.js")

URL = "https://www.apymeco.com.ar/001.php?id=3"
FUENTE = "APYMECO - Indice general de la construccion"
TIMEOUT = 45
MIN_FILAS = 6           # la pagina publica 13 meses; menos de 6 es parseo roto

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# APYMECO abrevia los meses en tres letras y mayusculas: ENE/26, SET/25.
# Se aceptan las dos grafias de septiembre y las variantes con cuatro digitos.
MES_ABR = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Encabezado -> clave interna. Se prueba en este orden: el primero que aparece
# en el texto del encabezado se queda con la columna. "m2" va antes que
# "indice" porque el titulo de la primera columna de valores es "$/m2".
COLUMNAS = [
    ("m2",      ("$/m", "/m2", "/m²", "metro cuadrado", "precio")),
    ("indice",  ("indice",)),
    ("var",     ("variacion", "var")),
]


# ── Descarga ─────────────────────────────────────────────────────────────
def bajar(url):
    """GET con reintento sin verificar certificado (algunas PC corporativas
    tienen el store de certificados desactualizado y falla el handshake)."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
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
    for enc in ("utf-8", "latin-1"):
        try:
            return crudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", "replace")


# ── Utilidades de texto ──────────────────────────────────────────────────
def limpiar(celda):
    """Texto plano de una celda: sin tags, sin entidades, sin espacios de mas."""
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", celda, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def sin_tildes(s):
    for a, b in zip("áéíóúÁÉÍÓÚüÜ", "aeiouAEIOUuU"):
        s = s.replace(a, b)
    return s


def a_periodo(texto):
    """'JUN/26' / 'jun-2026' / '06/2026' -> '2026-06-01'. None si no es un mes."""
    t = sin_tildes(texto.lower().strip())
    m = re.match(r"^([a-z]{3,10})\s*[/\-. ]\s*(\d{2,4})$", t)
    if m:
        num = MES_ABR.get(m.group(1)[:3])
        if num is None:
            return None
        anio = int(m.group(2))
        if anio < 100:
            anio += 2000 if anio < 70 else 1900
        return "%04d-%02d-01" % (anio, num)
    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return "%s-%02d-01" % (m.group(2), int(m.group(1)))
    return None


def a_numero(texto):
    """'$ 2.254.981,82' / '14.896,76' / '4,27%' -> float. None si no hay numero.

    Formato argentino: el punto es separador de miles y la coma decimal."""
    t = texto.replace("$", "").replace("%", "").replace(" ", "").replace("−", "-")
    t = t.replace(".", "").replace(",", ".")
    m = re.match(r"^[+-]?\d+(?:\.\d+)?$", t)
    return round(float(t), 4) if m else None


# ── Parseo del HTML ──────────────────────────────────────────────────────
def filas_html(html):
    """Todas las <tr> de la pagina, ya convertidas a listas de texto."""
    out = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S | re.I):
        celdas = [limpiar(c) for c in
                  re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if celdas:
            out.append(celdas)
    return out


def mapear_columnas(fila):
    """Dada una fila de encabezados, devuelve {clave: indice de columna}."""
    mapa = {}
    for i, celda in enumerate(fila):
        t = sin_tildes(celda.lower())
        for clave, patrones in COLUMNAS:
            if clave in mapa:
                continue
            if any(p in t for p in patrones):
                mapa[clave] = i
                break
    return mapa


def parsear_tabla(html):
    """Parseo normal, por <tr>/<td>. [] si la pagina no trae tabla."""
    filas = filas_html(html)
    if not filas:
        return []

    mapa, datos = {}, []
    for fila in filas:
        posible = mapear_columnas(fila)
        # Un encabezado util identifica al menos el m2 y el indice
        if "m2" in posible and "indice" in posible and not a_periodo(fila[0]):
            mapa = posible
            datos = []                     # las filas de datos vienen despues
            continue
        periodo = a_periodo(fila[0]) if fila else None
        if periodo:
            datos.append((periodo, fila))

    if not mapa:
        # Sin encabezados reconocibles: el orden publicado es
        # Mes | $/m2 | Indice | Variacion
        print("[AVISO] No se reconocieron los encabezados de la tabla; "
              "se usa el orden de columnas habitual.")
        mapa = {"m2": 1, "indice": 2, "var": 3}

    salida, vistos = [], set()
    for periodo, fila in datos:
        def col(clave):
            i = mapa.get(clave)
            return a_numero(fila[i]) if i is not None and i < len(fila) else None
        m2 = col("m2")
        if m2 is None or periodo in vistos:
            continue
        vistos.add(periodo)
        salida.append((periodo, m2, col("indice"), col("var")))
    return salida


def parsear_texto(html):
    """Respaldo: si el sitio deja de emitir <table>, se lee del texto plano.

    Busca el patron 'MES/AA  $x.xxx.xxx,xx  xx.xxx,xx  x,xx%'."""
    texto = limpiar(html)
    patron = re.compile(
        r"(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)\s*[/\-]\s*(\d{2,4})"
        r"\s*\$?\s*([\d.]+,\d+)"
        r"\s+([\d.]+,\d+)"
        r"(?:\s+(-?[\d.,]+)\s*%?)?",
        re.I)
    salida, vistos = [], set()
    for m in patron.finditer(texto):
        periodo = a_periodo(m.group(1) + "/" + m.group(2))
        if not periodo or periodo in vistos:
            continue
        vistos.add(periodo)
        salida.append((periodo, a_numero(m.group(3)), a_numero(m.group(4)),
                       a_numero(m.group(5) or "")))
    return salida


def parsear(html):
    """[(periodo, precioM2, indice, varMensualPub)] ascendente."""
    filas = parsear_tabla(html)
    if len(filas) < MIN_FILAS:
        alt = parsear_texto(html)
        if len(alt) > len(filas):
            print("[AVISO] El parseo por tabla trajo %d fila(s); se usa el "
                  "respaldo por texto plano (%d)." % (len(filas), len(alt)))
            filas = alt
    filas.sort(key=lambda f: f[0])
    return filas


# ── Cache existente: la pagina solo muestra 13 meses ─────────────────────
def leer_cache():
    """Serie ya guardada, como dict 'aaaa-mm-01' -> (m2, indice, var)."""
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return {}
    prev = {}
    for m in re.finditer(r'\["(\d{4}-\d{2}-\d{2})"\s*,\s*([^\]]*)\]', txt):
        vals = [None if v.strip() in ("null", "") else float(v)
                for v in m.group(2).split(",")]
        vals += [None] * (3 - len(vals))
        prev[m.group(1)] = tuple(vals[:3])
    return prev


def mezclar(nuevas, previas):
    """Une lo bajado con lo que ya habia. Gana el dato nuevo, pero se avisa si
    revisa un mes viejo: puede ser una correccion legitima de APYMECO o el
    sintoma de que el parseo se corrio de columna."""
    fusion = dict(previas)
    revisiones = []
    for periodo, m2, idx, var in nuevas:
        viejo = previas.get(periodo)
        if viejo and viejo[0] and m2 and abs(m2 / viejo[0] - 1) > 0.005:
            revisiones.append("%s: %s -> %s" % (periodo[:7], viejo[0], m2))
        fusion[periodo] = (m2, idx, var)
    if revisiones:
        print("[AVISO] %d mes(es) ya guardados cambiaron de valor: %s"
              % (len(revisiones), ", ".join(revisiones[:5])))
    return [(p,) + fusion[p] for p in sorted(fusion)]


# ── Controles antes de escribir ──────────────────────────────────────────
def controlar(filas, bajadas):
    """Aborta si la serie no tiene sentido. Vale mas quedarse con el cache
    viejo que pisarlo con un parseo roto."""
    if len(bajadas) < MIN_FILAS:
        raise SystemExit(
            "[ERROR] Solo se parsearon %d meses de la pagina (minimo %d). "
            "Cambio el formato. Se conserva el apymeco_cache.js anterior."
            % (len(bajadas), MIN_FILAS))

    m2s = [f[1] for f in filas if f[1] is not None]
    if not m2s or min(m2s) <= 0:
        raise SystemExit("[ERROR] Hay precios de m2 nulos o negativos. "
                         "Se conserva el cache anterior.")

    # Control fuerte de esta fuente: precio y indice son la MISMA serie a
    # distinta escala, asi que precioM2 / indice tiene que dar constante.
    # Si las columnas se corren, el cociente explota y esto lo agarra.
    ratios = [f[1] / f[2] for f in filas if f[1] and f[2]]
    if not ratios:
        raise SystemExit("[ERROR] No se pudo leer el indice en ninguna fila. "
                         "Se conserva el cache anterior.")
    ratios.sort()
    mediana = ratios[len(ratios) // 2]
    # El precio del m2 siempre es varias veces mas grande que el indice. Si el
    # cociente da menos que 1, las dos columnas vinieron al reves: el cociente
    # sigue siendo constante y el control de abajo lo dejaria pasar.
    if mediana <= 1:
        raise SystemExit(
            "[ERROR] El precio del m2 quedo por debajo del indice (cociente %s): "
            "las columnas vinieron invertidas. Se conserva el cache anterior."
            % round(mediana, 5))
    fuera = [r for r in ratios if abs(r / mediana - 1) > 0.01]
    if len(fuera) > max(1, len(ratios) // 10):
        raise SystemExit(
            "[ERROR] El cociente precio/indice no es constante (%s a %s, "
            "mediana %s): las columnas no son las esperadas. "
            "Se conserva el cache anterior."
            % (round(ratios[0], 3), round(ratios[-1], 3), round(mediana, 3)))

    # Coherencia: la variacion publicada tiene que dar parecido a la que sale
    # de dividir los indices de dos meses seguidos.
    idx = {f[0]: f[2] for f in filas if f[2] is not None}
    malas = 0
    for a, b in zip(filas, filas[1:]):
        if b[3] is None or a[0] not in idx or b[0] not in idx:
            continue
        calc = (idx[b[0]] / idx[a[0]] - 1) * 100
        if abs(calc - b[3]) > 0.5:
            malas += 1
    if malas > 2:
        raise SystemExit(
            "[ERROR] La variacion mensual publicada no coincide con la "
            "calculada en %d meses. Se conserva el cache anterior." % malas)

    huecos = []
    for a, b in zip(filas, filas[1:]):
        ya, ma = int(a[0][:4]), int(a[0][5:7])
        esperado = "%04d-%02d-01" % (ya + (ma == 12), 1 if ma == 12 else ma + 1)
        if b[0] != esperado:
            huecos.append("%s->%s" % (a[0][:7], b[0][:7]))
    if huecos:
        print("[AVISO] %d hueco(s) en la serie: %s"
              % (len(huecos), ", ".join(huecos[:5])))

    return mediana


# ── Escritura ────────────────────────────────────────────────────────────
def num(v):
    """Numero para el .js. No se usa %g como en los otros caches: el precio del
    m2 pasa los siete digitos y %g lo convertiria a notacion cientifica,
    perdiendo los centavos."""
    if v is None:
        return "null"
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s or "0"


def emitir(filas, ratio):
    hasta = filas[-1][0][:7]
    cuerpo = ",\n".join(
        '    ["%s",%s,%s,%s]' % (f[0], num(f[1]), num(f[2]), num(f[3]))
        for f in filas)
    return (
        "/* ═══════════════════════════\n"
        "   apymeco_cache.js  -  Grupo Elyon\n"
        "   Generado por update_apymeco_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + FUENTE + " (La Plata / Buenos Aires)\n"
        "   Columnas: fecha, precio del m2 en pesos, indice general,\n"
        "             variacion mensual tal como la publica APYMECO.\n"
        "   El precio EXCLUYE IVA, terreno, honorarios, gastos legales y\n"
        "   utilidad del desarrollador: es costo directo de obra.\n"
        "   La pagina solo muestra 13 meses; el script ACUMULA historico.\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.APYMECO_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + FUENTE + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  ratio: " + num(round(ratio, 4)) + ",\n"
        "  serie: [\n" + cuerpo + "\n  ]\n"
        "};\n"
    )


def main():
    diagnostico = "--diagnostico" in sys.argv
    print("Actualizando indice APYMECO desde apymeco.com.ar...")
    try:
        html = bajar(URL)
    except Exception as e:
        raise SystemExit("[ERROR] No se pudo bajar la pagina (%s). "
                         "Se conserva el apymeco_cache.js anterior." % e)

    bajadas = parsear(html)
    if diagnostico:
        print("   Filas parseadas de la pagina: %d" % len(bajadas))
        for f in bajadas:
            print("     %s  m2=%s  idx=%s  var=%s" % f)
        print("\n[DIAGNOSTICO] No se escribio nada.")
        return

    previas = leer_cache()
    filas = mezclar(bajadas, previas)
    ratio = controlar(filas, bajadas)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(emitir(filas, ratio))

    ult = filas[-1]
    nuevos = len([f for f in filas if f[0] not in previas])
    print("   Pagina        : %d meses (%s a %s)"
          % (len(bajadas), bajadas[0][0][:7], bajadas[-1][0][:7]))
    print("   Serie guardada: %d meses (%s a %s)%s"
          % (len(filas), filas[0][0][:7], ult[0][:7],
             ", %d nuevo(s)" % nuevos if nuevos else ""))
    print("   Precio/indice : %s (constante de la fuente)" % round(ratio, 3))
    print("\n[OK] apymeco_cache.js")
    print("     %s = $ %s /m2 - indice %s - %s%% mensual"
          % (ult[0][:7],
             ("{:,.2f}".format(ult[1]).replace(",", "@").replace(".", ",")
              .replace("@", ".")) if ult[1] else "N/D",
             num(ult[2]), num(ult[3])))


if __name__ == "__main__":
    main()
