#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_riesgo_cache.py - Tablero Gestion Grupo Elyon
=====================================================
Genera riesgo_cache.js con el riesgo pais (EMBI+ Argentina).

Por que existe
--------------
El tablero venia leyendo la API de argentinadatos.com directamente desde el
navegador. Esa API funciona bien pero publica con rezago: al 07/08/2026 daba
421 puntos con fecha 04/08, mientras Rava Bursatil ya mostraba 448 del mismo
dia. Tres dias y 27 puntos de diferencia.

Rava no se puede consultar desde el navegador (no habilita CORS), asi que el
dato se baja desde aca y queda guardado en riesgo_cache.js. El tablero se
queda con el mas reciente entre el cache y la API.

Fuentes, en orden:
    1. Rava Bursatil - pagina de perfil de RIESGO PAIS (valor del dia +
       tabla de cotizaciones historicas)
    2. Rava Bursatil - pagina "historico/riesgo-pais/hoy"
    3. argentinadatos.com - API publica (respaldo, con rezago)

Uso:
    python update_riesgo_cache.py
"""

import json
import os
import re
import ssl
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "riesgo_cache.js")
TIMEOUT = 25
DIAS_SERIE = 400          # cuantos dias de historico guardar

RAVA_PERFIL = "https://www.rava.com/perfil/RIESGO%20PAIS"
RAVA_HOY = "https://www.rava.com/cotizaciones/historico/riesgo-pais/hoy/"
API_ULTIMO = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo"
API_SERIE = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def _get(url):
    """GET con reintento sin verificar el certificado (algunas PC corporativas
    tienen el store de certificados desactualizado y falla el handshake)."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/json,*/*",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            return resp.read().decode("utf-8", "replace")


def _num(txt):
    """'1.081,00' -> 1081.0   |   '448,00' -> 448.0"""
    t = str(txt).strip().replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _sin_tags(html):
    """Saca scripts, estilos y etiquetas: queda el texto con separadores."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", "|", html)
    html = html.replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", html)


def parse_rava_serie(html):
    """Saca la tabla de cotizaciones historicas de la pagina de Rava.

    No se ata a la estructura del HTML: busca fechas dd/mm/aaaa seguidas de
    cuatro numeros (apertura, maximo, minimo, cierre) y se queda con el
    cierre. Asi sigue funcionando si Rava cambia clases o etiquetas."""
    texto = _sin_tags(html)
    patron = re.compile(
        r"(\d{2}/\d{2}/\d{4})"
        r"[^\d]{1,12}([\d.]+,\d{2})"
        r"[^\d]{1,12}([\d.]+,\d{2})"
        r"[^\d]{1,12}([\d.]+,\d{2})"
        r"[^\d]{1,12}([\d.]+,\d{2})")

    out = {}
    for fecha, _ap, _max, _min, cierre in patron.findall(texto):
        d, m, a = fecha.split("/")
        v = _num(cierre)
        # El riesgo pais argentino se movio historicamente entre 100 y 25.000
        # puntos. Un valor fuera de rango es basura de la pagina, no un dato.
        if v and 50 <= v <= 30000:
            out["%s-%s-%s" % (a, m, d)] = v
    return sorted(out.items())


def parse_rava_ultimo(html):
    """Valor del momento + hora, desde el <meta description> o el titulo.
    Ej: '$448,00 (+0,40%)' y '07/08 11:45'."""
    valor = variacion = hora = None

    m = re.search(r'(?is)<meta[^>]+(?:name|property)="(?:og:)?description"[^>]+'
                  r'content="[^"]*?\$\s*([\d.]+,\d{2})\s*\(([+-]?[\d.,]+)%\)', html)
    if not m:
        m = re.search(r'(?is)<title>[^<]*?\$\s*([\d.]+,\d{2})\s*\(([+-]?[\d.,]+)%\)', html)
    if m:
        valor = _num(m.group(1))
        variacion = _num(m.group(2))

    h = re.search(r"(\d{2}/\d{2})\s+(\d{2}:\d{2})", _sin_tags(html))
    if h:
        hora = h.group(1) + " " + h.group(2)

    return valor, variacion, hora


def fuente_rava():
    """(serie, ultimo, etiqueta) desde Rava Bursatil."""
    for url in (RAVA_PERFIL, RAVA_HOY):
        try:
            html = _get(url)
        except Exception as e:
            print("[AVISO] Rava " + url.rsplit("/", 2)[-2] + ": " + str(e))
            continue

        serie = parse_rava_serie(html)
        valor, variacion, hora = parse_rava_ultimo(html)

        if serie or valor:
            # El valor intradiario todavia no esta en la tabla de cierres:
            # se agrega como dato del dia para no perder frescura.
            if valor and hora:
                d, m = hora.split()[0].split("/")
                hoy = "%s-%s-%s" % (datetime.now().year, m, d)
                serie = [p for p in serie if p[0] != hoy] + [(hoy, valor)]
                serie.sort()
            if serie:
                print("[OK] Riesgo pais desde Rava Bursatil: %s puntos al %s"
                      % (int(serie[-1][1]), serie[-1][0]))
                return serie, serie[-1], "Rava Bursátil"
        print("[AVISO] Rava respondio pero no se pudo leer la cotizacion.")
    return [], None, None


def fuente_api():
    """Respaldo: API de argentinadatos (misma que usaba el tablero)."""
    try:
        arr = json.loads(_get(API_SERIE))
        serie = sorted({str(r["fecha"])[:10]: float(r["valor"])
                        for r in arr if r.get("valor") is not None}.items())
        if serie:
            print("[OK] Riesgo pais desde argentinadatos: %s puntos al %s"
                  % (int(serie[-1][1]), serie[-1][0]))
            return serie, serie[-1], "argentinadatos.com"
    except Exception as e:
        print("[AVISO] argentinadatos: " + str(e))
    return [], None, None


def main():
    print("Actualizando riesgo_cache.js ...\n")

    serie, ultimo, fuente = fuente_rava()
    if not serie:
        print("      Rava no respondio, se usa la API de respaldo.")
        serie, ultimo, fuente = fuente_api()

    if not serie:
        raise SystemExit("\n[ERROR] Ninguna fuente devolvio el riesgo pais. "
                         "Se conserva el riesgo_cache.js anterior.")

    serie = serie[-DIAS_SERIE:]
    prev = serie[-2][1] if len(serie) > 1 else None
    varDia = round((ultimo[1] / prev - 1) * 100, 2) if prev else None

    filas = ",\n".join('    ["%s", %s]' % (f, ("%g" % v)) for f, v in serie)
    js = (
        "/* ═══════════════════════════════════════════════════\n"
        "   riesgo_cache.js  -  Grupo Elyon\n"
        "   Generado por update_riesgo_cache.py el "
        + datetime.now().strftime("%d/%m/%Y %H:%M") + "\n"
        "   Fuente: " + fuente + "\n"
        "   NO editar a mano: se pisa en cada corrida.\n"
        "═══════════════════════════════════════════════════ */\n"
        "window.RIESGO_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  fecha: "' + ultimo[0] + '",\n'
        "  valor: " + ("%g" % ultimo[1]) + ",\n"
        "  varDia: " + (("%g" % varDia) if varDia is not None else "null") + ",\n"
        "  serie: [\n" + filas + "\n  ]\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    print("\n[OK] riesgo_cache.js")
    print("     %s puntos al %s (%s)" % (int(ultimo[1]), ultimo[0], fuente))
    print("     %s dias de historico" % len(serie))


if __name__ == "__main__":
    main()
