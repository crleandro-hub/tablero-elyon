# Tablero de Gestión — Grupo Elyon

Documento único: qué mide cada indicador, de dónde sale, cómo se publica y qué hacer cuando algo se rompe.

- **Link público:** https://crleandro-hub.github.io/tablero-elyon/
- **Repositorio:** https://github.com/crleandro-hub/tablero-elyon
- GitHub Pages sirve la carpeta `docs` de la rama `main`.

---

## Cómo se actualiza

Una tarea del Programador de tareas de Windows llamada **"Tablero Elyon - Actualizar y publicar"** corre de lunes a viernes a las 8:30 y ejecuta `actualizar_auto.bat`. Si la PC estaba apagada, la tarea corre apenas la prendas. El link público se refresca uno o dos minutos después del push.

El ciclo tiene 13 pasos: diez fuentes de datos, el armado del HTML, la verificación y la publicación.

Si una fuente falla, **no frena el ciclo**: conserva el cache anterior y sigue. Mejor un dato viejo que el tablero roto. La verificación del paso 12 avisa después si algo quedó atrasado, y si encuentra problemas reales en los datos **frena la publicación**.

- A mano, con todo en pantalla: **`2-ACTUALIZAR-TABLERO.bat`**
- Recrear la tarea programada: **`3-PROGRAMAR-TAREA-8-30.bat`**
- Ver o modificar la tarea: Inicio → "Programador de tareas"

Cada corrida deja constancia en `log_actualizacion.txt` (automática) o `log_actualizar.txt` (manual). Ninguno se sube al repositorio.

---

## Tabla de fuentes

| Indicador | Fuente | Script | Cache | Publica | Acceso |
|---|---|---|---|---|---|
| BADLAR, TAMAR, UVA del día | BCRA API v4.0 | `update_bcra_cache.py` | `bcra_cache.js` | Diario hábil | API JSON |
| UVA serie histórica | BCRA API v4.0 | `update_uva_cache.py` | `uva_cache.js` | Diario hábil | API JSON, paginada |
| Índice CAC | Cámara Argentina de la Construcción | `update_cac_cache.py` | `cac_cache.js` | Mensual, ~mitad de mes | **Excel local** |
| ICC Córdoba | Estadística y Censos de Córdoba | `update_icc_cba_cache.py` | `icc_cba_cache.js` | Mensual, ~día 17 | CSV vía CKAN |
| ICC INDEC (GBA) | INDEC | `update_icc_indec_cache.py` | `icc_indec_cache.js` | Mensual, ~día 17 | Excel de nombre fijo |
| ISAC + insumos | INDEC vía SSPM | `update_isac_cache.py` | `isac_cache.js` | Mensual, ~5 semanas de rezago | API de series |
| ISAC: empleo y permisos | INDEC (cuadros 3 y 4) | — | `isac_manual.json` | Mensual | **Carga manual** |
| Registro General de Córdoba | Registro General de la Provincia | `update_rgp_cba_cache.py` | `rgp_cba_cache.js` | Mensual, ~día 23 | CSV vía CKAN |
| MERVAL | Yahoo → Rava → Stooq | `update_merval_cache.py` | `merval_cache.js` | Diario hábil | Scraping, 3 respaldos |
| Riesgo país | Rava, con argentinadatos de respaldo | `update_riesgo_cache.py` | `riesgo_cache.js` | Diario hábil | Scraping HTML |
| REM (inflación esperada) | BCRA | `update_rem_cache.py` | `rem_cache.js` | Mensual | Planilla xlsx |
| Escalas UOCRA / UECARA | Paritarias homologadas | — | `salarios_cache.js` | 2 a 4 veces por año | **Carga manual** |
| Inflación, dólares, crédito hipotecario | datos.gob.ar, dolarapi, ArgentinaDatos | — | — | Diario / mensual | **En vivo desde el navegador** |

### Las fuentes frágiles

Son las que van a romperse primero.

**Riesgo país y MERVAL** dependen de scraping de HTML: si Rava rediseña la página, el script deja de encontrar el número. El de MERVAL tiene tres fuentes en cascada, así que aguanta más.

**Los CSV de Córdoba** se bajan de un link que redirige a un S3 firmado que vence en una hora. Los scripts resuelven el link por la API de CKAN antes de usar el directo, porque el nombre del archivo del Registro General lleva el mes adentro.

**El Excel del ICC INDEC** viene transpuesto: capítulos en filas y meses en columnas. El parser busca la fila de años y la de meses en vez de asumir posiciones, y valida contra junio 2026 antes de escribir. Si el INDEC cambia el formato, aborta y vuelca la estructura.

---

## Si algo se rompe

**Primero:** abrí el log y buscá el `[AVISO] Fallo`. Después corré ese script solo, a mano, para ver el error completo: `python update_XXX_cache.py`. Varios tienen modo diagnóstico, por ejemplo `python update_icc_indec_cache.py --diagnostico`.

**`fatal: Unable to create '.git/index.lock'`** — quedó un bloqueo de una corrida cortada. `actualizar_auto.bat` ya limpia esto antes de empezar; si persiste:

```
cd "C:\Users\LMoreno\Dropbox\CLAUDE\Tablero General Grupo Elyon"
Remove-Item .git\*.lock, .git\objects\maintenance.lock -Force -ErrorAction SilentlyContinue
```

**`[EXCEL DESACTUALIZADO]` en el log** — salió un mes nuevo del CAC. Bajá la serie histórica de camarco.org.ar/indicadores y pisá el `.xls` de la carpeta. El resto se actualiza solo.

**El push pide usuario y contraseña** — se perdieron las credenciales del Credential Manager. Corré `git push` a mano una vez desde PowerShell: se abre el navegador, autorizás, y queda guardado.

**El link muestra datos viejos** — fijate en el log si la publicación dijo `[OK]`. También puede ser caché del navegador: Ctrl+F5.

**La serie de UVA termina después de hoy** — es correcto. El BCRA publica la UVA por anticipado. Si *no* lo hace, cambió algo en la fuente.

**Las tarjetas de dólar de arriba no coinciden con la sección de abajo** — no es un error. Arriba va dolarapi.com, en vivo. La serie histórica sale de ArgentinaDatos, que publica el cierre con un día de rezago. Las variaciones de las tarjetas son cierre contra cierre.

**El tablero muestra un cartel rojo de fuentes desactualizadas** — comparó la fecha de cada cache contra lo que corresponde a su frecuencia y algo quedó viejo. Dice cuál y hace cuántos días.

---

## Los archivos de la carpeta

**Se edita a mano**

- `tablero_elyon.html` — el tablero. Es el único archivo de diseño.
- `Indicador CAC_serie histórica.xls` — serie del CAC. Se pisa cuando sale un mes nuevo.
- `salarios_cache.js` — escalas de convenio. Instrucciones en el encabezado del archivo.
- `isac_manual.json` — empleo y permisos del informe del INDEC.

**Ciclo automático**

- `actualizar_auto.bat` — lo que corre la tarea programada.
- `2-ACTUALIZAR-TABLERO.bat` — lo mismo, a mano y con pantalla.
- `3-PROGRAMAR-TAREA-8-30.bat` + `_programar_tarea.ps1` — dan de alta la tarea.
- `4-PROBAR-MERVAL-Y-REM.bat` y `5-PROBAR-ICC-INDEC.bat` — prueban una fuente sola, sin publicar.

**Motor**

- Los once `update_*.py` de la tabla de arriba.
- `build_publicar.py` — embebe los caches en el HTML y genera las salidas.
- `verificar.py` — chequeo de frescura, integridad y estructura.
- `xlsx_lite.py` — lector mínimo de `.xlsx` con la librería estándar, para que el REM funcione sin pandas.

**Se regeneran solos, no editar**

- Los once `*_cache.js`.
- `docs/index.html` — lo que se publica.
- `tablero_elyon_portable.html` — archivo suelto para mandar por mail. Anda sin internet, salvo dólar y riesgo país que son en vivo.

---

## Seguridad: este tablero es público

La pantalla de login es decorativa. La contraseña está en el JavaScript y el sitio se publica en GitHub Pages, que es público: cualquiera que abra el código fuente la ve, o directamente se saltea la pantalla. Los datos ya viajaron al navegador antes de que se ejecute la validación.

Con el contenido actual no importa: **todo lo que hay acá es información pública** del INDEC, el BCRA y la Provincia de Córdoba.

**La regla: en esta carpeta no entra información confidencial.** Nada de flujo de caja, márgenes, obras ni contratos. Eso va en un proyecto separado, decidido así en agosto de 2026.

El motivo no es sólo la contraseña. `actualizar_auto.bat` corre `git add -A` y `git push` todos los días hábiles sin elegir archivos: **cualquier cosa que quede en esta carpeta se publica sola a la mañana siguiente.** Y git no olvida — un archivo subido una vez queda en el historial público aunque después se borre.

Por eso el tablero tiene una sola pantalla. El menú con los módulos de Ventas y Avance de Obra se quitó: van al proyecto aparte.

Cuando llegue ese momento, la arquitectura cambia: repositorio propio y privado, sin GitHub Pages, sin push automático, y si hace falta acceso remoto con login real, Cloudflare Access con lista de mails autorizados.
