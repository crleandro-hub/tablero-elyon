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

call :log "[1/14] BCRA - valores del dia (TAMAR / BADLAR / UVA)..."
%PY% update_bcra_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_bcra_cache.py - se conservan los datos previos."

call :log "[2/14] BCRA - serie historica UVA..."
%PY% update_uva_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_uva_cache.py - se conserva la serie previa."

call :log "[3/14] Indice CAC..."
%PY% update_cac_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_cac_cache.py - se conservan los datos previos."

call :log "[4/14] Indice MERVAL (pesos y dolares)..."
%PY% update_merval_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_merval_cache.py - se conservan los datos previos."

call :log "[5/14] REM del BCRA (inflacion esperada)..."
%PY% update_rem_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_rem_cache.py - se conservan los datos previos."

call :log "[6/14] Riesgo pais (Rava Bursatil)..."
%PY% update_riesgo_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_riesgo_cache.py - se conservan los datos previos."

call :log "[7/14] Caucion a 1, 7 y 14 dias (Rava Bursatil)..."
%PY% update_caucion_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_caucion_cache.py - se conservan los datos previos."

call :log "[8/14] ISAC e insumos de la construccion (INDEC)..."
%PY% update_isac_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_isac_cache.py - se conservan los datos previos."

call :log "[9/14] ICC de Cordoba (Estadistica y Censos Cba)..."
%PY% update_icc_cba_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_icc_cba_cache.py - se conservan los datos previos."

call :log "[10/14] Registro General de la Propiedad de Cordoba..."
%PY% update_rgp_cba_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_rgp_cba_cache.py - se conservan los datos previos."

call :log "[11/14] ICC del INDEC (Gran Buenos Aires)..."
%PY% update_icc_indec_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_icc_indec_cache.py - se conservan los datos previos."

call :log "[12/14] Generando docs\index.html y version portable..."
%PY% build_publicar.py >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[ERROR] Fallo build_publicar.py. No se publica."
  goto :fin
)

call :log "[13/14] Verificando frescura e integridad de los datos..."
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

call :log "[14/14] Publicando en GitHub Pages..."
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
