#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xlsx_lite.py - Tablero Gestion Grupo Elyon
==========================================
Lector minimo de archivos .xlsx usando SOLO la libreria estandar.

Por que existe:
    Los scripts del tablero corren en la PC con la tarea programada, donde no
    hay garantia de tener openpyxl ni pandas instalados. Un .xlsx no es mas que
    un ZIP con XML adentro, asi que se puede leer con zipfile + ElementTree.

Uso:
    from xlsx_lite import leer_hoja
    filas = leer_hoja(ruta_o_bytes, "Cuadros de resultados")
    # filas -> lista de listas; cada celda es str, float o None
"""

import datetime as _dt
import io
import re
import zipfile
import xml.etree.ElementTree as ET

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# Serial 1 de Excel = 1900-01-01, con el bug del 29/02/1900 que Excel arrastra.
_EPOCH = _dt.datetime(1899, 12, 30)


def _col_index(ref):
    """'BC12' -> 54 (indice de columna base 0)."""
    letras = re.match(r"([A-Z]+)", ref or "")
    if not letras:
        return 0
    n = 0
    for c in letras.group(1):
        n = n * 26 + (ord(c) - 64)
    return n - 1


def _shared_strings(z):
    try:
        raw = z.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    out = []
    for si in ET.fromstring(raw).findall(NS_MAIN + "si"):
        # El texto puede venir partido en varios <t> (por formato enriquecido)
        out.append("".join(t.text or "" for t in si.iter(NS_MAIN + "t")))
    return out


def _hojas(z):
    """{nombre de hoja: ruta interna del xml}."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    destino = {r.get("Id"): r.get("Target") for r in rels.findall(NS_PKG + "Relationship")}

    out = {}
    for sh in wb.iter(NS_MAIN + "sheet"):
        rid = sh.get(NS_REL + "id")
        tgt = destino.get(rid, "")
        if not tgt:
            continue
        if tgt.startswith("/"):
            tgt = tgt[1:]
        elif not tgt.startswith("xl/"):
            tgt = "xl/" + tgt
        out[sh.get("name")] = tgt
    return out


def _fechas_por_estilo(z):
    """Indices de estilo que representan fechas, para convertir el serial."""
    try:
        st = ET.fromstring(z.read("xl/styles.xml"))
    except KeyError:
        return set()

    # Formatos propios del archivo que parezcan fecha
    fmt_fecha = set()
    for nf in st.iter(NS_MAIN + "numFmt"):
        code = (nf.get("formatCode") or "").lower()
        if any(x in code for x in ("yy", "dd", "mmm")) and "[" not in code:
            fmt_fecha.add(int(nf.get("numFmtId")))
    # Formatos de fecha predefinidos de Excel
    fmt_fecha |= set(range(14, 23)) | set(range(45, 48)) | {27, 30, 36, 50, 57}

    xfs = st.find(NS_MAIN + "cellXfs")
    if xfs is None:
        return set()
    return {i for i, xf in enumerate(xfs.findall(NS_MAIN + "xf"))
            if int(xf.get("numFmtId") or 0) in fmt_fecha}


def leer_hoja(origen, nombre_hoja=None):
    """Devuelve la hoja como lista de filas (listas de celdas).

    origen      : ruta a un .xlsx o los bytes del archivo
    nombre_hoja : nombre exacto; si es None toma la primera hoja
    """
    datos = origen if isinstance(origen, (bytes, bytearray)) else open(origen, "rb").read()
    z = zipfile.ZipFile(io.BytesIO(datos))

    strings = _shared_strings(z)
    hojas = _hojas(z)
    estilos_fecha = _fechas_por_estilo(z)

    if nombre_hoja is None:
        ruta = next(iter(hojas.values()))
    else:
        if nombre_hoja not in hojas:
            raise KeyError("No existe la hoja '%s'. Hojas: %s"
                           % (nombre_hoja, ", ".join(hojas)))
        ruta = hojas[nombre_hoja]

    filas = []
    for row in ET.fromstring(z.read(ruta)).iter(NS_MAIN + "row"):
        celdas = []
        for c in row.findall(NS_MAIN + "c"):
            i = _col_index(c.get("r"))
            while len(celdas) < i:
                celdas.append(None)

            tipo = c.get("t")
            if tipo == "inlineStr":
                nodo = c.find(NS_MAIN + "is")
                val = "".join(t.text or "" for t in nodo.iter(NS_MAIN + "t")) if nodo is not None else None
            else:
                v = c.find(NS_MAIN + "v")
                bruto = v.text if v is not None else None
                if bruto is None:
                    val = None
                elif tipo == "s":
                    idx = int(bruto)
                    val = strings[idx] if idx < len(strings) else None
                elif tipo in ("str", "e"):
                    val = bruto
                elif tipo == "b":
                    val = bruto == "1"
                else:
                    try:
                        num = float(bruto)
                    except ValueError:
                        val = bruto
                    else:
                        s = c.get("s")
                        if s is not None and int(s) in estilos_fecha and num > 0:
                            val = (_EPOCH + _dt.timedelta(days=num)).strftime("%Y-%m-%d")
                        else:
                            val = num
            celdas.append(val)
        filas.append(celdas)
    return filas


def nombres_de_hojas(origen):
    datos = origen if isinstance(origen, (bytes, bytearray)) else open(origen, "rb").read()
    return list(_hojas(zipfile.ZipFile(io.BytesIO(datos))))
