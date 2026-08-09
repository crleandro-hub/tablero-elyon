# Fuentes del Tablero — Grupo Elyon

Qué mide cada indicador, de dónde sale, qué script lo baja y qué hacer cuando falla.

Link público: https://crleandro-hub.github.io/tablero-elyon/

---

## Tabla de fuentes

| Indicador | Fuente | Script | Cache | Publica | Tipo de acceso |
|---|---|---|---|---|---|
| BADLAR, TAMAR, UVA del día | BCRA API v4.0 | `update_bcra_cache.py` | `bcra_cache.js` | Diario hábil | API JSON |
| UVA serie histórica | BCRA API v4.0 | `update_uva_cache.py` | `uva_cache.js` | Diario hábil | API JSON, paginada |
| Índice CAC | Cámara Argentina de la Construcción | `update_cac_cache.py` | `cac_cache.js` | Mensual, ~mitad de mes | **Excel local** en la carpeta |
| ICC Córdoba | Estadística y Censos de Córdoba | `update_icc_cba_cache.py` | `icc_cba_cache.js` | Mensual, ~día 17 | CSV vía CKAN |
| ICC INDEC (GBA) | INDEC | `update_icc_indec_cache.py` | `icc_indec_cache.js` | Mensual, ~día 17 | Excel de nombre fijo |
| ISAC + insumos | INDEC vía SSPM | `update_isac_cache.py` | `isac_cache.js` | Mensual, ~5 semanas de rezago | API de series de tiempo |
| ISAC: empleo y permisos | INDEC (cuadros 3 y 4 del informe) | — | `isac_manual.json` | Mensual | **Carga manual** |
| Registro General de Córdoba | Registro General de la Provincia | `update_rgp_cba_cache.py` | `rgp_cba_cache.js` | Mensual, ~día 23 | CSV vía CKAN |
| MERVAL | Yahoo → Rava → Stooq | `update_merval_cache.py` | `merval_cache.js` | Diario hábil | Scraping con 3 respaldos |
| Riesgo país | Rava, con argentinadatos de respaldo | `update_riesgo_cache.py` | `riesgo_cache.js` | Diario hábil | Scraping HTML |
| REM (inflación esperada) | BCRA | `update_rem_cache.py` | `rem_cache.js` | Mensual | Planilla xlsx |
| Escalas UOCRA / UECARA | Paritarias homologadas | — | `salarios_cache.js` | 2 a 4 veces por año | **Carga manual** |
| Inflación, dólares, crédito hipotecario | datos.gob.ar, dolarapi, ArgentinaDatos | — | — | Diario / mensual | **En vivo desde el navegador** |

---

## Las tres fuentes frágiles

Son las que van a romperse primero. Vale la pena saber cuáles son.

**Riesgo país y MERVAL** dependen de scraping de HTML. Si Rava rediseña la página, el script deja de encontrar el número. El de MERVAL tiene tres fuentes en cascada, así que aguanta más.

**Los CSV de Córdoba** (ICC y Registro General) se bajan de un link que redirige a un S3 firmado que vence en una hora. Los scripts resuelven el link por la API de CKAN antes de usar el link directo, porque el nombre del archivo del Registro General lleva el mes adentro y se pincha cuando publican uno nuevo.

**El Excel del ICC INDEC** viene transpuesto: capítulos en filas y meses en columnas, agrupados por año. El parser busca la fila de años y la de meses en vez de asumir posiciones fijas, y valida el resultado contra junio 2026 antes de escribir nada. Si el INDEC cambia el formato, el script aborta y vuelca la estructura en vez de guardar cualquier cosa.

---

## Cuando algo falla

El `.bat` nunca pisa un cache con datos malos: si un script falla, conserva el anterior y sigue. Eso evita romper el tablero, pero también hace que una fuente pueda quedar muerta sin que se note. Por eso hay dos controles:

- **`verificar.py`** corre al final del ciclo y avisa qué fuente está atrasada, si hay huecos en las series o saltos sospechosos. Devuelve error si algo está roto.
- **El tablero** muestra un cartel rojo arriba de todo cuando algún cache quedó viejo para su frecuencia.

Pasos para diagnosticar:

1. Abrí `log_actualizacion.txt` y buscá el `[AVISO] Fallo` correspondiente.
2. Corré el script solo, a mano, para ver el error completo: `python update_XXX_cache.py`.
3. Si el problema es de formato de la fuente, casi todos los scripts tienen modo diagnóstico. El del ICC INDEC es `python update_icc_indec_cache.py --diagnostico`.

---

## Los archivos de la carpeta

**Ciclo automático**

- `actualizar_auto.bat` — lo que corre la tarea programada de lunes a viernes 8:30. Actualiza, verifica, publica.
- `2-ACTUALIZAR-TABLERO.bat` — lo mismo pero a mano, con la salida en pantalla.
- `3-PROGRAMAR-TAREA-8-30.bat` y `_programar_tarea.ps1` — dan de alta la tarea programada.
- `4-PROBAR-MERVAL-Y-REM.bat` y `5-PROBAR-ICC-INDEC.bat` — prueban una fuente sola, sin publicar.

**Construcción del tablero**

- `tablero_elyon.html` — el tablero. Es el único archivo que se edita.
- `build_publicar.py` — embebe todos los caches adentro del HTML y genera `docs/index.html` (GitHub Pages) y `tablero_elyon_portable.html` (para mandar suelto).
- `verificar.py` — el chequeo general.
- `xlsx_lite.py` — lector mínimo de `.xlsx` con la librería estándar, para que `update_rem_cache.py` funcione en una PC sin pandas.

**Datos que se editan a mano**

- `salarios_cache.js` — escalas de convenio. Las instrucciones están en el encabezado del archivo.
- `isac_manual.json` — empleo registrado y permisos de edificación del informe del INDEC.

---

## Seguridad: este tablero es público

La pantalla de login es decorativa. La contraseña está en el JavaScript y el sitio se publica en GitHub Pages, que es público: cualquiera que abra el código fuente la ve, o directamente se saltea la pantalla. Los datos ya viajaron al navegador antes de que se ejecute la validación.

Con el contenido actual no importa, porque **todo lo que hay acá es información pública** del INDEC, el BCRA y la Provincia de Córdoba.

**La regla, entonces: en esta carpeta no entra información confidencial.** Nada de flujo de caja, márgenes, obras ni contratos. Eso va en un proyecto separado, decidido así en agosto de 2026.

El motivo no es sólo la contraseña. `actualizar_auto.bat` corre `git add -A` y `git push` todos los días hábiles a las 8:30, sin elegir archivos: **cualquier cosa que quede en esta carpeta se publica sola a la mañana siguiente.** Y git no olvida — un archivo subido una vez queda en el historial público aunque después se borre.

Por eso el tablero tiene una sola pantalla. El menú con los módulos de Ventas y Avance de Obra se quitó: esos van al proyecto aparte.
