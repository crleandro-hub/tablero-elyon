# Tablero de Gestión — Grupo Elyon

Documento único: qué mide cada indicador, de dónde sale, cómo se publica y qué hacer cuando algo se rompe.

- **Link público:** https://crleandro-hub.github.io/tablero-elyon/
- **Repositorio:** https://github.com/crleandro-hub/tablero-elyon
- GitHub Pages sirve la carpeta `docs` de la rama `main`.

---

## Cómo se actualiza

Una tarea del Programador de tareas de Windows llamada **"Tablero Elyon - Actualizar y publicar"** corre de lunes a viernes a las 11, 13, 15 y 17 y ejecuta `actualizar_auto.bat`. Si la PC estaba apagada, la tarea corre apenas la prendas. El link público se refresca uno o dos minutos después del push.

El ciclo tiene 20 pasos: diecisiete fuentes de datos, el armado del HTML, la verificación y la publicación.

Las fuentes **mensuales** (CAC, REM, ISAC, los dos ICC, el Registro General, el Índice Construya, APYMECO y las series de Córdoba del IERIC) corren solo en la primera vuelta del día: pedirles el dato cada dos horas es tiempo perdido. La marca es el archivo `.ultima_corrida_mensual`.

Si una fuente falla, **no frena el ciclo**: conserva el cache anterior y sigue. Mejor un dato viejo que el tablero roto. La verificación del paso 17 avisa después si algo quedó atrasado, y si encuentra problemas reales en los datos **frena la publicación**.

- A mano, con todo en pantalla: **`2-ACTUALIZAR-TABLERO.bat`**
- Recrear la tarea programada: **`3-PROGRAMAR-TAREA-CADA-2-HORAS.bat`**
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
| Índice Construya | Grupo Construya | `update_construya_cache.py` | `construya_cache.js` | Mensual, ~día 10 | **Scraping de tabla HTML** |
| Costo del m² APYMECO | APYMECO (pymes, La Plata) | `update_apymeco_cache.py` | `apymeco_cache.js` | Mensual | **Scraping de tabla HTML** |
| ISAC: empleo y permisos | INDEC (cuadros 3 y 4) | — | `isac_manual.json` | Mensual | **Carga manual** |
| Registro General de Córdoba | Registro General de la Provincia | `update_rgp_cba_cache.py` | `rgp_cba_cache.js` | Mensual, ~día 23 | CSV vía CKAN |
| Empleo, salario y empresas de Córdoba | IERIC | `update_ieric_cba_cache.py` | `ieric_cba_cache.js` | Mensual, ~2 meses de rezago | **Scraping de links + .xls** |
| MERVAL | Yahoo → Rava → Stooq | `update_merval_cache.py` | `merval_cache.js` | Diario hábil | Scraping, 3 respaldos |
| Riesgo país | Rava, con argentinadatos de respaldo | `update_riesgo_cache.py` | `riesgo_cache.js` | Diario hábil | Scraping HTML |
| REM (inflación esperada) | BCRA | `update_rem_cache.py` | `rem_cache.js` | Mensual | Planilla xlsx |
| Ventas de desarrollistas | CEDUC / Economic Trends | `update_ceduc_cache.py` | `ceduc_cache.js` | Mensual, publicación irregular | **Texto pegado del PDF** |
| Escalas UOCRA / UECARA | Paritarias homologadas | — | `salarios_cache.js` | 2 a 4 veces por año | **Carga manual** |
| Inflación, dólares, crédito hipotecario | datos.gob.ar, dolarapi, ArgentinaDatos | — | — | Diario / mensual | **En vivo desde el navegador** |

### Las fuentes frágiles

Son las que van a romperse primero.

**Riesgo país y MERVAL** dependen de scraping de HTML: si Rava rediseña la página, el script deja de encontrar el número. El de MERVAL tiene tres fuentes en cascada, así que aguanta más.

**Los CSV de Córdoba** se bajan de un link que redirige a un S3 firmado que vence en una hora. Los scripts resuelven el link por la API de CKAN antes de usar el directo, porque el nombre del archivo del Registro General lleva el mes adentro.

**El Índice Construya** no tiene API ni archivo descargable: sale de parsear la tabla HTML de `grupoconstruya.com.ar`. El parser se guía por los **encabezados** de la tabla, no por el orden de las columnas, y antes de escribir controla que la variación interanual publicada coincida con la que sale de dividir los índices. Si no cierra, aborta y deja el cache anterior intacto.

**El IERIC** sirve los `.xls` desde `/wp-content/uploads/AAAA/MM/`, donde ese tramo es la fecha en que subieron el archivo y **cambia cuando lo refrescan**. Hardcodear la URL es la peor trampa de todas: el día que actualicen, el script sigue bajando la versión vieja **sin dar error**. Por eso los links se resuelven leyendo `series_estadisticas/cordoba/` en cada corrida. Además son BIFF viejo (OLE2), así que necesitan `xlrd`: `xlsx_lite.py` no los lee.

**APYMECO** también sale de parsear una tabla HTML, y además **la página solo publica los últimos 13 meses**. Por eso su script es el único que no pisa la serie: la mezcla con la que ya está en el cache y va acumulando historial corrida tras corrida. La consecuencia práctica es que si el parseo se rompe y nadie lo mira durante meses, esos meses no se recuperan: hay que pedírselos a APYMECO o reconstruirlos a mano. El control de integridad se apoya en que el precio del m² y el índice son la misma serie a distinta escala, así que el cociente entre los dos tiene que dar constante (hoy 151,374). Si deja de darlo, el parseo se corrió de columna y el script aborta.

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

**APYMECO aborta con "el cociente precio/índice no es constante"** — cambió el orden de las columnas de la tabla o la asociación rebasó el índice. Corré `python update_apymeco_cache.py --diagnostico`: muestra lo que parseó sin escribir nada. Si el orden cambió, se ajusta la lista `COLUMNAS` del script.

**El costo en dólares de la sección APYMECO no aparece** — sale de las series diarias de ArgentinaDatos, que se piden en vivo. Sin internet, las tarjetas de pesos siguen andando y el gráfico en dólares queda vacío. Es esperado en la versión portable.

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
- `ceduc/ceduc-AAAA-MM.txt` — el informe de CEDUC pasado a texto. Se abre el PDF,
  Ctrl+A, Ctrl+C, se pega en el Bloc de notas y se guarda ahí. Después se corre
  `python update_ceduc_cache.py`. Cada informe trae la serie completa desde 2010,
  así que con el último alcanza.

  **No está en el ciclo automático a propósito**: como el archivo lo armás vos,
  correrlo todos los días solo reescribiría el mismo dato con fecha nueva y
  generaría un commit diario sin cambios reales.

**Ciclo automático**

- `actualizar_auto.bat` — lo que corre la tarea programada.
- `2-ACTUALIZAR-TABLERO.bat` — lo mismo, a mano y con pantalla.
- `actualizar_auto.bat` trae el paso `[16/19]` de APYMECO, dentro del bloque de fuentes mensuales.
  `2-ACTUALIZAR-TABLERO.bat` corre lo mismo a mano: si le agregás fuentes, van en los dos.
- `3-PROGRAMAR-TAREA-CADA-2-HORAS.bat` + `_programar_tarea.ps1` — dan de alta la tarea.
  Para cambiar horarios se toca la línea `$horarios = 11, 13, 15, 17` del `.ps1` y se vuelve a correr.
- `4-PROBAR-MERVAL-Y-REM.bat`, `5-PROBAR-ICC-INDEC.bat` y `7-PROBAR-IERIC-CORDOBA.bat` — prueban una
  fuente sola, sin publicar. El de IERIC lista todas las planillas de la página de Córdoba y vuelca
  su estructura; sirve para ver qué hay publicado hoy cuando algo deja de parsearse.

**Motor**

- Los `update_*.py` de la tabla de arriba.
- `build_publicar.py` — embebe los caches en el HTML y genera las salidas.
- `verificar.py` — chequeo de frescura, integridad y estructura.
- `xlsx_lite.py` — lector mínimo de `.xlsx` con la librería estándar, para que el REM funcione sin pandas.

**Se regeneran solos, no editar**

- Los `*_cache.js`. Con una salvedad: `apymeco_cache.js` se regenera, pero **acumula**.
  Si se borra, se pierde todo el historial anterior a los 13 meses que muestra la página.
- `docs/index.html` — lo que se publica.
- `tablero_elyon_portable.html` — archivo suelto para mandar por mail. Anda sin internet, salvo dólar y riesgo país que son en vivo.

---

## Lo que se evaluó y quedó afuera

Anotado para no repetir la investigación. Agosto de 2026.

**Precio de venta de departamentos en Córdoba Capital.** No hay fuente pública, gratuita y
metodológicamente limpia. Se revisaron tres:

- *Zonaprop Index Córdoba* publica USD/m² de departamentos de Córdoba Capital (USD 1.474 en
  marzo de 2026), pero es precio de **oferta publicada**, no de operación cerrada, la metodología
  es propietaria, sale trimestral y arrastraba 4,5 meses de atraso mientras la edición de CABA
  salía mensual y al día.
- *UdeSA / Mercado Libre* publica variaciones, no un nivel en USD/m². Es un índice, no un precio.
- *IERIC "Precio del M2 Ciudad de Córdoba"* parece la solución y no lo es: sale del Suplemento
  Arquitectura de Clarín, es un rango mínimo/máximo de zona céntrica, la serie mensual termina en
  abril de 2025 y **está clavada en 1.900 / 2.200 desde 2021**. Es un dato muerto.

Conclusión: el tablero no muestra precio de venta. Es un hueco real del mercado, no una falla.

**Despachos de cemento por provincia (AFCP).** El dato existe y es excelente —desde enero de 2004,
mensual, con bolsa y granel por separado, en el `.xls` de la página de Córdoba del IERIC— pero
por disposición de la **Comisión Nacional de Defensa de la Competencia** del 27/04/2022 la AFCP
no puede publicar apertura provincial con menos de doce meses de antigüedad. El rezago es
regulatorio y permanente: nunca va a haber cemento provincial fresco. Se decidió dejarlo afuera
por eso. Si alguna vez se agrega, va como indicador estructural y con el motivo del rezago escrito
en el bloque.

**Permisos de edificación de Córdoba.** El INDEC releva 246 municipios (de Córdoba entran Córdoba,
Alta Gracia, Cosquín y Unquillo) pero **publica solo el agregado nacional**. La DGEyC tiene
recursos de permisos en `datosestadistica.cba.gov.ar`, pero congelados desde 2021. La
Municipalidad de Córdoba no publica permisos en datos abiertos. Quedó pendiente confirmar si el
recurso vivo "Sector Construcción - Coyuntura" los trae adentro.

Ojo con el portal: **`datosabiertos.cba.gov.ar` no existe** (no resuelve DNS). Los reales son
`datosestadistica.cba.gov.ar` (DGEyC, el que ya usan el ICC y el Registro General) y
`datosgestionabierta.cba.gov.ar`.

---

## Seguridad: este tablero es público

La pantalla de login es decorativa. La contraseña está en el JavaScript y el sitio se publica en GitHub Pages, que es público: cualquiera que abra el código fuente la ve, o directamente se saltea la pantalla. Los datos ya viajaron al navegador antes de que se ejecute la validación.

Con el contenido actual no importa: **todo lo que hay acá es información pública** del INDEC, el BCRA y la Provincia de Córdoba.

**La regla: en esta carpeta no entra información confidencial.** Nada de flujo de caja, márgenes, obras ni contratos. Eso va en un proyecto separado, decidido así en agosto de 2026.

El motivo no es sólo la contraseña. `actualizar_auto.bat` corre `git add -A` y `git push` todos los días hábiles sin elegir archivos: **cualquier cosa que quede en esta carpeta se publica sola a la mañana siguiente.** Y git no olvida — un archivo subido una vez queda en el historial público aunque después se borre.

Por eso el tablero tiene una sola pantalla. El menú con los módulos de Ventas y Avance de Obra se quitó: van al proyecto aparte.

Cuando llegue ese momento, la arquitectura cambia: repositorio propio y privado, sin GitHub Pages, sin push automático, y si hace falta acceso remoto con login real, Cloudflare Access con lista de mails autorizados.
