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
autorizada por permisos de edificacion. Esos dos cuadros los lee este mismo
script de los cuadros 3 y 4 del PDF del informe: alcanza con dejar el informe
en la carpeta isac/. De ahi regenera isac_manual.json y lo embebe.

Salida: isac_cache.js
    window.ISAC_CACHE = {
      updated, source, hasta,
      serie:    [[fecha, original, desestacionalizada], ...]   desde 2012-01
      insumos:  { clave: [[fecha, indice], ...], ... }          ultimos 30 meses
      delInforme: [meses que salen del informe y todavia no de la API]
      insumosDesest: [claves que salen de la serie sin estacionalidad]
      empleo:   { hasta, serie: [[fecha, puestos], ...] }
      permisos: { hasta, municipios, serie: [[fecha, m2, permisos], ...] }
    }

Uso:
    python update_isac_cache.py
"""

import json
import os
import re
import glob
import zlib
import ssl
import time
import urllib.request as req
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "isac_cache.js")
MANUAL_PATH = os.path.join(BASE_DIR, "isac_manual.json")

API = "https://apis.datos.gob.ar/series/api/series"
TIMEOUT = 40
INTENTOS = 3             # la API del SSPM se cuelga seguido; reintentar alcanza
ESPERA = 4               # segundos entre intentos (se va alargando)
MESES_INSUMOS = 30        # alcanza para interanual y acumulado del año

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# Nivel general: serie original y serie desestacionalizada
ID_NIVEL_ORIG = "33.2_ISAC_NIVELRAL_0_M_18_63"
ID_NIVEL_DESEST = "33.2_ISAC_SIN_EDAD_0_M_23_56"

# Insumos, serie original (distribucion 33.3). El orden es el del informe.
# Cada insumo: (clave, id de la serie ORIGINAL, id de la serie SIN ESTACIONALIDAD).
# El INDEC publica las dos, pero la distribucion "serie original" (33.3) devuelve
# la columna vacia para cemento, sanitarios, asfalto y resto: el catalogo los
# lista hasta el ultimo mes, pero la API no trae un solo valor. Para esos cuatro
# se usa la serie sin estacionalidad (33.4), que si viene completa, y el tablero
# lo aclara en la tarjeta.
INSUMOS = [
    ("cemento",    "33.3_ISAC_CEMENAND_0_0_21_29", "33.4_ISAC_CEMENAND_0_0_21_24"),
    ("hormigon",   "33.3_ISAC_HORMIADO_0_0_23_36", "33.4_ISAC_HORMIADO_0_0_23_66"),
    ("hierro",     "33.3_ISAC_HIERRION_0_0_49_36", "33.4_ISAC_HIERRION_0_0_49_34"),
    ("ladrillos",  "33.3_ISAC_LADRICOS_0_0_21_27", "33.4_ISAC_LADRICOS_0_0_21_3"),
    ("cales",      "33.3_ISAC_CALESLES_0_0_10_7",  "33.4_ISAC_CALESLES_0_0_10_20"),
    ("yeso",       "33.3_ISAC_YESOESO_0_0_9_54",   "33.4_ISAC_YESOESO_0_0_9_99"),
    ("placas",     "33.3_ISAC_PLACAESO_0_0_19_5",  None),
    ("pisos",      "33.3_ISAC_PISOSCOS_0_0_37_22", "33.4_ISAC_PISOSCOS_0_0_37_54"),
    ("mosaicos",   "33.3_ISAC_MOSAIEOS_0_0_36_91", "33.4_ISAC_MOSAIEOS_0_0_36_95"),
    ("sanitarios", "33.3_ISAC_ARTICICA_0_0_37_38", "33.4_ISAC_ARTICICA_0_0_37_66"),
    ("pinturas",   "33.3_ISAC_PINTUION_0_0_31_13", None),
    ("asfalto",    "33.3_ISAC_ASFALLTO_0_0_12_97", "33.4_ISAC_ASFALLTO_0_0_12_6"),
    ("resto",      "33.3_ISAC_RESTOSTO_0_0_10_50", "33.4_ISAC_RESTOSTO_0_0_10_0"),
]


_sin_verificar = [False]     # se prende si el handshake SSL falla una vez


def _get(url):
    """Lo mismo que _get_bytes, decodificado como texto."""
    return _get_bytes(url).decode("utf-8", "replace")


def _get_bytes(url):
    """GET con reintentos.

    Dos cosas distintas pueden fallar. El handshake SSL, en PC con el store de
    certificados desactualizado: eso no se arregla reintentando, asi que a
    partir del primer fallo se sigue sin verificar. Y la lectura, porque
    apis.datos.gob.ar a veces tarda mas que el timeout y corta: ahi no hay nada
    roto, solo hay que volver a pedir. Un intento como mucho tarda TIMEOUT, y
    son INTENTOS intentos, para no colgar la corrida entera."""
    r = req.Request(url, headers={"User-Agent": UA, "Accept": "text/csv,text/html,*/*"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    ultimo = None
    for intento in range(INTENTOS):
        try:
            with req.urlopen(r, timeout=TIMEOUT,
                             context=ctx if _sin_verificar[0] else None) as resp:
                return resp.read()
        except ssl.SSLError as e:
            ultimo = e
            _sin_verificar[0] = True       # el proximo intento va sin verificar
            continue                       # sin esperar: es otro problema
        except Exception as e:
            ultimo = e
        if intento < INTENTOS - 1:
            time.sleep(ESPERA * (intento + 1))
    raise ultimo


def bajar_csv(ids, limit, sort="asc"):
    """Devuelve [[fecha, v1, v2, ...], ...] para una lista de ids.
    La API corta las URLs largas, asi que se pide de a pocos ids."""
    url = "%s/?ids=%s&limit=%d&sort=%s&format=csv" % (API, ",".join(ids), limit, sort)
    try:
        txt = _get(url).strip()
    except Exception as e:
        # Un problema de red no justifica volcar un traceback de 60 lineas en
        # el log de la corrida: se avisa en una linea y el que llama decide.
        print("   [AVISO] la API no contesto (%s): %s"
              % (", ".join(ids)[:60], str(e).strip() or type(e).__name__))
        return []
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


# ═══════════════════════════════════════════════════════════════════
#  CUADROS 3 Y 4 DEL INFORME, DESDE EL PDF
#  ═══════════════════════════════════════════════════════════════
#  Los puestos de trabajo registrados y la superficie autorizada por
#  permisos de edificacion NO estan en la API de datos.gob.ar: solo salen en
#  el informe de prensa. Hasta octubre de 2026 se copiaban a mano en
#  isac_manual.json, y por eso el archivo se quedo cuatro meses atras.
#
#  El PDF del INDEC tiene capa de texto, asi que se lee con zlib y
#  expresiones regulares, sin librerias de terceros. El circuito queda igual
#  de simple que el de CEDUC: se deja el PDF en la carpeta isac y listo.
#
#  Los nombres de los meses vienen partidos por el kerning del PDF
#  ("F ebrero"), por eso cada mes se busca con un patron que tolera espacios
#  entre letras.
# ═══════════════════════════════════════════════════════════════════
CARPETA_INFORMES = os.path.join(BASE_DIR, "isac")

# De donde sale el enlace al informe. Las paginas de seccion del INDEC arman
# el listado por JavaScript, asi que bajadas en crudo vienen vacias; la home
# tambien. El unico que sirve es /indec/Portada, que es el fragmento que la
# home carga por detras y trae el enlace al informe de prensa mas reciente de
# cada tema ya escrito en el HTML.
INDEC_BASE = "https://www.indec.gob.ar"
INDEC_PORTADA = INDEC_BASE + "/indec/Portada"
RE_LINK_ISAC = re.compile(r"/uploads/informesdeprensa/(isac_[0-9A-Za-z_]+\.pdf)")
# El nombre del informe lleva el mes de publicacion: isac_11_26XXXXXXXX.pdf
RE_MES_ARCHIVO = re.compile(r"^isac_(\d{2})_(\d{2})")

# Numeros del cuadro 1: decimales con coma, con o sin signo. No matchea la
# prosa del informe, donde el kerning del PDF separa las cifras ("4 , 4 %").
RE_DEC_INFORME = re.compile(r"[-\u2212]?\d{1,3},\d")

COMENTARIO_MANUAL = [
    "Datos del informe mensual del INDEC 'Indicadores de coyuntura de la actividad de la construccion'",
    "que NO estan publicados en la API de apis.datos.gob.ar: puestos de trabajo registrados y",
    "superficie autorizada por permisos de edificacion.",
    "NO se edita a mano: update_isac_cache.py lee los cuadros 3 y 4 del ultimo PDF que haya en la",
    "carpeta isac/ y regenera este archivo solo. Para cargar un mes nuevo basta dejar ahi el informe",
    "del INDEC (https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-9-45) y correr el tablero.",
    "Si el PDF no se puede leer, el script avisa y deja este archivo como estaba.",
    "Formato empleo:   [fecha, puestos de trabajo]",
    "Formato permisos: [fecha, superficie autorizada m2, cantidad de permisos]",
]

MESES_INFORME = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
                 "Diciembre"]
RE_NUM_INFORME = re.compile(r"\d{1,3}(?:\.\d{3})+")
RE_ANIO_INFORME = re.compile(r"\b(20\d\d)\s*\*?")
RE_MES_INFORME = re.compile("|".join(
    "(?P<m%d>%s)" % (i, r"\s*".join(re.escape(c) for c in m))
    for i, m in enumerate(MESES_INFORME)))


def _streams_pdf(datos):
    salida = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", datos, re.S):
        try:
            crudo = zlib.decompress(m.group(1))
        except Exception:
            continue
        trozos = []
        for s in re.finditer(rb"\((?:\\.|[^\\()])*\)", crudo, re.S):
            t = s.group(0)[1:-1]
            t = re.sub(rb"\\([()\\])", rb"\1", t)
            t = re.sub(rb"\\([0-7]{1,3})",
                       lambda g: bytes([int(g.group(1), 8) & 0xFF]), t)
            trozos.append(t)
        if trozos:
            salida.append(re.sub(r"\s+", " ",
                                 b" ".join(trozos).decode("latin-1", "replace")))
    return salida


def _filas_informe(texto, columnas):
    filas, anio, pos = [], None, 0
    while True:
        mm = RE_MES_INFORME.search(texto, pos)
        if not mm:
            break
        previo = RE_ANIO_INFORME.findall(texto[max(0, pos - 40):mm.start()])
        if previo:
            anio = int(previo[-1])
        idx = next(k for k in range(12) if mm.group("m%d" % k))
        nums = RE_NUM_INFORME.findall(texto[mm.end():mm.end() + 120])
        if anio and nums:
            fila = ["%04d-%02d-01" % (anio, idx + 1),
                    int(nums[0].replace(".", ""))]
            if columnas == 2:
                fila.append(int(nums[1].replace(".", "")) if len(nums) > 1 else None)
            filas.append(fila)
        pos = mm.end()
    vistos, unicas = set(), []
    for f in filas:
        if f[0] not in vistos:
            vistos.add(f[0])
            unicas.append(f)
    return sorted(unicas)


def _ultimo_informe_pdf():
    if not os.path.isdir(CARPETA_INFORMES):
        return None
    utiles = []
    for ruta in glob.glob(os.path.join(CARPETA_INFORMES, "*.pdf")):
        nombre = os.path.basename(ruta).lower()
        if nombre.startswith("~$") or "conflicto" in nombre:
            continue
        if os.path.getsize(ruta) < 10000:
            continue
        utiles.append(ruta)
    return max(utiles, key=os.path.getmtime) if utiles else None


def _contiguos(filas):
    """True si la serie no tiene huecos mensuales."""
    for a, b in zip(filas, filas[1:]):
        ya, ma = int(a[0][:4]), int(a[0][5:7])
        esperado = "%04d-%02d-01" % (ya + (ma == 12), ma % 12 + 1)
        if b[0] != esperado:
            return False
    return True


def _avisar_revisiones(antes, ahora, etiqueta):
    """El INDEC revisa los datos provisorios: conviene enterarse."""
    if not antes:
        return
    viejos = {f[0]: f[1:] for f in antes}
    cambios = []
    for f in ahora:
        v = viejos.get(f[0])
        if v and list(v) != list(f[1:]):
            cambios.append("       %s %s -> %s" % (f[0][:7], list(v), list(f[1:])))
    if cambios:
        print("   [REVISION] %s: el INDEC cambio %d mes(es) ya cargado(s):"
              % (etiqueta, len(cambios)))
        for c in cambios[:6]:
            print(c)
        if len(cambios) > 6:
            print("       ...y %d mas." % (len(cambios) - 6))


def bajar_informe_indec():
    """Trae el ultimo informe de prensa del ISAC, si todavia no lo tenemos.

    Antes el informe se dejaba a mano en la carpeta isac y por eso el tablero
    se quedaba atras: el INDEC publica el informe varios dias antes de que la
    serie aparezca en la API del SSPM, y nadie se enteraba. El enlace sale de
    la portada del INDEC, que es la unica pagina que lo sirve en el HTML.

    Si algo falla NO es grave: se sigue con el PDF que ya hubiera en la
    carpeta. Devuelve la ruta del informe mas nuevo, o None."""
    # La portada pesa un par de megas y el INDEC publica una vez por mes: si
    # ya tenemos el informe de este mes no hay nada que buscar.
    hoy = datetime.now()
    if _tengo_informe_de(hoy.month, hoy.year % 100):
        return _ultimo_informe_pdf()

    try:
        html = _get(INDEC_PORTADA)
    except Exception as e:
        print("   [AVISO] no se pudo leer la portada del INDEC: %s" % e)
        return None

    nombres = RE_LINK_ISAC.findall(html)
    if not nombres:
        print("   [AVISO] la portada del INDEC no traia enlace al informe del ISAC.")
        return None

    nombre = nombres[0]
    destino = os.path.join(CARPETA_INFORMES, nombre)
    if os.path.exists(destino) and os.path.getsize(destino) > 10000:
        return destino

    try:
        os.makedirs(CARPETA_INFORMES, exist_ok=True)
        datos = _get_bytes(INDEC_BASE + "/uploads/informesdeprensa/" + nombre)
    except Exception as e:
        print("   [AVISO] no se pudo bajar %s: %s" % (nombre, e))
        return None

    if not datos.startswith(b"%PDF") or len(datos) < 10000:
        print("   [AVISO] lo que bajo de %s no es un PDF." % nombre)
        return None

    tmp = destino + ".tmp"
    with open(tmp, "wb") as f:
        f.write(datos)
    os.replace(tmp, destino)
    print("   Informe nuevo del INDEC: %s (%d KB)" % (nombre, len(datos) // 1024))
    return destino


def _tengo_informe_de(mes, anio2):
    """True si en la carpeta ya hay un informe publicado en ese mes."""
    if not os.path.isdir(CARPETA_INFORMES):
        return False
    for ruta in glob.glob(os.path.join(CARPETA_INFORMES, "*.pdf")):
        m = RE_MES_ARCHIVO.match(os.path.basename(ruta).lower())
        if m and int(m.group(1)) == mes and int(m.group(2)) == anio2:
            return True
    return False


def _filas_cuadro1(texto):
    """[[fecha, nivel original, desestacionalizada], ...] del cuadro 1.

    La fila trae siete numeros: nivel original, su variacion interanual, la
    acumulada del año, el nivel desestacionalizado, su variacion mensual, el
    nivel tendencia-ciclo y su variacion. Nos quedamos con el primero y el
    cuarto, que son los dos niveles que guarda el cache."""
    filas, anio, pos = [], None, 0
    dec = lambda s: float(s.replace("\u2212", "-").replace(",", "."))
    while True:
        mm = RE_MES_INFORME.search(texto, pos)
        if not mm:
            break
        previo = RE_ANIO_INFORME.findall(texto[max(0, pos - 40):mm.start()])
        if previo:
            anio = int(previo[-1])
        idx = next(k for k in range(12) if mm.group("m%d" % k))
        nums = RE_DEC_INFORME.findall(texto[mm.end():mm.end() + 90])
        if anio and len(nums) >= 4:
            filas.append(["%04d-%02d-01" % (anio, idx + 1), dec(nums[0]), dec(nums[3])])
        pos = mm.end()
    vistos, unicas = set(), []
    for f in filas:
        if f[0] not in vistos:
            vistos.add(f[0])
            unicas.append(f)
    return sorted(unicas)


def nivel_desde_informe(ruta):
    """Cuadro 1 del informe, o [] si no se pudo leer."""
    if not ruta:
        return []
    try:
        datos = open(ruta, "rb").read()
    except Exception:
        return []
    for s in _streams_pdf(datos):
        if "Enero" not in s or len(RE_DEC_INFORME.findall(s)) < 60:
            continue
        filas = _filas_cuadro1(s)
        if len(filas) >= 12 and _contiguos(filas):
            return filas
    return []


def completar_con_informe(serie, ruta):
    """Suma al final de la serie de la API los meses que solo estan en el PDF.

    El INDEC publica el informe de prensa y recien varios dias despues carga
    la serie en la API del SSPM. En esa ventana el tablero mostraba el mes
    anterior aunque el dato nuevo ya fuera publico, que es exactamente lo que
    uno va a buscar. Ahora se completa con el informe.

    Dos resguardos antes de pegar nada: los meses que estan en los dos lados
    tienen que coincidir (el informe redondea a un decimal, asi que se compara
    con esa tolerancia) y el mes nuevo tiene que ser el siguiente al ultimo de
    la API, sin huecos. Si algo no cierra, se deja la serie de la API sola.

    Devuelve (serie, [meses que salieron del informe])."""
    filas = nivel_desde_informe(ruta)
    if not filas or not serie:
        return serie, []

    ultimo = serie[-1][0]
    nuevas = [f for f in filas if f[0] > ultimo]
    if not nuevas:
        return serie, []

    api = {f[0]: f for f in serie}
    comunes = [f for f in filas if f[0] in api]
    if len(comunes) < 6:
        print("   [AVISO] el cuadro 1 comparte solo %d mes(es) con la API: "
              "no se completa." % len(comunes))
        return serie, []

    peor = 0.0
    for f in comunes:
        a = api[f[0]]
        for i in (1, 2):
            if a[i] is not None:
                peor = max(peor, abs(round(a[i], 1) - f[i]))
    if peor > 0.06:
        print("   [AVISO] el cuadro 1 no coincide con la API (hasta %.2f de "
              "diferencia): no se completa." % peor)
        return serie, []

    esperado = _siguiente_mes(ultimo)
    if nuevas[0][0] != esperado:
        print("   [AVISO] el informe salta de %s a %s: no se completa."
              % (ultimo[:7], nuevas[0][0][:7]))
        return serie, []

    print("   Del informe   : %s (la API del SSPM todavia va hasta %s)"
          % (", ".join(f[0][:7] for f in nuevas), ultimo[:7]))
    return serie + nuevas, [f[0][:7] for f in nuevas]


def _siguiente_mes(fecha):
    a, m = int(fecha[:4]), int(fecha[5:7])
    return "%04d-%02d-01" % (a + (m == 12), m % 12 + 1)


def actualizar_manual_desde_pdf():
    """Regenera isac_manual.json con los cuadros 3 y 4 del informe.

    Si algo no cierra NO toca el archivo: se sigue con lo que ya habia."""
    ruta = _ultimo_informe_pdf()
    if not ruta:
        return
    print("   Informe del INDEC: %s" % os.path.basename(ruta))

    try:
        datos = open(ruta, "rb").read()
    except Exception as e:
        print("   [AVISO] no se pudo abrir el informe: %s" % e)
        return
    if not datos.startswith(b"%PDF"):
        print("   [AVISO] el archivo no es un PDF.")
        return

    empleo, permisos = [], []
    for s in _streams_pdf(datos):
        if len(RE_NUM_INFORME.findall(s)) < 12 or "Enero" not in s:
            continue
        if "Cuentas Nacionales" in s and not empleo:
            empleo = _filas_informe(s, 1)
        elif ("Mineras" in s or "Construcci" in s) and not permisos:
            filas = _filas_informe(s, 2)
            if filas and filas[-1][1] > 500000:
                permisos = filas

    if len(empleo) < 12 or len(permisos) < 12:
        print("   [AVISO] no se reconocieron los cuadros 3 y 4 "
              "(empleo %d, permisos %d). Se usa isac_manual.json como estaba."
              % (len(empleo), len(permisos)))
        return
    if not _contiguos(empleo) or not _contiguos(permisos):
        print("   [AVISO] las series del informe tienen huecos. No se toca nada.")
        return

    previo = {}
    if os.path.exists(MANUAL_PATH):
        try:
            with open(MANUAL_PATH, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = {}

    _avisar_revisiones(previo.get("empleo", {}).get("serie"), empleo, "empleo")
    _avisar_revisiones(previo.get("permisos", {}).get("serie"), permisos, "permisos")

    salida = dict(previo)
    salida["_comentario"] = COMENTARIO_MANUAL
    salida["fuente"] = ("INDEC, Indicadores de coyuntura de la actividad de la "
                        "construccion (cuadros 3 y 4), leido de " + os.path.basename(ruta))
    salida["informe"] = os.path.basename(ruta)
    salida["empleo"] = {"hasta": empleo[-1][0][:7], "serie": empleo}
    salida["permisos"] = {"hasta": permisos[-1][0][:7],
                          "municipios": previo.get("permisos", {}).get("municipios", 246),
                          "serie": permisos}

    tmp = MANUAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANUAL_PATH)
    print("   isac_manual.json regenerado: empleo hasta %s, permisos hasta %s."
          % (empleo[-1][0][:7], permisos[-1][0][:7]))


def main():
    print("Actualizando ISAC desde apis.datos.gob.ar (INDEC / SSPM)...")

    # 0) El informe del INDEC. Se baja solo y se lee antes de pegarle a la
    #    API: trae empleo y permisos (que la API no publica) y el nivel
    #    general del mes nuevo, que la API carga varios dias despues.
    ruta_informe = bajar_informe_indec() or _ultimo_informe_pdf()
    actualizar_manual_desde_pdf()

    # 1) Nivel general: original + desestacionalizada, serie completa
    serie = bajar_csv([ID_NIVEL_ORIG, ID_NIVEL_DESEST], 1000, "asc")
    if not serie:
        raise SystemExit(
            "[AVISO] apis.datos.gob.ar no contesto el nivel general en %d intentos. "
            "No se toca isac_cache.js: queda el de la corrida anterior y en la "
            "proxima se vuelve a intentar. (Empleo y permisos, que salen del PDF, "
            "ya quedaron actualizados.)" % INTENTOS)
    print("   Nivel general : %d meses, hasta %s (API)" % (len(serie), serie[-1][0][:7]))
    serie, del_informe = completar_con_informe(serie, ruta_informe)
    hasta = serie[-1][0][:7]

    # 2) Insumos, de a 3 ids por request (URLs mas largas fallan).
    #    Primero la serie original; lo que venga vacio se reintenta con la
    #    serie sin estacionalidad y queda marcado.
    insumos = {}
    desest = []

    def pedir(pares):
        """pares: [(clave, id)]. Devuelve {clave: [[fecha, valor], ...]} con
        datos de verdad (descarta las columnas que vienen todas vacias)."""
        salida = {}
        for i in range(0, len(pares), 3):
            grupo = pares[i:i + 3]
            filas = bajar_csv([sid for _, sid in grupo], MESES_INSUMOS, "desc")
            if not filas:
                print("   [AVISO] sin datos para: %s" % ", ".join(k for k, _ in grupo))
                continue
            for j, (clave, _) in enumerate(grupo):
                col = [[f[0], f[j + 1]] for f in filas if len(f) > j + 1]
                if any(v is not None for _, v in col):
                    salida[clave] = sorted(col)      # del mes mas viejo al mas nuevo
        return salida

    insumos.update(pedir([(k, orig) for k, orig, _ in INSUMOS]))

    faltan = [(k, sinest) for k, _, sinest in INSUMOS
              if k not in insumos and sinest]
    if faltan:
        print("   Sin serie original: %s. Se reintenta sin estacionalidad."
              % ", ".join(k for k, _ in faltan))
        rescatados = pedir(faltan)
        insumos.update(rescatados)
        desest = sorted(rescatados)

    vacios = [k for k, _, _ in INSUMOS if k not in insumos]
    print("   Insumos       : %d de %d%s" % (len(insumos), len(INSUMOS),
          (" (sin datos: " + ", ".join(vacios) + ")") if vacios else ""))
    if desest:
        print("   [AVISO] sin estacionalidad (la original viene vacia): %s"
              % ", ".join(desest))

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
    for clave, _, _ in INSUMOS:
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
        "   (Empleo y permisos salen del PDF que haya en la carpeta isac)\n"
        "═══════════════════════════ */\n"
        "window.ISAC_CACHE = {\n"
        '  updated: "' + datetime.now().isoformat(timespec="seconds") + '",\n'
        '  source: "' + fuente + '",\n'
        '  hasta: "' + hasta + '",\n'
        "  delInforme: " + json.dumps(del_informe) + ",\n"
        "  serie: [\n" + filas_serie + "\n  ],\n"
        "  insumos: {\n" + ",\n".join(bloques) + "\n  },\n"
        "  insumosDesest: " + json.dumps(desest) + ",\n"
        "  empleo: " + json.dumps(manual.get("empleo", {}), ensure_ascii=False) + ",\n"
        "  permisos: " + json.dumps(manual.get("permisos", {}), ensure_ascii=False) + ",\n"
        '  informe: ' + json.dumps(manual.get("informe", ""), ensure_ascii=False) + "\n"
        "};\n"
    )

    with open(CACHE_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(js)

    ult = serie[-1]
    print("\n[OK] isac_cache.js")
    print("     ISAC %s = %.1f (original) / %.1f (desest.)"
          % (hasta, ult[1] or 0, ult[2] or 0))


if __name__ == "__main__":
    main()
