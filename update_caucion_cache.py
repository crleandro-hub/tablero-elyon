#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_caucion_cache.py - Tablero Gestion Grupo Elyon
=====================================================
Genera caucion_cache.js con la tasa de caucion bursatil en pesos a 1, 7 y
14 dias (TNA, %), tal como la publica Rava Bursatil.

Que es la caucion:
    Un prestamo de muy corto plazo garantizado con titulos, dentro de BYMA.
    El colocador pone pesos y se lleva la tasa; el tomador deja titulos en
    garantia. Para nosotros es el piso de referencia del costo del dinero a
    dias: sirve para decidir si conviene dejar la caja quieta, colocarla, o
    tomar plata contra los excedentes de obra.

Por que hace falta este script:
    Rava no habilita CORS, asi que el navegador no puede pedirle los datos.
    Python si puede. El tablero lee caucion_cache.js.

Ojo con el dato:
    La caucion a 1 dia es MUY volatil intradiario (puede pasar de 9% a 40%
    en la misma rueda). Lo que se guarda aca es el ULTIMO valor operado de
    la rueda, que es el mismo que muestra la pagina de Rava. No es un
    promedio ponderado por monto: para eso hay que ir al informe de BYMA.

Fuentes, en orden de intento:
    1. Rava clasico - API publica de historicos (token tomado de la pagina)
    2. Rava www     - tabla "Cotizaciones historicas" del perfil (HTML)
    3. Rava www     - meta og:description del perfil (solo ultimo valor)

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import html as htmllib
import json
import os
import re
import ssl
import urllib.parse
import urllib.request as req
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "caucion_cache.js")

RAVA_API = "https://clasico.rava.com/lib/restapi/v3/publico/cotizaciones/historicos"
RAVA_TOKEN_URL = "https://clasico.rava.com/perfil/MERVAL"
RAVA_PERFIL = "https://www.rava.com/perfil/"

# clave interna -> (especie en Rava, etiqueta para el tablero)
PLAZOS = [
    ("d1",  "CAUCION 1D",  "1 día"),
    ("d7",  "CAUCION 7D",  "7 días"),
    ("d14", "CAUCION 14D", "14 días"),
]

ANIOS_SERIE = 2
TIMEOUT = 30

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def _get(url):
    """GET con reintento sin verificacion SSL (algunas instalaciones Windows
    no traen la cadena de certificados completa)."""
    r = req.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/json,*/*",
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


def _post(url, campos):
    body = urllib.parse.urlencode(campos).encode()
    r = req.Request(url, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json, */*",
        "Referer": RAVA_TOKEN_URL,
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


def _num(txt):
    """'21,80' o '1.234,5' -> float. Devuelve None si no es un numero."""
    s = str(txt).strip().replace(".", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────
#  Fuente 1: API de Rava clasico
# ─────────────────────────────────────────────────────────────
_token_cache = []


def _token():
    """El access_token de la API viene embebido en el HTML del perfil."""
    if _token_cache:
        return _token_cache[0]
    doc = _get(RAVA_TOKEN_URL).decode("utf-8", "replace")
    m = re.search(r'access[_-]?token["\']?\s*[:=]\s*["\']([A-Za-z0-9._-]{10,})["\']',
                  doc, re.I)
    if not m:
        raise ValueError("no se encontro el access_token en la pagina de Rava")
    _token_cache.append(m.group(1))
    return _token_cache[0]


def serie_api(especie):
    """[(fecha ISO, cierre)] ascendente desde la API de Rava clasico."""
    hasta = datetime.now()
    desde = hasta - timedelta(days=365 * ANIOS_SERIE)
    crudo = _post(RAVA_API, {
        "access_token": _token(),
        "especie": especie,
        "fecha_inicio": desde.strftime("%Y-%m-%d"),
        "fecha_fin": hasta.strftime("%Y-%m-%d"),
    })
    j = json.loads(crudo)
    filas = j.get("body") or j.get("data") or j.get("datos") or []

    out = {}
    for f in filas:
        if not isinstance(f, dict):
            continue
        fecha = str(f.get("fecha") or f.get("Fecha") or "")[:10]
        cierre = f.get("cierre", f.get("Cierre", f.get("close")))
        if len(fecha) == 10 and cierre not in (None, ""):
            try:
                out[fecha] = float(cierre)
            except (TypeError, ValueError):
                pass
    if not out:
        raise ValueError("la API no devolvio cotizaciones")
    return sorted(out.items())


# ─────────────────────────────────────────────────────────────
#  Fuente 2: tabla de cotizaciones historicas del perfil
# ─────────────────────────────────────────────────────────────
def serie_perfil(especie):
    """[(fecha ISO, cierre)] leyendo la tabla del perfil de www.rava.com.

    La tabla viene servida en el HTML (no la arma JavaScript), asi que
    alcanza con leer las filas: Fecha | Apertura | Maximo | Minimo | Cierre."""
    doc = _get(RAVA_PERFIL + urllib.parse.quote(especie)).decode("utf-8", "replace")

    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", doc, re.S | re.I):
        celdas = [htmllib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                  for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(celdas) < 5:
            continue
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", celdas[0])
        if not m:
            continue
        cierre = _num(celdas[4])
        if cierre is None:
            continue
        out["%s-%s-%s" % (m.group(3), m.group(2), m.group(1))] = cierre

    if not out:
        raise ValueError("no se encontraron filas en la tabla del perfil")
    return sorted(out.items())


# ─────────────────────────────────────────────────────────────
#  Fuente 3: ultimo valor del meta og:description
# ─────────────────────────────────────────────────────────────
def ultimo_meta(especie):
    """(fecha ISO de hoy, valor) leido del meta og:description del perfil.

    Es el ultimo recurso: Rava pone ahi el precio y la variacion, por ejemplo
    '$21,80 (+36,30%). Tasa de la caucion...'. No trae fecha, asi que se
    asume la rueda de hoy."""
    doc = _get(RAVA_PERFIL + urllib.parse.quote(especie)).decode("utf-8", "replace")
    m = re.search(r'property=["\']og:description["\']\s+content=["\']([^"\']+)', doc, re.I)
    if not m:
        m = re.search(r'name=["\']description["\']\s+content=["\']([^"\']+)', doc, re.I)
    if not m:
        raise ValueError("no se encontro el meta description")
    v = re.search(r"\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]+|[0-9]+[.,][0-9]+)",
                  htmllib.unescape(m.group(1)))
    if not v:
        raise ValueError("el meta description no traia un numero")
    val = _num(v.group(1))
    if val is None:
        raise ValueError("no se pudo interpretar el numero del meta")
    return [(datetime.now().strftime("%Y-%m-%d"), val)]


def serie(especie):
    """Cascada de fuentes. Devuelve [] si ninguna responde."""
    for fn, etiqueta in ((serie_api, "API Rava clasico"),
                         (serie_perfil, "tabla del perfil"),
                         (ultimo_meta, "meta del perfil")):
        try:
            s = fn(especie)
            if s:
                print("[OK] " + especie + " desde " + etiqueta
                      + " (" + str(len(s)) + " ruedas)")
                return s
        except Exception as e:
            print("[AVISO] " + especie + " / " + etiqueta + ": " + str(e))
    return []


def main():
    print("Actualizando caucion_cache.js ...")

    datos = {}
    for clave, especie, etiqueta in PLAZOS:
        s = serie(especie)
        if not s:
            datos[clave] = None
            continue
        fecha, valor = s[-1]
        prev = s[-2][1] if len(s) > 1 else None
        datos[clave] = {
            "etiqueta": etiqueta,
            "fecha": fecha,
            "valor": round(valor, 2),
            # Variacion en PUNTOS porcentuales, no en %: pasar de 16% a 21,8%
            # es "+5,8 pp". Decir "+36%" sobre una tasa confunde mas de lo que
            # aclara, sobre todo con la caucion a 1 dia que salta todo el tiempo.
            "varPp": round(valor - prev, 2) if prev is not None else None,
            "serie": [[f, round(v, 2)] for f, v in s[-260:]],
        }

    if not any(datos.values()):
        raise SystemExit("[ERROR] Ninguna fuente devolvio las tasas de caucion. "
                         "Se conserva el cache anterior.")

    def bloque(clave):
        d = datos.get(clave)
        if not d:
            return "  " + clave + ": null,\n"
        filas = ",".join('["%s",%s]' % (f, v) for f, v in d["serie"])
        return (
            "  " + clave + ": {\n"
            '    etiqueta: "' + d["etiqueta"] + '",\n'
            '    fecha: "' + d["fecha"] + '",\n'
            "    valor: " + str(d["valor"]) + ",\n"
            "    varPp: " + (str(d["varPp"]) if d["varPp"] is not None else "null") + ",\n"
            "    serie: [" + filas + "]\n"
            "  },\n"
        )

    js = (
        "/* -----------------------------------------------------------------\n"
        "   caucion_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n"
        "   Tasa de caucion bursatil en pesos (TNA %), fuente Rava Bursatil.\n"
        "   d1 / d7 / d14 = plazos de 1, 7 y 14 dias.\n"
        "   valor = ultimo valor operado de la rueda (no es promedio ponderado)\n"
        "   varPp = variacion contra la rueda anterior, en puntos porcentuales\n"
        "----------------------------------------------------------------- */\n"
        "window.CAUCION_CACHE = {\n"
        + bloque("d1") + bloque("d7") + bloque("d14")
        + '  fuente: "Caución BYMA · Rava Bursátil",\n'
        + '  updated: "' + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + '"\n'
        + "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(js)

    resumen = " / ".join(
        c + " " + (str(datos[c]["valor"]) + "%" if datos.get(c) else "N/D")
        for c in ("d1", "d7", "d14"))
    print("[OK] caucion_cache.js  ->  " + resumen)


if __name__ == "__main__":
    main()
