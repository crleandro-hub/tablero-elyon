#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_precio_cba_cache.py - Tablero Gestion Grupo Elyon
========================================================
Precio de OFERTA de departamentos en venta en Cordoba capital, en dolares
por m2, de dos fuentes VIVAS. Es el otro lado del negocio: el tablero mide
muy bien el costo de construir y sin precio de venta no se lee el margen.

Por que dos fuentes y no una
----------------------------
El ZPIndex de Zonaprop (zpindex_cache.js) quedo congelado en marzo de 2026
para Cordoba: sirve de ancla historica pero no de dato corriente. De las
alternativas relevadas en noviembre de 2026:

  Roomix   serie mensual descargable en CSV (15 meses al 26/11/2026),
           apertura por barrio, y el valor de departamentos aparte del
           total de mercado. Es la unica automatizable de punta a punta.
  Mudafy   monitor que se actualiza todos los dias, con el valor de
           departamentos de la ciudad. No publica serie: la historia la
           vamos armando nosotros mes a mes, igual que con el ZPIndex.
  MeLi-UdeSA  la mas seria metodologicamente (mensual desde 2018) pero los
           Excel viven en carpetas de Google Drive: no se puede bajar solo.
  CPI Cordoba  publica precios totales por barrio, sin superficie. No sirve
           para un USD/m2.

Las tres fuentes vivas cerraban entre USD 1.500 y 1.633/m2 en noviembre de
2026, contra los USD 1.474 que marcaba Zonaprop en marzo: son coherentes
entre si, asi que Mudafy funciona como control de Roomix y viceversa.

OJO CON LA MEZCLA DE TIPOLOGIAS
-------------------------------
El CSV de Roomix mezcla casas y departamentos (por eso da ~1.309 y no
~1.633). El nivel comparable con Zonaprop y con Mudafy es el de
DEPARTAMENTOS, que solo esta en la pagina. Por eso se guardan las dos cosas:
la serie larga del CSV para ver la evolucion, y el valor de departamentos
para comparar niveles entre fuentes.

Salida: precio_cba_cache.js
    window.PRECIO_CBA_CACHE = {
      updated, chequeado, aviso,
      roomix: { mes, mesSerie, deptosUsdM2, deptosAvisos, totalUsdM2, varIa,
                serie: [[mes, usdM2], ...], serieDeptos: [[mes, usdM2], ...],
                barrios: [[nombre, usdM2], ...], url },
      mudafy: { fecha, mes, deptosUsdM2, tipico,
                serieDeptos: [[mes, usdM2], ...], url }
    }
"""

import os
import re
import ssl
import sys
import time
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from marca_cache import marcar  # noqa: E402

CACHE_PATH = os.path.join(BASE_DIR, "precio_cba_cache.js")

TIMEOUT = 45
INTENTOS = 3
ESPERA = 4
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

ROOMIX_CSV = "https://roomix.ai/datos/roomix-index/cordoba-capital/precios.csv"
ROOMIX_WEB = "https://roomix.ai/roomix-index/cordoba-capital"
MUDAFY_WEB = "https://mudafy.com.ar/monitor-inmobiliario/cordoba-cordoba-capital"

# Cuantos barrios se guardan (ordenados de mayor a menor USD/m2).
TOPE_BARRIOS = 24

# Diferencia tolerada entre las dos fuentes antes de avisar. Miden lo mismo
# (precio pedido de departamentos) sobre catalogos distintos, asi que un
# desvio chico es normal; uno grande significa que alguna leyo cualquier cosa.
TOLERANCIA_FUENTES = 0.35

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

RE_TAGS = re.compile(r"<(script|style)[\s\S]*?</\1>|<[^>]+>", re.I)


def _texto(html):
    """HTML -> texto plano con espacios normalizados."""
    t = RE_TAGS.sub(" ", html)
    t = re.sub(r"&nbsp;|&#\d+;", " ", t)
    t = t.replace("&amp;", "&").replace("&oacute;", "ó")
    return re.sub(r"\s+", " ", t)


def _get(url):
    """GET con reintentos. Mismo criterio que el resto de los actualizadores:
    el handshake SSL falla distinto que una lectura lenta y se trata distinto."""
    r = req.Request(url, headers={"User-Agent": UA,
                                  "Accept": "text/html,text/csv,*/*",
                                  "Accept-Language": "es-AR,es;q=0.9"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    sin_verificar = [False]
    ultimo = None
    for intento in range(INTENTOS):
        try:
            with req.urlopen(r, timeout=TIMEOUT,
                             context=ctx if sin_verificar[0] else None) as resp:
                return resp.read().decode("utf-8", "replace")
        except ssl.SSLError as e:
            ultimo = e
            sin_verificar[0] = True
            continue
        except Exception as e:
            ultimo = e
        if intento < INTENTOS - 1:
            time.sleep(ESPERA * (intento + 1))
    raise ultimo


def _usd(txt):
    """'1.633' -> 1633. Las dos fuentes usan el punto como separador de miles
    en los precios, nunca como decimal, asi que alcanza con sacar lo que no
    sea digito."""
    n = re.sub(r"\D", "", str(txt))
    return float(n) if n else 0.0


def _pct(txt):
    """'+8,5' -> 8.5 ; '-3,1' -> -3.1 (tambien el menos tipografico)."""
    s = str(txt).strip().replace("\u2212", "-").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _ym(nombre_mes, anio):
    nombre_mes = nombre_mes.strip().lower()
    if nombre_mes not in MESES:
        return None
    return "%s-%02d" % (anio, MESES.index(nombre_mes) + 1)


def _plausible(usd):
    return 100 <= usd <= 20000


# ───────────────────────── Roomix ─────────────────────────

def leer_roomix_csv():
    """[[mes, usdM2], ...] del CSV de la ciudad. Mezcla casas y deptos."""
    txt = _get(ROOMIX_CSV)
    lineas = [l for l in txt.splitlines() if l.strip()]
    if not lineas or "venta_usd_m2" not in lineas[0]:
        raise ValueError("el CSV de Roomix no tiene la cabecera esperada")
    col = lineas[0].split(",").index("venta_usd_m2")
    serie = []
    for l in lineas[1:]:
        partes = l.split(",")
        if len(partes) <= col:
            continue
        mes = partes[0].strip()
        if not re.match(r"^\d{4}-\d{2}$", mes):
            continue
        v = _usd(partes[col])
        if _plausible(v):
            serie.append([mes, v])
    if not serie:
        raise ValueError("el CSV de Roomix no trajo ninguna fila usable")
    return sorted(serie)


def leer_roomix_web():
    """{mes, deptosUsdM2, deptosAvisos, varIa, barrios} de la pagina."""
    html = _get(ROOMIX_WEB)
    texto = _texto(html)

    d = {}

    m = re.search(r"Datos a\s+(" + "|".join(MESES) + r")\s+de\s+(\d{4})",
                  texto, re.I)
    d["mes"] = _ym(m.group(1), m.group(2)) if m else None

    m = re.search(r"Departamentos\s*[·.]\s*Venta\s*US\$\s*([\d.]+)\s*/m²"
                  r"(?:\s*([\d.]+)\s*avisos)?", texto, re.I)
    if not m:
        raise ValueError("no se encontro el USD/m2 de departamentos en Roomix")
    d["deptosUsdM2"] = _usd(m.group(1))
    d["deptosAvisos"] = int(_usd(m.group(2))) if m.group(2) else None
    if not _plausible(d["deptosUsdM2"]):
        raise ValueError("el USD/m2 de Roomix (%s) no es plausible"
                         % d["deptosUsdM2"])

    m = re.search(r"Precio de venta\s*US\$\s*[\d.]+\s*/m²\s*"
                  r"([+\-\u2212]?[\d,]+)\s*%\s*interanual", texto, re.I)
    d["varIa"] = _pct(m.group(1)) if m else None

    # Barrios: cada fila es un enlace a su propia ficha con el USD/m2 al lado.
    barrios, vistos = [], set()
    for slug, nombre, usd in re.findall(
            r'/roomix-index/([a-z0-9-]+)"[^>]*>\s*<span[^>]*>([^<]{2,40})</span>'
            r'.{0,400}?US\$([\d.]+)/m²', html, re.S):
        nombre = nombre.strip()
        v = _usd(usd)
        if nombre and nombre not in vistos and _plausible(v):
            vistos.add(nombre)
            barrios.append([nombre, v])
    d["barrios"] = sorted(barrios, key=lambda b: -b[1])[:TOPE_BARRIOS]
    return d


# ───────────────────────── Mudafy ─────────────────────────

def leer_mudafy():
    """{fecha, mes, deptosUsdM2, tipico} del monitor diario."""
    html = _get(MUDAFY_WEB)
    texto = _texto(html)

    d = {}
    m = re.search(r"Actualizado el\s+(\d{1,2})\s+de\s+(" + "|".join(MESES)
                  + r")\s+de\s+(\d{4})", texto, re.I)
    if m:
        d["fecha"] = "%s/%02d/%s" % (m.group(1), MESES.index(m.group(2).lower()) + 1,
                                     m.group(3))
        d["mes"] = _ym(m.group(2), m.group(3))
    else:
        d["fecha"] = None
        d["mes"] = None

    m = re.search(r"se publica a USD\s*([\d.]+)", texto, re.I)
    if not m:
        raise ValueError("no se encontro el USD/m2 de departamentos en Mudafy")
    d["deptosUsdM2"] = _usd(m.group(1))
    if not _plausible(d["deptosUsdM2"]):
        raise ValueError("el USD/m2 de Mudafy (%s) no es plausible"
                         % d["deptosUsdM2"])

    m = re.search(r"precio típico es USD\s*([\d.]+)", texto, re.I)
    d["tipico"] = _usd(m.group(1)) if m else None

    if d["mes"] is None:
        d["mes"] = datetime.now().strftime("%Y-%m")
    return d


# ───────────────────── serie que vamos armando ─────────────────────

def _bloque_previo(bloque):
    """El bloque de una fuente tal cual quedo en el cache, texto incluido."""
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        txt = open(CACHE_PATH, encoding="utf-8").read()
    except Exception:
        return None
    b = re.search(r'\n(  %s:\s*\{.*?\n  \})' % bloque, txt, re.S)
    return b.group(1) if b else None


def _serie_previa(bloque, clave="serieDeptos"):
    """La serie de departamentos que ya quedo en el cache. Ni Roomix ni Mudafy
    publican el historico de ESE corte, asi que lo acumulamos nosotros."""
    b = _bloque_previo(bloque)
    if not b:
        return {}
    s = re.search(r'%s:\s*\[(.*?)\]' % clave, b, re.S)
    if not s:
        return {}
    return {f: float(v) for f, v in
            re.findall(r'\["(\d{4}-\d{2})",([\d.]+)\]', s.group(1))}


def _js(s):
    return '"' + str(s).replace("\\", "/").replace('"', "'") + '"'


def _opt(v):
    if v is None:
        return "null"
    if isinstance(v, str):
        return _js(v)
    return "%g" % v


def _serie_js(serie):
    return ",".join('["%s",%g]' % (f, v) for f, v in serie)


def main():
    print("Actualizando el precio de venta de departamentos en Cordoba...")

    avisos = []

    roomix, mudafy = None, None

    try:
        roomix = leer_roomix_web()
        roomix["serie"] = leer_roomix_csv()
        roomix["mesSerie"] = roomix["serie"][-1][0]
        roomix["totalUsdM2"] = roomix["serie"][-1][1]
        if roomix["mes"] is None:
            roomix["mes"] = roomix["mesSerie"]
        serie = _serie_previa("roomix")
        serie[roomix["mes"]] = roomix["deptosUsdM2"]
        roomix["serieDeptos"] = sorted([[f, v] for f, v in serie.items()])
        print("   Roomix     %s · deptos USD %g/m2 · total USD %g/m2 · "
              "%d meses en el CSV · %d barrios"
              % (roomix["mes"], roomix["deptosUsdM2"], roomix["totalUsdM2"],
                 len(roomix["serie"]), len(roomix["barrios"])))
    except Exception as e:
        print("   [AVISO] Roomix: %s" % e)
        avisos.append("Roomix: %s" % e)

    try:
        mudafy = leer_mudafy()
        serie = _serie_previa("mudafy")
        serie[mudafy["mes"]] = mudafy["deptosUsdM2"]
        mudafy["serieDeptos"] = sorted([[f, v] for f, v in serie.items()])
        print("   Mudafy     %s · deptos USD %g/m2 · tipico USD %s · al %s"
              % (mudafy["mes"], mudafy["deptosUsdM2"],
                 ("%g" % mudafy["tipico"]) if mudafy["tipico"] else "?",
                 mudafy["fecha"]))
    except Exception as e:
        print("   [AVISO] Mudafy: %s" % e)
        avisos.append("Mudafy: %s" % e)

    if roomix is None and mudafy is None:
        raise SystemExit("[AVISO] no se pudo leer ninguna fuente de precio. "
                         "Se conserva precio_cba_cache.js como estaba.")

    # Control cruzado: las dos miden precio pedido de departamentos en la
    # misma ciudad, asi que tienen que parecerse.
    if roomix and mudafy:
        a, b = roomix["deptosUsdM2"], mudafy["deptosUsdM2"]
        desvio = abs(a - b) / ((a + b) / 2)
        print("   Contraste  Roomix %g vs Mudafy %g · %.1f%% de diferencia"
              % (a, b, desvio * 100))
        if desvio > TOLERANCIA_FUENTES:
            avisos.append("Roomix (USD %g/m2) y Mudafy (USD %g/m2) difieren "
                          "%.0f%%: revisar cual leyo mal" % (a, b, desvio * 100))

    partes = []
    if roomix:
        partes.append(
            "  roomix: {\n"
            '    nombre: "Roomix",\n'
            '    mes: %s,\n' % _opt(roomix["mes"])
            + '    mesSerie: %s,\n' % _opt(roomix["mesSerie"])
            + '    deptosUsdM2: %g,\n' % roomix["deptosUsdM2"]
            + '    deptosAvisos: %s,\n' % _opt(roomix["deptosAvisos"])
            + '    totalUsdM2: %g,\n' % roomix["totalUsdM2"]
            + '    varIa: %s,\n' % _opt(roomix["varIa"])
            + '    url: %s,\n' % _js(ROOMIX_WEB)
            + '    serie: [%s],\n' % _serie_js(roomix["serie"])
            + '    serieDeptos: [%s],\n' % _serie_js(roomix["serieDeptos"])
            + '    barrios: [%s]\n' % ",".join(
                '[%s,%g]' % (_js(n), v) for n, v in roomix["barrios"])
            + "  }")
    if mudafy:
        partes.append(
            "  mudafy: {\n"
            '    nombre: "Mudafy",\n'
            '    mes: %s,\n' % _opt(mudafy["mes"])
            + '    fecha: %s,\n' % _opt(mudafy["fecha"])
            + '    deptosUsdM2: %g,\n' % mudafy["deptosUsdM2"]
            + '    tipico: %s,\n' % _opt(mudafy["tipico"])
            + '    url: %s,\n' % _js(MUDAFY_WEB)
            + '    serieDeptos: [%s]\n' % _serie_js(mudafy["serieDeptos"])
            + "  }")

    # Si una fuente se cayo, se conserva lo que ya estaba en vez de borrarlo:
    # la serie de departamentos la venimos acumulando nosotros y no se
    # recupera sola. Queda marcada como vieja por su propio campo "mes".
    if roomix is None:
        viejo = _bloque_previo("roomix")
        if viejo:
            partes.insert(0, viejo)
            print("   Roomix     se conserva lo que ya estaba en el cache")
    if mudafy is None:
        viejo = _bloque_previo("mudafy")
        if viejo:
            partes.append(viejo)
            print("   Mudafy     se conserva lo que ya estaba en el cache")

    js = (
        "/* ═══════════════════════════\n"
        "   precio_cba_cache.js  -  Grupo Elyon\n"
        "   Generado por update_precio_cba_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Precio de OFERTA de departamentos en venta en Cordoba capital,\n"
        "   en dolares por m2. Es precio PEDIDO, no escriturado.\n"
        "   Roomix: serie mensual propia (CSV) + valor de departamentos.\n"
        "   Mudafy: monitor diario, sirve de control cruzado.\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.PRECIO_CBA_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "Roomix + Mudafy · precio de oferta",\n'
        + ",\n".join(partes)
        + "\n};\n"
    )

    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)
    os.replace(tmp, CACHE_PATH)

    marcar(CACHE_PATH, "; ".join(avisos) if avisos else None)

    print("\n[OK] precio_cba_cache.js")
    for a in avisos:
        print("     [OJO] " + a)


if __name__ == "__main__":
    main()
