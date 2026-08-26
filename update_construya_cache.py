#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_construya_cache.py - Tablero Gestion Grupo Elyon
========================================================
Genera construya_cache.js con el Indice Construya, que publica el Grupo
Construya (camara de empresas lideres de materiales).

Por que esta en el tablero
--------------------------
Es el termometro mas RAPIDO de la actividad de la construccion. Mide el
volumen fisico vendido al sector privado por las 12 empresas del grupo
(ladrillos ceramicos, cemento, cal, aceros largos, aberturas de aluminio,
adhesivos, pinturas, sanitarios, calderas, griferia, caños y revestimientos)
y sale alrededor del dia 10 del mes siguiente. El ISAC del INDEC, que mide lo
mismo pero para toda la economia, llega entre 4 y 6 semanas mas tarde. O sea:
Construya adelanta el ISAC casi un mes.

Diferencias con el ISAC que conviene tener presentes:
  · Construya es privado y de universo acotado (12 empresas), el ISAC es
    oficial y de universo amplio (13 insumos de todo el mercado).
  · Construya solo mide venta al sector PRIVADO: no toma obra publica.
  · Base distinta. La serie de Construya arranca en 2002 = 100 y en la pagina
    se publica desde enero de 2017.

De donde salen los datos
------------------------
    https://www.grupoconstruya.com.ar/servicios/indice_construya

No hay API ni archivo descargable: la serie esta en una tabla HTML de esa
pagina. Este script la parsea. El parseo se apoya en los ENCABEZADOS de la
tabla, no en el orden de las columnas, para que un cambio de maquetado no
ensucie los datos en silencio. Si algo no cierra, aborta sin escribir y el
construya_cache.js anterior queda intacto.

Salida: construya_cache.js
    window.CONSTRUYA_CACHE = {
      updated, source, hasta, informe,
      serie: [[fecha, conEstacionalidad, desestacionalizado,
               varIAPub, varAcumPub, varMensualPub], ...]   ascendente
    }
Las tres ultimas columnas son las variaciones tal como las publica el Grupo
Construya. El tablero las recalcula por su cuenta a partir del indice (mismo
criterio que usa para el ISAC) y las publicadas quedan como control.

Uso:
    python update_construya_cache.py
"""

import html as _html
import os
import re
import ssl
import sys
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from marca_cache import marcar, guardar_diagnostico, limpiar_diagnostico  # noqa: E402
CACHE_PATH = os.path.join(BASE_DIR, "construya_cache.js")

URL = "https://www.grupoconstruya.com.ar/servicios/indice_construya"
TIMEOUT = 45
MIN_FILAS = 60          # la pagina publica ~9 años; menos de 5 es que fallo el parseo

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MES_NUM = {m: i + 1 for i, m in enumerate(MESES)}
MES_NUM["setiembre"] = 9        # la pagina alterna las dos grafias

# Encabezado -> clave interna. Se prueba en este orden y gana la primera que
# aparece en el texto del encabezado, por eso "desestacionaliz" va antes que
# "estacionalidad": si no, "Indice Desestacionalizado" caeria en la otra.
COLUMNAS = [
    ("desest",   ("desestacionaliz",)),
    ("con_est",  ("con estacionalidad", "estacionalidad")),
    ("var_ia",   ("interanual",)),
    ("var_acum", ("acumulada", "acumulado")),
    ("var_mes",  ("mensual",)),
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


# ── Parseo del HTML ──────────────────────────────────────────────────────
def limpiar(celda):
    """Texto plano de una celda: sin tags, sin entidades, sin espacios de mas."""
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", celda, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def filas_html(html):
    """Todas las <tr> de la pagina, ya convertidas a listas de texto."""
    out = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html, re.S | re.I):
        celdas = [limpiar(c) for c in
                  re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if celdas:
            out.append(celdas)
    return out


def filas_div(html):
    """Filas de la maqueta NUEVA, hecha con <div> en lugar de <table>.

    En agosto de 2026 Grupo Construya rehizo la pagina: la tabla dejo de ser
    <table>/<tr>/<td> y paso a ser una grilla de <div class="TablaRowIndice">.
    Cada celda lleva adelante su propio rotulo en un <span class="tituloInline">
    (es el rotulo que se ve cuando la pagina se mira en el celular):

        <div class="TablaRowIndice">
          <div><span class="tituloInline">Mes: </span>Julio 2026</div>
          <div class="conestac"><span class="tituloInline">Con Estacionalidad: </span>280,0</div>
          ...

    Ese rotulo es una ventaja: en vez de depender del orden de las columnas, se
    arma un encabezado con los rotulos y las filas con los valores. El resto del
    script (mapear_columnas, a_periodo, los controles) sigue funcionando igual
    que con la tabla vieja, y si algun dia vuelven a <table> tampoco se rompe."""
    bloques = re.split(r'<div[^>]*class="[^"]*TablaRowIndice[^"]*"[^>]*>',
                       html, flags=re.I)[1:]
    if not bloques:
        return []

    # El valor se toma hasta que cierra la celda, no hasta el primer "<": los
    # meses de enero vienen en negrita (<strong>Enero 2026</strong>) y cortando
    # en el "<" quedaban vacios, con lo que se perdian nueve eneros de la serie.
    # El rotulo de "% Anual Acumulado" ademas va envuelto en un <h5>.
    par = re.compile(
        r'<span[^>]*tituloInline[^>]*>(.*?)</span>(.*?)</(?:div|h5)>', re.S | re.I)
    encabezado, out = None, []
    for bloque in bloques:
        pares = [(limpiar(r).rstrip(": "), limpiar(v)) for r, v in par.findall(bloque)]
        if len(pares) < 3:                   # fila incompleta o de corte
            continue
        if encabezado is None:
            encabezado = [r for r, _ in pares]
            out.append(encabezado)
        out.append([v for _, v in pares])
    return out


def sin_tildes(s):
    for a, b in zip("áéíóúÁÉÍÓÚüÜ", "aeiouAEIOUuU"):
        s = s.replace(a, b)
    return s


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


def a_periodo(texto):
    """'Enero 2017' / 'ene-17' / '01/2017' -> '2017-01-01'. None si no es un mes."""
    t = sin_tildes(texto.lower().strip())
    m = re.match(r"^([a-z]{3,10})[\s\-/.]+(\d{2,4})$", t)
    if m:
        nombre, anio = m.group(1), m.group(2)
        num = MES_NUM.get(nombre)
        if num is None:                      # abreviaturas: ene, feb, sep...
            for nom, n in MES_NUM.items():
                if nom.startswith(nombre[:3]):
                    num = n
                    break
        if num is None:
            return None
        anio = int(anio)
        if anio < 100:
            anio += 2000 if anio < 70 else 1900
        return "%04d-%02d-01" % (anio, num)
    m = re.match(r"^(\d{1,2})[/\-](\d{4})$", t)
    if m:
        return "%s-%02d-01" % (m.group(2), int(m.group(1)))
    m = re.match(r"^(\d{4})[/\-](\d{1,2})$", t)
    if m:
        return "%s-%02d-01" % (m.group(1), int(m.group(2)))
    return None


def a_numero(texto):
    """'304,9' / '-6,9%' / '+8,2 %' -> float. None si no hay numero."""
    t = texto.replace("%", "").replace(" ", "").replace("−", "-")
    t = t.replace(".", "").replace(",", ".")     # separador de miles y decimal
    m = re.match(r"^[+-]?\d+(?:\.\d+)?$", t)
    return round(float(t), 4) if m else None


def parsear(html):
    """[(periodo, con_est, desest, var_ia, var_acum, var_mes)] ascendente."""
    filas = filas_html(html)
    if not filas:
        filas = filas_div(html)
        if filas:
            print("   La pagina ya no usa <table>: se leyo la grilla de <div>.")
    if not filas:
        guardar_diagnostico(BASE_DIR, "construya", html)
        raise SystemExit("[ERROR] La pagina no trajo la serie, ni como <table> "
                         "ni como grilla de <div>. Quedo _construya_diagnostico.html "
                         "con lo que llego. Se conserva el construya_cache.js anterior.")

    mapa, datos = {}, []
    for fila in filas:
        posible = mapear_columnas(fila)
        # Un encabezado util tiene al menos el indice con y sin estacionalidad
        if "con_est" in posible and "desest" in posible and not a_periodo(fila[0]):
            mapa = posible
            datos = []                       # las filas de datos vienen despues
            continue
        periodo = a_periodo(fila[0]) if fila else None
        if periodo:
            datos.append((periodo, fila))

    if not mapa:
        # Sin encabezados reconocibles, el orden observado en la pagina es:
        # Mes | Con estacionalidad | Var. interanual | Var. acumulada |
        # Desestacionalizado | Var. mensual
        print("[AVISO] No se reconocieron los encabezados de la tabla; "
              "se usa el orden de columnas habitual.")
        mapa = {"con_est": 1, "var_ia": 2, "var_acum": 3, "desest": 4, "var_mes": 5}

    salida, vistos = [], set()
    for periodo, fila in datos:
        def col(clave):
            i = mapa.get(clave)
            return a_numero(fila[i]) if i is not None and i < len(fila) else None
        con_est = col("con_est")
        if con_est is None:                  # fila de titulo o de corte
            continue
        if periodo in vistos:
            continue
        vistos.add(periodo)
        salida.append((periodo, con_est, col("desest"),
                       col("var_ia"), col("var_acum"), col("var_mes")))

    salida.sort(key=lambda f: f[0])
    return salida


def buscar_informe(html):
    """La bajada del informe: 'Buenos Aires, 10 de agosto de 2026.- En julio...'.

    Se toma una ventana de 420 caracteres y se corta en el ultimo punto, para
    no quedarse con el 'Buenos Aires, 10 de agosto de 2026.' pelado: ese primer
    punto llega a los 35 caracteres y se comeria toda la novedad del mes."""
    texto = limpiar(html)
    m = re.search(r"Buenos Aires,\s*\d{1,2}\s+de\s+\w+\s+de\s+\d{4}.{0,420}", texto, re.S)
    if not m:
        return ""
    frag = re.sub(r"\s+", " ", m.group(0)).strip()
    corte = frag.rfind(".")
    if corte > 120:
        frag = frag[:corte + 1]
    return frag


# ── Controles antes de escribir ──────────────────────────────────────────
def controlar(filas):
    """Aborta si la serie no tiene sentido. Vale mas quedarse con el cache
    viejo que pisarlo con un parseo roto."""
    if len(filas) < MIN_FILAS:
        raise SystemExit("[ERROR] Solo se parsearon %d meses (minimo %d). "
                         "Cambio el formato de la pagina. Se conserva el cache anterior."
                         % (len(filas), MIN_FILAS))

    valores = [f[1] for f in filas if f[1] is not None]
    if not valores or min(valores) <= 0 or max(valores) > 5000:
        raise SystemExit("[ERROR] Los valores del indice quedaron fuera de rango "
                         "(%s a %s). Se conserva el cache anterior."
                         % (min(valores or [0]), max(valores or [0])))

    huecos = []
    for a, b in zip(filas, filas[1:]):
        ya, ma = int(a[0][:4]), int(a[0][5:7])
        esperado = "%04d-%02d-01" % (ya + (ma == 12), 1 if ma == 12 else ma + 1)
        if b[0] != esperado:
            huecos.append("%s->%s" % (a[0][:7], b[0][:7]))
    if huecos:
        print("[AVISO] %d hueco(s) en la serie: %s"
              % (len(huecos), ", ".join(huecos[:5])))

    # Coherencia: la variacion interanual publicada tiene que dar parecido a la
    # que sale de dividir los indices. Si no da, se corrieron las columnas.
    mapa = {f[0][:7]: f[1] for f in filas if f[1] is not None}
    malas = 0
    for f in filas[-24:]:
        pub = f[3]
        prev = mapa.get("%04d-%s" % (int(f[0][:4]) - 1, f[0][5:7]))
        if pub is None or not prev or not f[1]:
            continue
        calc = (f[1] / prev - 1) * 100
        if abs(calc - pub) > 1.5:
            malas += 1
    if malas > 4:
        raise SystemExit("[ERROR] La variacion interanual publicada no coincide con "
                         "la calculada en %d de los ultimos 24 meses: las columnas "
                         "no son las esperadas. Se conserva el cache anterior." % malas)


# ── Escritura ────────────────────────────────────────────────────────────
def num(v):
    return "null" if v is None else ("%g" % v)


def emitir(filas, informe, fuente):
    hasta = filas[-1][0][:7]
    cuerpo = ",\n".join(
        '    ["%s",%s,%s,%s,%s,%s]' % (f[0], num(f[1]), num(f[2]),
                                       num(f[3]), num(f[4]), num(f[5]))
        for f in filas)
    return (
        "/* ═══════════════════════════\n"
        "   construya_cache.js  -  Grupo Elyon\n"
        "   Generado por update_construya_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + "\n"
        "   Columnas: fecha, indice con estacionalidad, indice desestacionalizado,\n"
        "             var. interanual, var. acumulada del año y var. mensual\n"
        "             (las tres variaciones, tal como las publica la camara).\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.CONSTRUYA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  informe: " + _json_str(informe) + ",\n"
        "  serie: [\n" + cuerpo + "\n  ]\n"
        "};\n"
    )


def _json_str(s):
    s = (s or "").replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\n", " ").replace("\r", " ")
    return '"' + s + '"'


def main():
    print("Actualizando Indice Construya desde grupoconstruya.com.ar...")
    try:
        html = bajar(URL)
    except Exception as e:
        raise SystemExit("[ERROR] No se pudo bajar la pagina (%s). "
                         "Se conserva el construya_cache.js anterior." % e)

    filas = parsear(html)
    controlar(filas)
    informe = buscar_informe(html)

    js = emitir(filas, informe, "Grupo Construya (indice_construya)")
    limpiar_diagnostico(BASE_DIR, "construya")
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    ult = filas[-1]
    print("   Serie         : %d meses, de %s a %s"
          % (len(filas), filas[0][0][:7], ult[0][:7]))
    if informe:
        print("   Informe       : %s" % informe[:110])
    print("\n[OK] construya_cache.js")
    print("     %s = %s con estacionalidad / %s desestacionalizado"
          % (ult[0][:7], num(ult[1]), num(ult[2])))
    print("     interanual %s%% · mensual desest. %s%%" % (num(ult[3]), num(ult[5])))


if __name__ == "__main__":
    # Corra bien o falle, queda constancia de que el script se ejecuto. Sin
    # esto, un cache que no se reescribe se lee como "el script no corre" y a
    # los 6 dias verificar.py frena la publicacion de TODO el tablero.
    try:
        main()
        marcar(CACHE_PATH)
    except SystemExit as e:
        if e.code:
            marcar(CACHE_PATH, e.code)
        raise
