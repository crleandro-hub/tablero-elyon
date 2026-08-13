#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_publicar.py - Tablero Gestion Grupo Elyon
================================================
Genera una version AUTOCONTENIDA del tablero: un unico archivo .html con los
datos de bcra_cache.js y cac_cache.js embebidos adentro.

Por que hace falta:
    tablero_elyon.html carga los datos con <script src="bcra_cache.js"> y
    <script src="cac_cache.js">. Esos archivos viven en esta carpeta, asi que
    si copias SOLO el html a otra PC el tablero no los encuentra y cae a los
    datos embebidos viejos. La version autocontenida no depende de nada local.

Genera dos salidas:
    1. docs/index.html            -> carpeta lista para publicar en GitHub Pages
    2. tablero_elyon_portable.html -> archivo suelto para mandar por mail/WhatsApp

Ejecutar DESPUES de actualizar los caches:
    python update_cac_cache.py
    python build_publicar.py
"""

import os
import re
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SRC_HTML = os.path.join(BASE_DIR, "tablero_elyon.html")
BCRA_JS = os.path.join(BASE_DIR, "bcra_cache.js")
CAC_JS = os.path.join(BASE_DIR, "cac_cache.js")
UVA_JS = os.path.join(BASE_DIR, "uva_cache.js")
MERVAL_JS = os.path.join(BASE_DIR, "merval_cache.js")
REM_JS = os.path.join(BASE_DIR, "rem_cache.js")
SAL_JS = os.path.join(BASE_DIR, "salarios_cache.js")
RIESGO_JS = os.path.join(BASE_DIR, "riesgo_cache.js")
CAUCION_JS = os.path.join(BASE_DIR, "caucion_cache.js")
ROFEX_JS = os.path.join(BASE_DIR, "rofex_cache.js")
ACCIONES_JS = os.path.join(BASE_DIR, "acciones_cache.js")
DOLAR_JS = os.path.join(BASE_DIR, "dolar_cache.js")
ISAC_JS = os.path.join(BASE_DIR, "isac_cache.js")
CONSTRUYA_JS = os.path.join(BASE_DIR, "construya_cache.js")
ICC_CBA_JS = os.path.join(BASE_DIR, "icc_cba_cache.js")
RGP_CBA_JS = os.path.join(BASE_DIR, "rgp_cba_cache.js")
ICC_INDEC_JS = os.path.join(BASE_DIR, "icc_indec_cache.js")
CEDUC_JS = os.path.join(BASE_DIR, "ceduc_cache.js")
APYMECO_JS = os.path.join(BASE_DIR, "apymeco_cache.js")

DOCS_DIR = os.path.join(BASE_DIR, "docs")
OUT_PAGES = os.path.join(DOCS_DIR, "index.html")
OUT_PORTABLE = os.path.join(BASE_DIR, "tablero_elyon_portable.html")


def leer(path, obligatorio=True):
    if not os.path.exists(path):
        if obligatorio:
            raise SystemExit("[ERROR] No se encontro: " + path)
        print("[AVISO] No se encontro " + os.path.basename(path) + " - se omite.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def inline(html, tag_src, contenido, etiqueta):
    """Reemplaza <script src="archivo.js"></script> por el contenido inline."""
    patron = re.compile(
        r'<script\s+src="' + re.escape(tag_src) + r'"\s*></script>[^\n]*'
    )
    if not patron.search(html):
        print("[AVISO] No se encontro la etiqueta de " + tag_src + " en el HTML.")
        return html
    if contenido is None:
        # Sin el archivo de datos, dejar el <script src> apuntando a un archivo
        # que no se publica daria un 404 en GitHub Pages. Se saca la etiqueta:
        # el tablero ya tiene el camino alternativo de consultar la API.
        return patron.sub("<!-- " + tag_src + " no disponible al generar -->", html, count=1)
    bloque = (
        "<script>\n/* === " + etiqueta + " embebido desde " + tag_src
        + " (build_publicar.py) === */\n" + contenido.strip() + "\n</script>"
    )
    # El contenido puede tener secuencias que rompan el parseo del script.
    bloque = bloque.replace("</script>", "<\\/script>", bloque.count("</script>") - 1)
    return patron.sub(lambda _: bloque, html, count=1)


def ultimo_construya(txt):
    """Ultimo mes e indice del Indice Construya, para el resumen del log."""
    if not txt:
        return "sin datos"
    filas = re.findall(r'\["(\d{4})-(\d{2})-\d{2}",\s*([-\d.]+)', txt)
    if not filas:
        return "sin datos"
    a, m, v = filas[-1]
    return v + " (" + m + "/" + a + ")"


def main():
    print("Generando version autocontenida del tablero...")

    html = leer(SRC_HTML)
    bcra = leer(BCRA_JS, obligatorio=False)
    cac = leer(CAC_JS, obligatorio=False)
    uva = leer(UVA_JS, obligatorio=False)
    merval = leer(MERVAL_JS, obligatorio=False)
    rem = leer(REM_JS, obligatorio=False)
    sal = leer(SAL_JS, obligatorio=False)
    riesgo = leer(RIESGO_JS, obligatorio=False)
    caucion = leer(CAUCION_JS, obligatorio=False)
    rofex = leer(ROFEX_JS, obligatorio=False)
    acciones = leer(ACCIONES_JS, obligatorio=False)
    dolar = leer(DOLAR_JS, obligatorio=False)
    isac = leer(ISAC_JS, obligatorio=False)
    construya = leer(CONSTRUYA_JS, obligatorio=False)
    icc_cba = leer(ICC_CBA_JS, obligatorio=False)
    rgp_cba = leer(RGP_CBA_JS, obligatorio=False)
    icc_indec = leer(ICC_INDEC_JS, obligatorio=False)
    ceduc = leer(CEDUC_JS, obligatorio=False)
    apymeco = leer(APYMECO_JS, obligatorio=False)

    html = inline(html, "bcra_cache.js", bcra, "BCRA_CACHE")
    html = inline(html, "cac_cache.js", cac, "CAC_CACHE")
    html = inline(html, "uva_cache.js", uva, "UVA_CACHE")
    html = inline(html, "merval_cache.js", merval, "MERVAL_CACHE")
    html = inline(html, "rem_cache.js", rem, "REM_CACHE")
    html = inline(html, "salarios_cache.js", sal, "SALARIOS_CACHE")
    html = inline(html, "riesgo_cache.js", riesgo, "RIESGO_CACHE")
    html = inline(html, "caucion_cache.js", caucion, "CAUCION_CACHE")
    html = inline(html, "rofex_cache.js", rofex, "ROFEX_CACHE")
    html = inline(html, "acciones_cache.js", acciones, "ACCIONES_CACHE")
    html = inline(html, "dolar_cache.js", dolar, "DOLAR_CACHE")
    html = inline(html, "isac_cache.js", isac, "ISAC_CACHE")
    html = inline(html, "construya_cache.js", construya, "CONSTRUYA_CACHE")
    html = inline(html, "icc_cba_cache.js", icc_cba, "ICC_CBA_CACHE")
    html = inline(html, "rgp_cba_cache.js", rgp_cba, "RGP_CBA_CACHE")
    html = inline(html, "icc_indec_cache.js", icc_indec, "ICC_INDEC_CACHE")
    html = inline(html, "ceduc_cache.js", ceduc, "CEDUC_CACHE")
    html = inline(html, "apymeco_cache.js", apymeco, "APYMECO_CACHE")

    ts = datetime.now().strftime("%d/%m/%Y %H:%M")
    sello = (
        "<!-- Version autocontenida generada por build_publicar.py el " + ts
        + " - datos embebidos, no depende de archivos externos -->\n"
    )
    html = sello + html

    os.makedirs(DOCS_DIR, exist_ok=True)
    for destino in (OUT_PAGES, OUT_PORTABLE):
        with open(destino, "w", encoding="utf-8") as f:
            f.write(html)

    # .nojekyll evita que GitHub Pages ignore archivos que empiezan con guion bajo
    open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()

    # Copia del Excel fuente NO se publica: solo el html hace falta.
    tam = os.path.getsize(OUT_PAGES) / 1024

    # Resumen de que quedo embebido
    def ultimo_cac(txt):
        if not txt:
            return "sin datos"
        fechas = re.findall(r'\["(\d{4})-(\d{2})-\d{2}"', txt)
        return fechas[-1][1] + "/" + fechas[-1][0] if fechas else "sin datos"

    def val_bcra(txt, clave):
        if not txt:
            return "sin datos"
        m = re.search(clave + r":\s*\{\s*valor:\s*([\d.]+),\s*fecha:\s*\"(\d{4})-(\d{2})-(\d{2})\"", txt)
        if not m:
            return "sin datos"
        return m.group(1) + " (" + m.group(4) + "/" + m.group(3) + "/" + m.group(2) + ")"

    print("[OK] docs/index.html               (" + ("%.0f" % tam) + " KB)")
    print("[OK] tablero_elyon_portable.html   (mismo contenido, para mandar suelto)")
    print("")
    print("     Datos embebidos:")
    print("       TAMAR : " + val_bcra(bcra, "tamar"))
    print("       BADLAR: " + val_bcra(bcra, "badlar"))
    print("       UVA   : " + val_bcra(bcra, "uva"))
    def val_reservas(txt):
        if not txt:
            return "sin datos"
        import re as _re
        m = _re.search(r'reservas:\s*\{\s*valor:\s*(\d+)', txt)
        return "US$ " + m.group(1) + " M" if m else "sin datos"

    print("       RESERV: " + val_reservas(bcra))
    print("       CAC   : ultimo mes " + ultimo_cac(cac))
    print("       CONSTR: " + ultimo_construya(construya))

    def ultimo_apymeco(txt):
        """Ultimo mes y precio del m2 de APYMECO, para el resumen del log."""
        if not txt:
            return "sin datos"
        filas = re.findall(r'\["(\d{4})-(\d{2})-\d{2}",\s*([\d.]+)', txt)
        if not filas:
            return "sin datos"
        a, m, v = filas[-1]
        return "$ " + ("%s" % round(float(v))) + "/m2 (" + m + "/" + a + ")"

    print("       APYMECO: " + ultimo_apymeco(apymeco))

    def val_simple(txt, clave, sufijo=""):
        if not txt:
            return "sin datos"
        m = re.search(clave + r":\s*([-\d.]+|null)", txt)
        if not m or m.group(1) == "null":
            return "sin datos"
        return m.group(1) + sufijo

    print("       MERVAL: " + val_simple(merval, "ars", " pts")
          + " / USD " + val_simple(merval, "usd"))
    def val_caucion(txt):
        if not txt:
            return "sin datos"
        import re as _re
        partes = []
        for clave, etiqueta in (("d1", "1d"), ("d7", "7d"), ("d14", "14d")):
            m = _re.search(clave + r":\s*\{.*?valor:\s*([-\d.]+)", txt, _re.S)
            partes.append(etiqueta + " " + (m.group(1) + "%" if m else "N/D"))
        return " / ".join(partes)

    print("       CAUCION: " + val_caucion(caucion))
    def val_rofex(txt):
        if not txt:
            return "sin datos"
        import re as _re
        ms = _re.findall(r'etiqueta:\s*"([^"]+)",\s*precio:\s*([\d.]+)', txt)
        return " / ".join(e + " " + v for e, v in ms[:3]) if ms else "sin datos"

    print("       ROFEX : " + val_rofex(rofex))

    def val_acciones(txt):
        if not txt:
            return "sin datos"
        import re as _re
        def top(clave):
            m = _re.search(clave + r":\s*\[(.*?)\]", txt, _re.S)
            if not m:
                return "-"
            ms = _re.findall(r'symbol:\s*"([^"]+)".*?pct:\s*(-?[\d.]+)', m.group(1))
            return " ".join("%s %s%%" % (s, p) for s, p in ms)
        return "suben " + top("mejores") + " | bajan " + top("peores")

    print("       ACCION: " + val_acciones(acciones))
    print("       DEVAL : TCN dic " + val_simple(rem, "tcnDic", " $/US$")
          + " / " + val_simple(rem, "tcnIa", "% i.a."))
    print("       REM   : " + val_simple(rem, "anual", "% i.a. dic")
          + " (relevamiento " + (re.search(r'relev:\s*"([^"]+)"', rem or "").group(1)
                                 if rem and re.search(r'relev:\s*"([^"]+)"', rem)
                                 else "sin datos") + ")")
    print("")
    def ultimo_salario(txt):
        if not txt:
            return "sin datos"
        filas = re.findall(r'\["(\d{4}-\d{2})",\s*\d+', txt)
        return "escala " + filas[-1] if filas else "sin datos"

    print("       UOCRA : " + ultimo_salario(sal))
    print("       RIESGO: " + val_simple(riesgo, "valor", " pb")
          + " (" + (re.search(r'fecha:\s*"([^"]+)"', riesgo or "").group(1)
                    if riesgo and re.search(r'fecha:\s*"([^"]+)"', riesgo)
                    else "sin datos") + ")")
    print("")
    print("     Para publicar: hace commit y push de la carpeta docs/")
    print("     (ver PUBLICAR.txt para los pasos completos)")


if __name__ == "__main__":
    main()
