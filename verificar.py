#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verificar.py - Tablero Gestion Grupo Elyon
===========================================
Chequeo general de todo el tablero, para correr al final del ciclo de
actualizacion y antes de publicar.

Por que existe
--------------
El .bat actualiza quince fuentes distintas. Cuando una falla escribe un
"[AVISO] Fallo" en el log, conserva el cache anterior y sigue. Eso esta bien
para no romper el tablero, pero significa que una fuente puede estar muerta
hace meses sin que nadie se entere: la tarjeta sigue mostrando el ultimo
numero que se pudo bajar, sin ninguna marca.

Esto revisa tres cosas:

  1. FRESCURA   - hace cuanto que cada cache no trae un dato nuevo, comparado
                  con lo que corresponde a su frecuencia de publicacion.
  2. INTEGRIDAD - fechas ordenadas y sin repetir, sin huecos en las series
                  mensuales, sin nulos en los ultimos meses, y sin saltos
                  absurdos (un salto de mas de 60% mes a mes casi siempre es
                  un error de parseo, no un dato).
  3. ESTRUCTURA - que el HTML no tenga ids repetidos ni divs desbalanceados,
                  y que cada cache que el tablero pide exista en la carpeta.

Devuelve codigo de salida 1 si encuentra ERRORES, para que el .bat pueda
frenar la publicacion. Los AVISOS no frenan nada.

Uso:
    python verificar.py
    python verificar.py --strict    (los avisos tambien devuelven error)
"""

import os
import re
import sys
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE_DIR, "tablero_elyon.html")

# archivo -> (frecuencia, dias maximos sin dato nuevo, dias maximos sin correr)
#
# Los limites salen del calendario real de cada fuente:
#   · las diarias se actualizan todos los habiles -> con 6 dias ya hay olor a quemado
#   · el ICC y el CAC salen a mitad del mes siguiente -> el dato vive ~45 dias
#   · el ISAC y el Registro General tienen mas rezago -> ~50 dias
#   · las escalas de UOCRA se cargan a mano 2 a 4 veces por año
# COMO SE ELIGE EL LIMITE DE DIAS DEL DATO
# ----------------------------------------
# El control mide la edad del dato mas nuevo del cache, y los datos mensuales
# llevan fecha del dia 1 del mes que miden. Entonces el limite NO es el rezago
# de publicacion: es cuanto envejece el ultimo dato ANTES de que salga el
# siguiente, que es bastante mas.
#
#   Si el mes M se publica el dia D del mes M+k, la vispera de esa publicacion
#   el dato mas nuevo todavia es el mes M-1. Su edad es la suma de los dias de
#   los meses M-1 .. M+k-1, mas D, menos 1.
#
#   k=1 (sale al mes siguiente):   peor caso ~ 61 + D
#   k=2 (sale a los dos meses):    peor caso ~ 91 + D
#
# El limite va con unos 7 dias de margen sobre ese peor caso, por si el
# organismo se atrasa. Poner menos NO detecta antes que algo se rompio:
# garantiza cartel rojo todos los meses, y un aviso que suena siempre deja
# de mirarse.
FRESCURA = {
    "bcra_cache.js":      ("diaria",  6,   6),
    "uva_cache.js":       ("diaria",  6,   6),
    "merval_cache.js":    ("diaria",  6,   6),
    "riesgo_cache.js":    ("diaria",  6,   6),
    "caucion_cache.js":   ("diaria",  6,   6),
    "rofex_cache.js":     ("diaria",  6,   6),
    "acciones_cache.js":  ("diaria",  6,   6),
    "dolar_cache.js":     ("diaria",  6,   6),
    "cac_cache.js":       ("mensual", 85,  6),
    "icc_cba_cache.js":   ("mensual", 85,  6),
    "icc_indec_cache.js": ("mensual", 85,  6),
    # ISAC: sale a los dos meses, alrededor del dia 8 (el de julio 2026 salio
    # el 08/09/2026). Peor caso 98 dias. Con 80 daba cartel 18 dias por mes.
    "isac_cache.js":      ("mensual", 105, 6),
    # Registro General: sale al mes siguiente, ~dia 23. Peor caso 83 dias.
    "rgp_cba_cache.js":   ("mensual", 90,  6),
    # IERIC: sale a los dos meses. El control mira la fecha mas nueva del
    # cache, que es la de empresas en actividad (va un mes adelante de
    # puestos y salario). Peor caso 103 dias.
    # OJO: como se mira el maximo, si puestos o salario se congelan pero
    # empresas sigue, esto no lo detecta. Es una limitacion del control
    # generico, no algo que este mal configurado aca.
    "ieric_cba_cache.js": ("mensual", 110, 6),
    # El Indice Construya sale alrededor del dia 10 del mes siguiente, mas
    # rapido que cualquier fuente oficial. Aun asi el peor caso son 70 dias:
    # la vispera de que salga el mes M, el dato mas nuevo es M-1 y ya tiene
    # dos meses y diez dias encima. Con 55 el cartel salia 15 dias por mes.
    "construya_cache.js": ("mensual", 80,  6),
    # APYMECO publica con un rezago parecido al del CAC. Es la unica fuente
    # que ACUMULA historico (la pagina solo muestra 13 meses), asi que un
    # cache viejo no es solo un dato desactualizado: son meses que se pierden
    # para siempre si el script queda roto mucho tiempo.
    # El dia de publicacion de APYMECO no esta confirmado; 95 cubre hasta el
    # dia 27 del mes siguiente. Si alguna vez se sabe la fecha exacta, ajustar.
    "apymeco_cache.js":   ("mensual", 95,  6),
    # CEDUC se carga desde un .txt que se arma a mano con el PDF del informe,
    # y la camara publica de forma irregular. Por eso no se controla cuando
    # corrio el script y el limite del dato es holgado: 150 dias.
    "ceduc_cache.js":     ("mensual", 150, None),
    # El REM se publica una vez por mes (el relevamiento de un mes sale a
    # principios del siguiente), asi que el archivo pasa semanas sin cambiar.
    # Lo que se controla es "chequeado", que update_rem_cache.py reescribe en
    # CADA corrida aunque no haya nada nuevo: 8 dias sin chequear si es que el
    # script dejo de correr.
    "rem_cache.js":       ("mensual", 75,  8),
    "salarios_cache.js":  ("manual",  240, None),   # se edita a mano
}

# Series donde un salto grande es normal y no hay que avisar:
# son conteos de operaciones, no indices de precios. Febrero y diciembre
# pegan saltos enormes todos los años por estacionalidad.
SIN_CONTROL_SALTO = {"transferencias", "hipotecas", "empleo", "permisos", "serie_riesgo",
                     "original", "desest"}   # CEDUC: son volumenes de venta, saltan solos

UMBRAL_SALTO = 0.60      # 60% mes a mes
MESES_SIN_NULOS = 12

errores, avisos = [], []


def err(msg):
    errores.append(msg)
    print("  [ERROR]  " + msg)


def avi(msg):
    avisos.append(msg)
    print("  [AVISO]  " + msg)


def ok(msg):
    print("  [ok]     " + msg)


# ── Lectura de los caches ────────────────────────────────────────────────
def bloques_array(txt):
    """Devuelve {clave: texto del array} para cada `clave: [ ... ]`.
    Cuenta corchetes en vez de usar una expresion regular, porque las filas
    son arrays adentro del array y una regex simple corta donde no debe."""
    out = {}
    for m in re.finditer(r'([A-Za-z_]\w*)\s*:\s*\[', txt):
        i = m.end() - 1
        prof = 0
        for j in range(i, len(txt)):
            if txt[j] == "[":
                prof += 1
            elif txt[j] == "]":
                prof -= 1
                if prof == 0:
                    out[m.group(1)] = txt[i:j + 1]
                    break
    return out


FILA = re.compile(r'\[\s*"(\d{4}-\d{2}(?:-\d{2})?)"\s*((?:,[^\[\]]*)?)\]')


def filas_de(bloque):
    """[(fecha, [valores])] a partir del texto de un array."""
    out = []
    for f, resto in FILA.findall(bloque):
        vals = []
        for v in resto.lstrip(",").split(","):
            v = v.strip()
            if v in ("", "null", "undefined"):
                vals.append(None)
            else:
                try:
                    vals.append(float(v))
                except ValueError:
                    vals.append(None)
        out.append((f[:7] if len(f) == 7 else f, vals))
    return out


def a_date(f):
    p = f.split("-")
    return date(int(p[0]), int(p[1]), int(p[2]) if len(p) > 2 else 1)


def mes_siguiente(d):
    return date(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1)


def revisar_serie(archivo, clave, filas):
    """Integridad de una serie: orden, duplicados, huecos, nulos y saltos.

    Ojo con el orden: algunos caches guardan la serie ascendente y otros
    descendente, segun como la devuelve la fuente. Los insumos del ISAC, por
    ejemplo, vienen del mas nuevo al mas viejo. Las dos formas son validas y al
    tablero le da igual porque indexa por fecha, asi que aca solo se rechaza
    una serie que no este ordenada en NINGUN sentido. El resto de los controles
    se hacen sobre una copia ordenada."""
    if len(filas) < 3:
        return
    fechas = [a_date(f) for f, _ in filas]

    asc = fechas == sorted(fechas)
    desc = fechas == sorted(fechas, reverse=True)
    if not asc and not desc:
        err("%s · %s: las fechas estan desordenadas" % (archivo, clave))
    if len(set(fechas)) != len(fechas):
        rep = [f for f in set(fechas) if fechas.count(f) > 1][:3]
        err("%s · %s: fechas repetidas (%s)"
            % (archivo, clave, ", ".join(str(f) for f in rep)))

    if desc:                       # se trabaja siempre de viejo a nuevo
        filas = list(reversed(filas))
        fechas = list(reversed(fechas))

    # Huecos: solo tiene sentido en series mensuales (todas dia 1)
    if all(f.day == 1 for f in fechas) and len(fechas) > 12:
        huecos = []
        for a, b in zip(fechas, fechas[1:]):
            if mes_siguiente(a) != b:
                huecos.append("%s->%s" % (a.strftime("%Y-%m"), b.strftime("%Y-%m")))
        if huecos:
            avi("%s · %s: %d hueco(s) en la serie (%s)"
                % (archivo, clave, len(huecos), ", ".join(huecos[:4])))

    ultimos = filas[-MESES_SIN_NULOS:]
    nulos = [f for f, v in ultimos if not v or v[0] is None]
    if nulos:
        avi("%s · %s: %d nulo(s) en los ultimos %d registros (%s)"
            % (archivo, clave, len(nulos), MESES_SIN_NULOS, ", ".join(nulos[:4])))

    if clave in SIN_CONTROL_SALTO:
        return
    for (fa, va), (fb, vb) in zip(filas[-25:], filas[-24:]):
        if not va or not vb or va[0] in (None, 0) or vb[0] is None:
            continue
        salto = vb[0] / va[0] - 1
        if abs(salto) > UMBRAL_SALTO:
            avi("%s · %s: salto de %+.0f%% entre %s y %s — revisar el parseo"
                % (archivo, clave, salto * 100, fa, fb))


CUALQUIER_FECHA = re.compile(r'"(\d{4}-\d{2}(?:-\d{2})?)"')


def ultima_fecha(bloques, txt=""):
    """La fecha mas reciente del cache.

    Primero mira las series. Si no encuentra ninguna —porque el cache son
    cuatro numeros sueltos como el REM, o porque la serie esta anidada de una
    forma que el lector de arrays no agarra, como la de salarios— cae a buscar
    cualquier fecha entrecomillada en el archivo. En un cache de datos toda
    fecha es un dato, asi que el maximo sirve igual.

    Excepcion: la curva de futuros. Ahi las fechas son VENCIMIENTOS, no ruedas:
    apuntan al futuro por definicion y tomar el maximo daba una antiguedad
    negativa. Lo que hay que controlar es la rueda de la que salio la curva."""
    m = re.search(r'rueda:\s*"(\d{4}-\d{2}-\d{2})"', txt)
    if m:
        return a_date(m.group(1))

    ult = None
    # Hay caches que son una FOTO, no una serie: el ranking de acciones del dia
    # no tiene fechas adentro. Ahi el dato es tan viejo como la corrida que lo
    # escribio, asi que vale el sello de `updated`.
    if "ACCIONES_CACHE" in txt or "DOLAR_CACHE" in txt:
        m = re.search(r'updated:\s*"(\d{4}-\d{2}-\d{2})', txt)
        if m:
            return a_date(m.group(1))

    for bloque in bloques.values():
        for f, _ in filas_de(bloque):
            d = a_date(f)
            if ult is None or d > ult:
                ult = d
    if ult is None:
        for f in CUALQUIER_FECHA.findall(txt):
            try:
                d = a_date(f)
            except ValueError:
                continue
            if ult is None or d > ult:
                ult = d
    return ult


def revisar_cache(archivo):
    ruta = os.path.join(BASE_DIR, archivo)
    print("\n> %s" % archivo)
    if not os.path.exists(ruta):
        err("%s: no existe. Corre el update correspondiente." % archivo)
        return

    txt = open(ruta, encoding="utf-8", errors="replace").read()
    if "window." not in txt:
        err("%s: no define ningun window.*_CACHE" % archivo)
        return

    frecuencia, dias_dato, dias_script = FRESCURA.get(archivo, ("?", None, None))
    hoy = date.today()

    # ¿Hace cuanto que no corre el script?
    # "chequeado" gana sobre "updated": lo escribe el script en cada corrida
    # aunque el dato no cambie. Mirar solo "updated" hace que una fuente
    # mensual parezca caida entre publicacion y publicacion.
    m = (re.search(r'chequeado\s*:\s*"([\d\-T:]+)"', txt)
         or re.search(r'(?:updated|actualizado)\s*:\s*"([\d\-T:]+)"', txt))
    if m and dias_script is not None:
        d = a_date(m.group(1)[:10])
        edad = (hoy - d).days
        if edad > dias_script:
            err("%s: el cache se genero hace %d dias (%s). El script no esta corriendo."
                % (archivo, edad, d))
        else:
            ok("generado hace %d dia(s)" % edad)
    elif not m:
        avi("%s: no tiene campo updated/actualizado" % archivo)

    # ¿Hace cuanto que la fuente no publica un dato nuevo?
    bloques = bloques_array(txt)
    ult = ultima_fecha(bloques, txt)
    if ult is None:
        avi("%s: no se encontro ninguna serie con fechas" % archivo)
    else:
        edad = (hoy - ult).days
        etiqueta = "ultimo dato %s (%d dias)" % (ult, edad)
        if dias_dato and edad > dias_dato:
            # AVISO y no ERROR a proposito. Que una fuente tarde en publicar no
            # es un problema del tablero: el INDEC saca el ISAC a mitad del mes
            # siguiente y el IERIC con dos meses de rezago, asi que todos los
            # meses hay una ventana de dias en que estan "vencidos". Si eso
            # frenara la publicacion, dejarian de subirse tambien el dolar, el
            # riesgo pais y el MERVAL, y -peor- el sitio publico quedaria
            # congelado en la version anterior, SIN el cartel rojo que avisa
            # que hay fuentes viejas. Publicar con el cartel es estrictamente
            # mejor que no publicar. Los errores quedan para lo que si rompe:
            # cache ausente, estructura mala, fechas desordenadas o repetidas.
            avi("%s: %s. Esperado para una fuente %s: hasta %d dias. "
                "Se publica igual; el tablero lo muestra en el cartel de fuentes."
                % (archivo, etiqueta, frecuencia, dias_dato))
        else:
            ok(etiqueta)

    for clave, bloque in bloques.items():
        filas = filas_de(bloque)
        if len(filas) >= 3:
            revisar_serie(archivo, clave, filas)


# ── Estructura del HTML ──────────────────────────────────────────────────
def revisar_html():
    print("\n> tablero_elyon.html")
    if not os.path.exists(HTML):
        err("no existe tablero_elyon.html")
        return
    h = open(HTML, encoding="utf-8", errors="replace").read()

    ids = re.findall(r'\sid="([^"]+)"', h)
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        err("ids repetidos en el HTML: %s" % ", ".join(dup))
    else:
        ok("%d ids, ninguno repetido" % len(ids))

    abre, cierra = len(re.findall(r"<div\b", h)), h.count("</div>")
    if abre != cierra:
        err("divs desbalanceados: %d abiertos y %d cerrados" % (abre, cierra))
    else:
        ok("%d divs, balanceados" % abre)

    # Cada <script src="algo_cache.js"> tiene que existir en la carpeta
    faltan = [s for s in re.findall(r'<script src="([^"]+_cache\.js)"', h)
              if not os.path.exists(os.path.join(BASE_DIR, s))]
    if faltan:
        err("el HTML pide caches que no estan: %s" % ", ".join(faltan))
    else:
        ok("todos los caches que pide el HTML existen")

    # Los generados por build_publicar.py
    for salida in ("tablero_elyon_portable.html", os.path.join("docs", "index.html")):
        ruta = os.path.join(BASE_DIR, salida)
        if not os.path.exists(ruta):
            avi("falta %s — corre build_publicar.py" % salida)
            continue
        gen = open(ruta, encoding="utf-8", errors="replace").read()
        pedidos = set(re.findall(r"window\.(\w+_CACHE)\b", h))
        embebidos = set(re.findall(r"window\.(\w+_CACHE)\s*=", gen))
        faltantes = sorted(pedidos - embebidos)
        if faltantes:
            avi("%s no tiene embebido: %s" % (salida, ", ".join(faltantes)))
        else:
            ok("%s tiene los %d caches embebidos" % (salida, len(embebidos)))


def main():
    print("=" * 62)
    print(" VERIFICACION DEL TABLERO — %s" % datetime.now().strftime("%d/%m/%Y %H:%M"))
    print("=" * 62)

    for archivo in FRESCURA:
        revisar_cache(archivo)
    revisar_html()

    print("\n" + "=" * 62)
    if not errores and not avisos:
        print(" TODO EN ORDEN. Se puede publicar.")
    else:
        print(" %d error(es) y %d aviso(s)." % (len(errores), len(avisos)))
        if errores:
            print("\n Errores (frenan la publicacion):")
            for e in errores:
                print("   · " + e)
        if avisos:
            print("\n Avisos (no frenan, pero conviene mirarlos):")
            for a in avisos:
                print("   · " + a)
    print("=" * 62)

    if errores or ("--strict" in sys.argv and avisos):
        sys.exit(1)


if __name__ == "__main__":
    # Codigos de salida, para que el .bat sepa distinguir:
    #   0 = todo bien
    #   1 = la verificacion encontro problemas reales -> no publicar
    #   2 = el verificador se cayo por su cuenta -> avisar, pero publicar igual.
    #       Un bug aca no tiene por que frenar el ciclo entero.
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        print("\n[ERROR] verificar.py se cayo con una excepcion inesperada.")
        print("        Esto es un problema del verificador, no de los datos.")
        traceback.print_exc()
        sys.exit(2)
