@echo off
rem =====================================================
rem  GRUPO ELYON - Actualizacion automatica (sin dialogos).
rem  Lo ejecuta el Programador de tareas de Windows.
rem  Para correrlo a mano: 2-ACTUALIZAR-TABLERO.bat
rem =====================================================
setlocal
cd /d "%~dp0"
set "LOG=%~dp0log_actualizacion.txt"

rem ---------- Rotar el registro si supera 1 MB ----------
for %%F in ("%LOG%") do if %%~zF GTR 1048576 (
  if exist "%LOG%.old" del /f /q "%LOG%.old"
  move /y "%LOG%" "%LOG%.old" >nul
)

call :log "==================================================="
call :log "Inicio: %date% %time%"

rem ---------- Detectar Python ----------
call :buscarpython
if not defined PY (
  call :log "[ERROR] No se encontro Python en esta PC."
  call :log "        Instalalo desde https://www.python.org/downloads/windows/"
  call :log "        tildando 'Add python.exe to PATH'. Se aborta."
  goto :fin
)
call :log "Python: %PY%"

where git >nul 2>&1
if errorlevel 1 (
  call :log "[ERROR] Git no esta instalado. Se aborta."
  goto :fin
)
if not exist ".git" (
  call :log "[ERROR] No hay repositorio git en la carpeta. Se aborta."
  goto :fin
)

rem ---------- Limpiar bloqueos huerfanos ----------
if exist ".git\index.lock"               del /f /q ".git\index.lock"
if exist ".git\HEAD.lock"                del /f /q ".git\HEAD.lock"
if exist ".git\objects\maintenance.lock" del /f /q ".git\objects\maintenance.lock"

rem =====================================================
rem  DIARIAS vs MENSUALES
rem  La tarea corre 4 veces por dia, pero el CAC, el REM, el ISAC, los dos
rem  ICC, el Registro General y el Indice Construya publican una vez por mes:
rem  pedirles el dato cada corrida es tiempo perdido y golpear de mas a la
rem  fuente. Esas siete corren SOLO en la primera vuelta del dia. La marca es un
rem  archivo con la fecha adentro; si no coincide con hoy, se corren.
rem =====================================================
set "MARCA=%~dp0.ultima_corrida_mensual"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "HOY=%%d"

set "MENSUALES=1"
if not exist "%MARCA%" goto :marca_lista
set /p ULTIMA=<"%MARCA%"
if "%ULTIMA%"=="%HOY%" set "MENSUALES=0"
:marca_lista
if "%MENSUALES%"=="1" (
  call :log "Primera corrida de %HOY%: se actualizan tambien las fuentes mensuales."
) else (
  call :log "Las fuentes mensuales ya se actualizaron hoy: se omiten."
)

call :log "[1/18] BCRA - valores del dia (TAMAR / BADLAR / UVA)..."
%PY% update_bcra_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_bcra_cache.py - se conservan los datos previos."

call :log "[2/18] BCRA - serie historica UVA..."
%PY% update_uva_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_uva_cache.py - se conserva la serie previa."

if "%MENSUALES%"=="1" (
  call :log "[3/18] Indice CAC..."
  %PY% update_cac_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_cac_cache.py - se conservan los datos previos."
) else (
  call :log "[3/18] Indice CAC... omitido (mensual, ya corrio hoy)"
)

call :log "[4/18] Indice MERVAL (pesos y dolares)..."
%PY% update_merval_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_merval_cache.py - se conservan los datos previos."

if "%MENSUALES%"=="1" (
  call :log "[5/18] REM del BCRA (inflacion esperada)..."
  %PY% update_rem_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_rem_cache.py - se conservan los datos previos."
) else (
  call :log "[5/18] REM del BCRA (inflacion esperada)... omitido (mensual, ya corrio hoy)"
)

call :log "[6/18] Riesgo pais (Rava Bursatil)..."
%PY% update_riesgo_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_riesgo_cache.py - se conservan los datos previos."

call :log "[7/18] Caucion a 1, 7 y 14 dias (Rava Bursatil)..."
%PY% update_caucion_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_caucion_cache.py - se conservan los datos previos."

call :log "[8/18] Dolar futuro ROFEX (Matba Rofex)..."
%PY% update_rofex_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_rofex_cache.py - se conservan los datos previos."

call :log "[9/18] Acciones del panel lider (BYMA)..."
%PY% update_acciones_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_acciones_cache.py - se conservan los datos previos."

call :log "[10/18] Tipo de cambio - respaldo (dolarapi / bluelytics)..."
%PY% update_dolar_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_dolar_cache.py - se conserva el respaldo previo."

if "%MENSUALES%"=="1" (
  call :log "[11/18] ISAC e insumos de la construccion (INDEC)..."
  %PY% update_isac_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_isac_cache.py - se conservan los datos previos."
) else (
  call :log "[11/18] ISAC e insumos de la construccion (INDEC)... omitido (mensual, ya corrio hoy)"
)

if "%MENSUALES%"=="1" (
  call :log "[12/18] ICC de Cordoba (Estadistica y Censos Cba)..."
  %PY% update_icc_cba_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_icc_cba_cache.py - se conservan los datos previos."
) else (
  call :log "[12/18] ICC de Cordoba (Estadistica y Censos Cba)... omitido (mensual, ya corrio hoy)"
)

if "%MENSUALES%"=="1" (
  call :log "[13/18] Registro General de la Propiedad de Cordoba..."
  %PY% update_rgp_cba_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_rgp_cba_cache.py - se conservan los datos previos."
) else (
  call :log "[13/18] Registro General de la Propiedad de Cordoba... omitido (mensual, ya corrio hoy)"
)

if "%MENSUALES%"=="1" (
  call :log "[14/18] ICC del INDEC (Gran Buenos Aires)..."
  %PY% update_icc_indec_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_icc_indec_cache.py - se conservan los datos previos."
) else (
  call :log "[14/18] ICC del INDEC (Gran Buenos Aires)... omitido (mensual, ya corrio hoy)"
)

if "%MENSUALES%"=="1" (
  call :log "[15/18] Indice Construya (Grupo Construya)..."
  %PY% update_construya_cache.py >> "%LOG%" 2>&1
  if errorlevel 1 call :log "[AVISO] Fallo update_construya_cache.py - se conservan los datos previos."
) else (
  call :log "[15/18] Indice Construya (Grupo Construya)... omitido (mensual, ya corrio hoy)"
)

if "%MENSUALES%"=="1" (echo %HOY%)>"%MARCA%"

call :log "[16/18] Generando docs\index.html y version portable..."
%PY% build_publicar.py >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[ERROR] Fallo build_publicar.py. No se publica."
  goto :fin
)

call :log "[17/18] Verificando frescura e integridad de los datos..."
%PY% verificar.py >> "%LOG%" 2>&1
rem  0 = todo bien   1 = datos con problemas, no publicar
rem  2 = se cayo el verificador, es un bug suyo: se publica igual
rem  Se compara el codigo exacto en vez de usar "if errorlevel", que en cmd
rem  significa "mayor o igual" y encadenado con else se comporta mal.
set "RC=%errorlevel%"
if "%RC%"=="2" call :log "[AVISO] verificar.py no pudo completarse. Se publica igual."
if "%RC%"=="1" (
  call :log "[ERROR] verificar.py encontro problemas en los datos. NO se publica."
  goto :fin
)

call :log "[18/18] Publicando en GitHub Pages..."
git add -A >> "%LOG%" 2>&1
git commit -m "Actualizacion automatica de indicadores %date%" >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[INFO] Sin cambios en los datos. Nada para publicar."
  goto :fin
)
git push >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[ERROR] Fallo el push a GitHub."
  goto :fin
)
call :log "[OK] Publicado. El link se refresca en 1-2 minutos."

:fin
call :log "Fin: %date% %time%"
exit /b 0


rem =====================================================
rem  Subrutinas
rem =====================================================

:buscarpython
rem Deja en PY el comando de Python que funcione, o vacio.
rem Prueba: py -3  ->  python  ->  python3  ->  instalaciones tipicas.
set "PY="
py -3 -c "import sys" >nul 2>&1     && set "PY=py -3"      && exit /b 0
python  -c "import sys" >nul 2>&1   && set "PY=python"     && exit /b 0
python3 -c "import sys" >nul 2>&1   && set "PY=python3"    && exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
for /d %%D in ("%ProgramFiles%\Python3*") do (
  if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
for /d %%D in ("C:\Python3*") do (
  if not defined PY if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
)
exit /b 0

:log
echo %~1
echo %~1>> "%LOG%"
exit /b 0
