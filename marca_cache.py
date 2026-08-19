#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
marca_cache.py - Tablero Gestion Grupo Elyon
============================================
Deja constancia de que un actualizador CORRIO, sin tocar los datos del cache.

Por que hace falta
------------------
El tablero y verificar.py miraban la fecha del campo `updated` para saber si
un script seguia corriendo. Pero `updated` solo cambia cuando el script LOGRA
escribir. Entonces habia dos situaciones distintas que se veian igual:

  · la fuente no publico nada nuevo (normal en las mensuales)
  · el script corre pero el parseo falla (hay que arreglar algo)

y las dos terminaban en el mismo cartel: "el script no corre desde hace N
dias", que ademas es falso. Peor: a los 6 dias verificar.py lo tomaba como
error y frenaba la publicacion de TODO el tablero.

Con esto, cada script estampa en su cache:

  chequeado : cuando corrio por ultima vez (aunque no haya escrito nada)
  aviso     : por que no pudo refrescar, en castellano, o null si anduvo bien

El tablero muestra `aviso` textual en el cartel de fuentes y verificar.py mira
`chequeado` para el control de "hace cuanto corre". Los datos no se tocan.

Uso tipico, al final del script:

    if __name__ == "__main__":
        try:
            main()
        except SystemExit as e:
            marcar(CACHE_PATH, e.code)
            raise
"""

import os
import re
from datetime import datetime


def marcar(cache_path, aviso=None):
    """Reescribe solo `chequeado` y `aviso` dentro del window.XXX_CACHE = {...}.

    No toca ninguna otra linea. Si el archivo no existe o no tiene la forma
    esperada, no hace nada: nunca puede romper un cache bueno."""
    try:
        with open(cache_path, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return False

    m = re.search(r"(window\.[A-Z_0-9]+\s*=\s*\{)", txt)
    if not m:
        return False

    # Se sacan las marcas anteriores y se reescriben arriba de todo: al quedar
    # primeras siempre llevan coma y no hay riesgo de dejar el objeto invalido.
    txt = re.sub(r"\n\s*(chequeado|aviso)\s*:[^\n]*", "", txt)

    marca = '\n  chequeado: "%s",' % datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if aviso:
        limpio = " ".join(str(aviso).split())
        limpio = limpio.replace("\\", "/").replace('"', "'")[:220]
        marca += '\n  aviso: "%s",' % limpio
    else:
        marca += "\n  aviso: null,"

    txt = txt.replace(m.group(1), m.group(1) + marca, 1)
    try:
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(txt)
        os.replace(tmp, cache_path)     # atomico: nunca queda un cache a medias
        return True
    except Exception:
        return False


def guardar_diagnostico(base_dir, nombre, contenido, extension=".html"):
    """Deja lo que llego de la fuente para poder arreglar el parseo sin adivinar."""
    if not contenido:
        return None
    ruta = os.path.join(base_dir, "_%s_diagnostico%s" % (nombre, extension))
    try:
        datos = contenido if isinstance(contenido, (bytes, bytearray)) \
            else contenido.encode("utf-8", "replace")
        with open(ruta, "wb") as f:
            f.write(datos[:2_000_000])
        print("   [diagnostico] se guardo lo recibido en %s" % os.path.basename(ruta))
        return ruta
    except Exception as e:
        print("   [diagnostico] no se pudo guardar: %s" % e)
        return None
