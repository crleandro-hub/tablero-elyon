#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_rem_cache.py - Tablero Gestion Grupo Elyon
=================================================
Genera rem_cache.js con la inflacion esperada del REM (Relevamiento de
Expectativas de Mercado) que publica el BCRA todos los meses.

Fuente principal: la planilla oficial del BCRA
    https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/informes/
    tablas-relevamiento-expectativas-mercado-<mes>-<anio>.xlsx
Se prueba el mes corriente y se va hacia atras hasta encontrar la ultima
publicada (el REM de un mes sale a principios del mes siguiente).

Se lee con xlsx_lite.py, que usa solo la libreria estandar: asi el script no
depende de que la PC tenga openpyxl ni pandas instalados.

Fuente de respaldo: bcra-rem-api, un servicio abierto que normaliza la misma
planilla. Puede quedar desactualizado, por eso va segundo.

Que guarda:
    m12     -> mediana esperada para los proximos 12 meses (var. % i.a.)
                 es el numero que el BCRA destaca como "inflacion esperada"
    anual   -> mediana esperada para diciembre del año en curso (var. % i.a.)
    mensual -> mediana del primer mes proyectado (var. % mensual)
    relev   -> mes del relevamiento, para mostrar la antiguedad del dato

Ejecutar diariamente via tarea programada, antes de build_publicar.py.
"""

import json
import re
import os
import ssl
import sys
import unicodedata
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from xlsx_lite import leer_hoja  # noqa: E402

CACHE_PATH = os.path.join(BASE_DIR, "rem_cache.js")

BCRA_PORTADA = "https://www.bcra.gob.ar/relevamiento-expectativas-mercado-rem/"
BCRA_URL = ("https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/"
            "informes/tablas-relevamiento-expectativas-mercado-{mes}-{anio}.xlsx")
MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_ALT = {"sep": "set"}          # el BCRA alterno esta abreviatura alguna vez
HOJA = "Cuadros de resultados"
MESES_ATRAS = 6                     # cuantos relevamientos hacia atras probar

API = "https://bcra-rem-api.facujallia.workers.dev/api"
TIMEOUT = 45


def _get(url, binario=False):
    # Encabezados de navegador: el sitio del BCRA rechaza pedidos "pelados"
    r = req.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/126.0.0.0 Safari/537.36"),
        "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                   "application/vnd.openxmlformats-officedocument."
                   "spreadsheetml.sheet,*/*;q=0.8"),
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Referer": "https://www.bcra.gob.ar/",
        "Connection": "close",
    })
    try:
        with req.urlopen(r, timeout=TIMEOUT) as resp:
            data = resp.read()
    except Exception:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with req.urlopen(r, timeout=TIMEOUT, context=ctx) as resp:
            data = resp.read()
    return data if binario else json.loads(data)


def sin_tildes(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# ─────────────────────────────────────────────────────────────
#  Fuente 1: planilla oficial del BCRA
# ─────────────────────────────────────────────────────────────
#  La planilla "Cuadros de resultados" no tiene una posicion fija: segun el
#  mes, las tablas arrancan en la columna A o en la B (el BCRA suele dejar una
#  columna de margen), los numeros vienen como numero o como texto con coma
#  decimal, y el rotulo del periodo puede ser una fecha ("2026-08-01"), una
#  abreviatura ("ago-26") o un año suelto ("2026").
#
#  La version anterior daba por sentado que el periodo estaba en la columna 0.
#  Cuando el BCRA corrio las tablas una columna a la derecha, TODAS las filas
#  quedaban con rotulo vacio, no matcheaba ninguna y el script terminaba en
#  "la planilla no trae medianas de IPC" — que es lo que venia pasando.
#
#  Ahora no se asume nada de la ubicacion: el rotulo es la primera celda no
#  vacia de la fila y la mediana se busca por el encabezado. Si aun asi falla,
#  se deja _rem_diagnostico.txt con el volcado de la hoja para poder arreglarlo
#  sin tener que adivinar.
# ─────────────────────────────────────────────────────────────
DIAG_PATH = os.path.join(BASE_DIR, "_rem_diagnostico.txt")

MES_ABREV = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
             "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}


def _texto(c):
    """Celda -> texto limpio. Los años vienen como 2026.0 y hay que verlos 2026."""
    if c is None:
        return ""
    if isinstance(c, float) and c == int(c):
        return str(int(c))
    return str(c).strip()


def _num(v):
    """Numero tolerante: acepta 2.1, '2,1', '2,1%', '1.234,56' y ' '."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("%", "").replace(" ", "").replace("\u00a0", "")
    if not s or s in ("-", "--", "s/d", "n/d"):
        return None
    if "," in s and "." in s:          # 1.234,56 -> formato local
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _rotulo(fila):
    """Primera celda no vacia: el periodo, este en la columna que este."""
    for c in fila:
        t = _texto(c)
        if t:
            return t
    return ""


def _fila_texto(fila):
    return " ".join(sin_tildes(_texto(c)) for c in fila if _texto(c))


def _es_mes(per):
    """'2026-08-01', 'ago-26', 'ago-2026', '2026-08' -> True."""
    if re.match(r"^\d{4}-\d{1,2}", per):
        return True
    m = re.match(r"^([a-z]{3})[-/\s.]*(\d{2,4})$", per)
    return bool(m and m.group(1) in MES_ABREV)


def _bloques(filas, es_titulo, es_corte):
    """Todos los cuadros cuyo titulo matchea. Devuelve [(header, filas), ...].

    Se devuelven todos los candidatos y no el primero, porque la hoja suele
    tener un indice arriba que menciona los mismos titulos: si se agarra ese,
    no hay datos abajo. El que llama prueba en orden y se queda con el que
    realmente trae medianas."""
    out = []
    for i, fila in enumerate(filas):
        if not es_titulo(_fila_texto(fila)):
            continue
        header = hdr_i = None
        for j in range(i + 1, min(i + 8, len(filas))):
            t = _fila_texto(filas[j])
            if "periodo" in t or "referencia" in t or "mediana" in t:
                header, hdr_i = filas[j], j
                break
        if header is None:
            continue
        datos, vacias = [], 0
        for k in range(hdr_i + 1, len(filas)):
            t = _fila_texto(filas[k])
            if not t:
                vacias += 1
                if vacias >= 2:
                    break
                continue
            vacias = 0
            if es_corte(t):
                break
            datos.append(filas[k])
        if datos:
            out.append((header, datos))
    return out


_CORTES = ("precios minoristas", "tasa de interes", "tipo de cambio",
           "actividad economica", "ipc nivel general", "ipc nucleo",
           "tasa de politica monetaria", "desocupacion", "exportaciones")


def _bloques_ipc(filas):
    return _bloques(
        filas,
        lambda t: "ipc nivel general" in t and "nucleo" not in t,
        lambda t: any(c in t for c in _CORTES if c != "ipc nivel general"))


def _bloques_tcn(filas):
    return _bloques(
        filas,
        lambda t: "tipo de cambio nominal" in t,
        lambda t: any(c in t for c in _CORTES if c != "tipo de cambio"))


def _col_mediana(header):
    for i, c in enumerate(header):
        if c is not None and "mediana" in sin_tildes(_texto(c)):
            return i
    return 2   # en la planilla del BCRA la mediana suele ser la tercera columna


def _medianas_ipc(header, datos, anio):
    col = _col_mediana(header)
    res = {"m12": None, "anual": None, "mensual": None}
    for fila in datos:
        per = sin_tildes(_rotulo(fila))
        if not per:
            continue
        v = _num(fila[col]) if col < len(fila) else None
        if v is None:
            continue
        if "12 meses" in per:
            if res["m12"] is None:
                res["m12"] = round(v, 4)
        elif re.fullmatch(r"%d(\.0)?" % anio, per):
            if res["anual"] is None:
                res["anual"] = round(v, 4)
        elif _es_mes(per) and res["mensual"] is None:
            res["mensual"] = round(v, 4)
    return res


def _tcn(header, datos, anio):
    """Nivel esperado del dolar mayorista para dic del año y del anterior."""
    col = _col_mediana(header)
    dic_act = dic_prev = None
    for fila in datos:
        per = sin_tildes(_rotulo(fila))
        if not per:
            continue
        v = _num(fila[col]) if col < len(fila) else None
        if v is None:
            continue
        for a, marca in ((anio, "act"), (anio - 1, "prev")):
            if re.match(r"^%d-12" % a, per) or re.match(r"^dic[-/\s.]*%s$" % str(a)[2:], per) \
               or re.match(r"^dic[-/\s.]*%d$" % a, per):
                if marca == "act":
                    dic_act = v
                else:
                    dic_prev = v
    ia = round((dic_act / dic_prev - 1) * 100, 1) if (dic_act and dic_prev) else None
    # El TCN va redondeado: la planilla trae la mediana con 12 decimales y sin
    # esto el cache guardaba "1651.792801841703", que ademas se ve en pantalla.
    return (round(dic_act, 2) if dic_act is not None else None), ia


def _volcar_diagnostico(contenido, motivo):
    """Deja la hoja en texto plano para poder corregir el parser sin adivinar."""
    try:
        from xlsx_lite import nombres_de_hojas
        lineas = ["Diagnostico REM - " + datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "Motivo: " + motivo, ""]
        try:
            lineas.append("Hojas del archivo: " + ", ".join(nombres_de_hojas(contenido)))
        except Exception as e:
            lineas.append("No se pudieron listar las hojas: %s" % e)
        lineas.append("")
        filas = leer_hoja(contenido, HOJA)
        lineas.append("Hoja '%s': %d filas. Primeras 220:" % (HOJA, len(filas)))
        for i, fila in enumerate(filas[:220]):
            celdas = " | ".join(_texto(c) for c in fila)
            if celdas.strip():
                lineas.append("%4d: %s" % (i, celdas[:300]))
        with open(DIAG_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
        print("   [diagnostico] volcado en _rem_diagnostico.txt")
    except Exception as e:
        print("   [diagnostico] no se pudo volcar: %s" % e)


def parsear_xlsx(contenido, anio):
    filas = leer_hoja(contenido, HOJA)

    candidatos = _bloques_ipc(filas)
    if not candidatos:
        raise ValueError("No se encontro el cuadro de IPC nivel general")

    res = None
    for header, datos in candidatos:
        parcial = _medianas_ipc(header, datos, anio)
        if parcial["m12"] is not None or parcial["anual"] is not None:
            res = parcial
            break
    if res is None:
        raise ValueError("El cuadro de IPC no trajo medianas reconocibles")

    res["tcnDic"], res["tcnIa"] = None, None
    for header, datos in _bloques_tcn(filas):
        dic, ia = _tcn(header, datos, anio)
        if dic is not None:
            res["tcnDic"], res["tcnIa"] = dic, ia
            break
    return res


def _mes_de_url(url):
    """'...-jul-2026.xlsx' -> '2026-07'."""
    m = re.search(r"-([a-z]{3})-(\d{4})\.xlsx", url, re.I)
    if not m:
        return None
    ab = m.group(1).lower()
    if ab == "set":
        ab = "sep"
    if ab not in MESES:
        return None
    return "%s-%02d" % (m.group(2), MESES.index(ab) + 1)


def _intentar_xlsx(url, etiqueta):
    """Baja y parsea una planilla. Devuelve el dict de resultados o None."""
    try:
        contenido = _get(url, binario=True)
    except Exception as e:
        print("   [%s] no se pudo bajar: %s" % (etiqueta, e))
        return None
    if contenido[:2] != b"PK":
        print("   [%s] la respuesta no es un xlsx (%d bytes)" % (etiqueta, len(contenido)))
        return None
    try:
        res = parsear_xlsx(contenido, datetime.now().year)
    except Exception as e:
        print("   [%s] no se pudo parsear: %s" % (etiqueta, e))
        _volcar_diagnostico(contenido, "%s: %s" % (etiqueta, e))
        return None
    if res["m12"] is None and res["anual"] is None:
        print("   [%s] la planilla no trae medianas de IPC" % etiqueta)
        _volcar_diagnostico(contenido, "%s: sin medianas de IPC" % etiqueta)
        return None
    return res


def desde_portada():
    """Lee el link a la planilla desde la pagina del REM.

    Es el camino mas confiable: no depende de adivinar el nombre del archivo
    ni de que el BCRA mantenga la convencion mes-anio."""
    try:
        html = _get(BCRA_PORTADA, binario=True).decode("utf-8", "replace")
    except Exception as e:
        print("   [portada] no se pudo abrir la pagina del REM: %s" % e)
        return None

    links = re.findall(
        r'href="([^"]*tablas-relevamiento-expectativas-mercado[^"]*\.xlsx)"',
        html, re.I)
    if not links:
        print("   [portada] la pagina no lista ninguna planilla .xlsx")
        return None

    for href in links[:3]:
        url = href if href.startswith("http") else "https://www.bcra.gob.ar" + href
        res = _intentar_xlsx(url, "portada")
        if res:
            res["relev"] = _mes_de_url(url)
            res["fuente"] = "BCRA (planilla oficial)"
            print("[OK] REM desde la planilla enlazada en la pagina del BCRA (%s)"
                  % res["relev"])
            return res
    return None


def desde_bcra():
    """Prueba los ultimos relevamientos hasta encontrar uno publicado."""
    print("Buscando la planilla del REM en bcra.gob.ar ...")

    res = desde_portada()
    if res:
        return res

    hoy = datetime.now()
    anio, mes = hoy.year, hoy.month

    for _ in range(MESES_ATRAS):
        # El REM de un mes se publica al mes siguiente: empezamos por el previo
        mes -= 1
        if mes == 0:
            mes, anio = 12, anio - 1

        abrevs = [MESES[mes - 1]]
        if MESES[mes - 1] in MESES_ALT:
            abrevs.append(MESES_ALT[MESES[mes - 1]])

        for ab in abrevs:
            url = BCRA_URL.format(mes=ab, anio=anio)
            res = _intentar_xlsx(url, "%s-%s" % (ab, anio))
            if res:
                res["relev"] = "%04d-%02d" % (anio, mes)
                res["fuente"] = "BCRA (planilla oficial)"
                print("[OK] REM %s-%s desde la planilla del BCRA" % (ab, anio))
                return res
    return None


# ─────────────────────────────────────────────────────────────
#  Fuente 2: API abierta que normaliza la misma planilla
# ─────────────────────────────────────────────────────────────
def _relev_desde_referencia(datos):
    """Deduce el mes del relevamiento de la fila 'proximos 12 meses'.

    Su columna 'referencia' dice, por ejemplo, 'var. % i.a.; abr-27': el
    horizonte es 12 meses despues del relevamiento, asi que restando un año
    sale abr-26. Se usa para no gastar un segundo pedido en /metadata, que el
    servicio rechaza por limitar a 1 llamada por minuto y por IP."""
    abrev = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
             "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}
    for f in datos:
        per = sin_tildes(f.get("período", f.get("periodo", "")))
        if "12 meses" not in per:
            continue
        ref = sin_tildes(f.get("referencia", ""))
        m = re.search(r"([a-z]{3})-(\d{2})", ref)
        if m and m.group(1) in abrev:
            return "%04d-%02d" % (2000 + int(m.group(2)) - 1, abrev[m.group(1)])
    return None


def desde_api():
    print("Probando la API abierta de respaldo ...")
    try:
        datos = (_get(API + "/ipc_general") or {}).get("datos") or []
    except Exception as e:
        print("   API REM: " + str(e))
        return None
    if not datos:
        return None

    anio = datetime.now().year

    def mediana(pred):
        for f in datos:
            per = str(f.get("período", f.get("periodo", "")))
            if pred(per) and f.get("mediana") is not None:
                return round(float(f["mediana"]), 4)
        return None

    res = {
        "m12":     mediana(lambda p: "12 meses" in p.lower()),
        "anual":   mediana(lambda p: p == str(anio)),
        "mensual": mediana(lambda p: p[:4].isdigit() and len(p) >= 7),
        "relev":   _relev_desde_referencia(datos),
        "fuente":  "bcra-rem-api",
        # La API de respaldo solo normaliza el cuadro de IPC. Sin TCN, el
        # tablero deja la tarjeta de devaluacion en N/D en vez de inventar.
        "tcnDic":  None,
        "tcnIa":   None,
    }
    if res["m12"] is None and res["anual"] is None:
        return None
    print("[OK] REM desde la API abierta (relevamiento %s)" % res["relev"])
    return res


def relev_actual():
    """Relevamiento que ya esta guardado en rem_cache.js, si lo hay."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            m = re.search(r'relev:\s*"(\d{4}-\d{2})"', f.read())
        return m.group(1) if m else None
    except Exception:
        return None


def marcar_chequeado(aviso=None):
    """Deja constancia de que el script CORRIO, sin tocar los datos.

    Hace falta para no mentirle al tablero. El REM se publica una vez por mes:
    entre publicacion y publicacion el archivo no cambia, y el tablero -que
    miraba la fecha de "updated"- concluia que "el script no corre desde hace N
    dias" cuando en realidad corria todos los dias y no habia nada nuevo que
    traer. Ahora "chequeado" dice cuando corrio y "aviso" por que no se pudo
    refrescar, que son dos cosas distintas."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return
    # se sacan las marcas anteriores y se reescriben arriba de todo, asi nunca
    # quedan al final (donde una coma de mas romperia el objeto)
    txt = re.sub(r"\n\s*(chequeado|aviso):[^\n]*", "", txt)
    marca = '\n  chequeado: "%s",' % datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if aviso:
        marca += '\n  aviso: "%s",' % str(aviso).replace('"', "'")[:180]
    txt = txt.replace("window.REM_CACHE = {", "window.REM_CACHE = {" + marca, 1)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception:
        pass


def main():
    print("Actualizando rem_cache.js ...")

    res = desde_bcra() or desde_api()
    if not res:
        marcar_chequeado("no se pudo bajar el REM de ninguna fuente")
        raise SystemExit("[ERROR] No se pudo obtener el REM. "
                         "Se conserva el cache anterior.")

    # No pisar un relevamiento nuevo con uno mas viejo. La API de respaldo
    # suele quedar atrasada varios meses; si el cache ya tiene algo mas
    # reciente, se lo deja como esta.
    previo = relev_actual()
    if previo and res.get("relev") and res["relev"] < previo:
        print("[SIN CAMBIOS] El cache ya tiene el relevamiento %s, mas nuevo "
              "que el %s que devolvio %s." % (previo, res["relev"], res["fuente"]))
        marcar_chequeado(
            "la planilla del BCRA no se pudo leer; %s solo llega a %s y el cache "
            "ya tiene %s" % (res["fuente"], res["relev"], previo)
            if res["fuente"] != "BCRA (planilla oficial)" else None)
        return
    if previo and res.get("relev") == previo:
        # Mismo relevamiento. Si vino de la planilla oficial se reescribe igual:
        # es la fuente autoritativa y conviene que pise cualquier carga manual.
        # Si vino del respaldo, no se toca el dato: solo se deja constancia de
        # que el script corrio.
        if res["fuente"] != "BCRA (planilla oficial)":
            print("[SIN CAMBIOS] El BCRA sigue en el relevamiento %s y el dato "
                  "actual no viene de la planilla oficial: no se toca." % previo)
            marcar_chequeado()
            return
        print("[IGUAL RELEVAMIENTO] %s ya estaba cargado; se reescribe con los "
              "valores de la planilla oficial." % previo)

    anio = datetime.now().year

    def js(v):
        if v is None:
            return "null"
        return '"%s"' % v if isinstance(v, str) else str(v)

    contenido = (
        "/* -----------------------------------------------------------------\n"
        "   rem_cache.js  -  Grupo Elyon  |  Actualizado automaticamente\n"
        "   Generado: " + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n"
        "   Fuente: " + res["fuente"] + "\n"
        "   m12   = var. % i.a. esperada para los proximos 12 meses\n"
        "   anual = var. % i.a. esperada a diciembre del año en curso\n"
        "   tcnDic = tipo de cambio nominal ($/US$) esperado para dic del año\n"
        "   tcnIa  = devaluacion % i.a. esperada a dic contra dic anterior\n"
        "----------------------------------------------------------------- */\n"
        "window.REM_CACHE = {\n"
        '  chequeado: "' + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + '",\n'
        "  aviso: null,\n"
        "  m12: " + js(res["m12"]) + ",\n"
        "  anual: " + js(res["anual"]) + ",\n"
        "  mensual: " + js(res["mensual"]) + ",\n"
        "  tcnDic: " + js(res.get("tcnDic")) + ",\n"
        "  tcnIa: " + js(res.get("tcnIa")) + ",\n"
        "  relev: " + js(res["relev"]) + ",\n"
        "  anio: " + str(anio) + ",\n"
        "  fuente: " + js(res["fuente"]) + ",\n"
        '  updated: "' + datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + '"\n'
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        f.write(contenido)

    print("[OK] rem_cache.js  ->  relevamiento %s  |  prox. 12 meses: %s%%"
          "  |  dic-%s: %s%%  |  TCN dic: %s"
          % (res["relev"], res["m12"], str(anio)[2:], res["anual"],
             res.get("tcnDic") or "N/D"))


if __name__ == "__main__":
    main()
