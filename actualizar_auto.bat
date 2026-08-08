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

call :log "[1/8] BCRA - valores del dia (TAMAR / BADLAR / UVA)..."
%PY% update_bcra_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_bcra_cache.py - se conservan los datos previos."

call :log "[2/8] BCRA - serie historica UVA..."
%PY% update_uva_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_uva_cache.py - se conserva la serie previa."

call :log "[3/8] Indice CAC..."
%PY% update_cac_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_cac_cache.py - se conservan los datos previos."

call :log "[4/8] Indice MERVAL (pesos y dolares)..."
%PY% update_merval_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_merval_cache.py - se conservan los datos previos."

call :log "[5/8] REM del BCRA (inflacion esperada)..."
%PY% update_rem_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_rem_cache.py - se conservan los datos previos."

call :log "[6/9] Riesgo pais (Rava Bursatil)..."
%PY% update_riesgo_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_riesgo_cache.py - se conservan los datos previos."

call :log "[7/10] ISAC e insumos de la construccion (INDEC)..."
%PY% update_isac_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_isac_cache.py - se conservan los datos previos."

call :log "[8/11] ICC de Cordoba (Estadistica y Censos Cba)..."
%PY% update_icc_cba_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_icc_cba_cache.py - se conservan los datos previos."

call :log "[9/12] Registro General de la Propiedad de Cordoba..."
%PY% update_rgp_cba_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_rgp_cba_cache.py - se conservan los datos previos."

call :log "[10/12] ICC del INDEC (Gran Buenos Aires)..."
%PY% update_icc_indec_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_icc_indec_cache.py - se conservan los datos previos."

call :log "[11/12] Generando docs\index.html y version portable..."
%PY% build_publicar.py >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[ERROR] Fallo build_publicar.py. No se publica."
  goto :fin
)

call :log "[12/12] Publicando en GitHub Pages..."
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
