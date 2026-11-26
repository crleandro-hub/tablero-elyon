#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_zpindex_cache.py - Tablero Gestion Grupo Elyon
=====================================================
Precio de OFERTA de departamentos en venta, en dolares por m2, del ZPIndex
de Zonaprop. Cordoba capital es el que interesa; CABA va al lado como
referencia viva.

Por que hace falta
------------------
El tablero mide muy bien el COSTO de construir (CAC, ICC, APYMECO, salarios)
pero no tenia nada del otro lado del negocio: a cuanto se vende. Sin eso no
se puede leer el margen, que es la pregunta de fondo del desarrollista:
cuando el costo sube mas rapido que el precio de venta, el negocio se cierra
aunque los dos esten subiendo.

De donde sale
-------------
De la propia pagina del index, no del PDF. El titular de la pagina trae el
numero y el mes en texto plano:

  "El precio medio de los departamentos de la ciudad se ubica en USD 1.474
   por m2, sube 0.8% en marzo."

y el enlace al PDF dice de que mes es el informe sin ambiguedad:

  INDEX_CBA_REPORTE_2026-03.pdf

Leer la pagina en vez del PDF evita parsear 950 KB de informe maquetado para
sacar un numero que ya esta escrito arriba.

OJO CON CORDOBA
---------------
Al 26/11/2026 Zonaprop tiene el index de Cordoba CONGELADO en marzo de 2026:
el ultimo PDF es el de 2026-03 y el mapa por barrio no se toca desde el
21/04. El de CABA en cambio sale todos los meses (2026-10 al dia), asi que no
es que se cayo el sitio: dejaron de publicar Cordoba. Por eso este script
guarda el mes de referencia y marca el dato como viejo cuando pasa el tiempo,
en vez de mostrar un numero sin fecha como si fuera de hoy. El dia que
vuelvan a publicar, lo levanta solo.

Salida: zpindex_cache.js
    window.ZPINDEX_CACHE = {
      updated, chequeado, aviso,
      plazas: { clave: { nombre, mes, usdM2, varMes, pdf, titular,
                         serie: [[mes, usdM2], ...] } }
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

CACHE_PATH = os.path.join(BASE_DIR, "zpindex_cache.js")

TIMEOUT = 40
INTENTOS = 3
ESPERA = 4
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# clave, nombre, url, sigla del PDF
PLAZAS = [
    ("cordoba", "Córdoba capital",
     "https://www.zonaprop.com.ar/blog/zpindex/cdba-venta/", "CBA"),
    ("caba", "CABA",
     "https://www.zonaprop.com.ar/blog/zpindex/caba-venta/", "CABA"),
]

# Cuantos dias puede tener el ultimo informe antes de avisar. El index sale
# mensual, asi que con 75 dias ya hay un mes entero sin publicar.
DIAS_VIEJO = 75

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

RE_TAGS = re.compile(r"<(script|style)[\s\S]*?</\1>|<[^>]+>", re.I)
RE_USD = re.compile(r"se ubica en USD\s*([\d.,]+)\s*por m2", re.I)
RE_VAR = re.compile(r"\b(sube|subi[oó]|baja|baj[oó])\s+([\d.,]+)\s*%\s+en\s+("
                    + "|".join(MESES) + r")\b", re.I)
# El titular que se muestra en el tablero. No se saca con una sola expresion
# porque los numeros llevan punto decimal ("sube 0.8%") y cualquier corte por
# punto parte la frase al medio.
def _titular(texto):
    i = texto.lower().find("el precio medio de los departamentos")
    if i < 0:
        i = texto.lower().find("el precio medio")
    if i < 0:
        return ""
    frag = re.split(r"Descarg[áa] el index|En este sitio usamos", texto[i:i + 900])[0]
    # Oracion = punto seguido de espacio y mayuscula. Asi "0.8%" no corta.
    partes = re.split(r"(?<=\.)\s+(?=[A-ZÁÉÍÓÚÑ¿])", frag)
    return " ".join(partes[:3]).strip()[:420]


def _get(url):
    """GET con reintentos. Igual criterio que el resto de los actualizadores:
    el handshake SSL falla distinto que una lectura lenta y se trata distinto."""
    r = req.Request(url, headers={"User-Agent": UA,
                                  "Accept": "text/html,*/*",
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


def _num(txt):
    """'1.474' -> 1474.0 ; '0.8' -> 0.8. Zonaprop usa el punto para los miles
    en los precios y tambien como decimal en los porcentajes, asi que se
    decide por la cantidad de digitos despues del ultimo separador."""
    s = str(txt).strip()
    m = re.search(r"[.,](\d+)$", s)
    if m and len(m.group(1)) <= 2 and len(re.sub(r"\D", "", s)) <= 4:
        return float(re.sub(r"[^\d]", "", s[:m.start()]) + "." + m.group(1))
    return float(re.sub(r"[^\d]", "", s) or 0)


def leer_plaza(url, sigla):
    """{mes, usdM2, varMes, pdf, titular} de la pagina del index."""
    html = _get(url)

    pdfs = re.findall(r"INDEX_%s_REPORTE_(\d{4})-(\d{2})\.pdf" % sigla, html)
    if not pdfs:
        raise ValueError("la pagina no tenia el enlace al PDF del informe")
    anio, mes = max(pdfs)
    ym = "%s-%s" % (anio, mes)

    texto = RE_TAGS.sub(" ", html)
    texto = re.sub(r"&nbsp;|&#\d+;", " ", texto)
    texto = re.sub(r"\s+", " ", texto)

    m = RE_USD.search(texto)
    if not m:
        raise ValueError("no se encontro el precio en USD por m2 en la pagina")
    usd = _num(m.group(1))
    if not (100 <= usd <= 20000):
        raise ValueError("el precio leido (%s) no es plausible" % usd)

    var = None
    mv = RE_VAR.search(texto)
    if mv:
        var = _num(mv.group(2))
        if mv.group(1).lower().startswith("baj"):
            var = -var

    titular = " ".join(_titular(texto).split())[:420]

    return {"mes": ym, "usdM2": usd, "varMes": var,
            "pdf": "INDEX_%s_REPORTE_%s.pdf" % (sigla, ym), "titular": titular}


def _serie_previa(clave):
    """La serie que ya quedo en el cache, para no perder meses viejos."""
    if not os.path.exists(CACHE_PATH):
        return []
    try:
        txt = open(CACHE_PATH, encoding="utf-8").read()
    except Exception:
        return []
    bloque = re.search(r'"?%s"?\s*:\s*\{(.*?)\n    \}' % clave, txt, re.S)
    if not bloque:
        return []
    return [[f, float(v)] for f, v in
            re.findall(r'\["(\d{4}-\d{2})",([\d.]+)\]', bloque.group(1))]


def _dias_desde(ym):
    a, m = int(ym[:4]), int(ym[5:7])
    # se cuenta desde el fin del mes de referencia
    fin = datetime(a + (m == 12), m % 12 + 1, 1)
    return (datetime.now() - fin).days


def main():
    print("Actualizando el ZPIndex de Zonaprop (precio de venta USD/m2)...")

    plazas, avisos = {}, []
    for clave, nombre, url, sigla in PLAZAS:
        try:
            d = leer_plaza(url, sigla)
        except Exception as e:
            print("   [AVISO] %s: %s" % (nombre, e))
            avisos.append("%s: %s" % (nombre, e))
            continue

        serie = {f: v for f, v in _serie_previa(clave)}
        nuevo = d["mes"] not in serie
        serie[d["mes"]] = d["usdM2"]
        d["serie"] = sorted([[f, v] for f, v in serie.items()])
        d["nombre"] = nombre
        d["url"] = url
        plazas[clave] = d

        dias = _dias_desde(d["mes"])
        estado = "mes nuevo" if nuevo else "sin cambios"
        print("   %-16s %s · USD %s/m2 · %s (%d dias)"
              % (nombre, d["mes"], ("%g" % d["usdM2"]), estado, dias))
        if dias > DIAS_VIEJO:
            avisos.append("Zonaprop no publica el index de %s desde %s"
                          % (nombre, d["mes"]))

    if not plazas:
        raise SystemExit("[AVISO] no se pudo leer ninguna plaza del ZPIndex. "
                         "Se conserva zpindex_cache.js como estaba.")

    def bloque(clave, d):
        serie = ",".join('["%s",%g]' % (f, v) for f, v in d["serie"])
        return (
            '    "%s": {\n' % clave
            + '      nombre: %s,\n' % _js(d["nombre"])
            + '      mes: "%s",\n' % d["mes"]
            + '      usdM2: %g,\n' % d["usdM2"]
            + '      varMes: %s,\n' % ("null" if d["varMes"] is None else "%g" % d["varMes"])
            + '      pdf: %s,\n' % _js(d["pdf"])
            + '      url: %s,\n' % _js(d["url"])
            + '      titular: %s,\n' % _js(d["titular"])
            + '      serie: [%s]\n' % serie
            + '    }')

    js = (
        "/* ═══════════════════════════\n"
        "   zpindex_cache.js  -  Grupo Elyon\n"
        "   Generado por update_zpindex_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: ZPIndex de Zonaprop · precio de OFERTA de departamentos\n"
        "   en venta, en dolares por m2. Es precio PEDIDO, no escriturado.\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════ */\n"
        "window.ZPINDEX_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "Zonaprop · ZPIndex",\n'
        "  plazas: {\n"
        + ",\n".join(bloque(k, plazas[k]) for k in plazas if k in plazas)
        + "\n  }\n};\n"
    )

    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)
    os.replace(tmp, CACHE_PATH)

    marcar(CACHE_PATH, "; ".join(avisos) if avisos else None)

    print("\n[OK] zpindex_cache.js")
    for k, d in plazas.items():
        print("     %-16s %s · USD %g/m2 · %d mes(es) en la serie"
              % (d["nombre"], d["mes"], d["usdM2"], len(d["serie"])))
    for a in avisos:
        print("     [OJO] " + a)


def _js(s):
    return '"' + str(s).replace("\\", "/").replace('"', "'") + '"'


if __name__ == "__main__":
    main()
