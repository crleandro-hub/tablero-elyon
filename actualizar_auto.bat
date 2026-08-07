@echo off
rem =====================================================
rem  GRUPO ELYON - Actualizacion automatica (sin ventanas
rem  de dialogo). Lo ejecuta el Programador de tareas de
rem  Windows. Para correrlo a mano, usa 2-ACTUALIZAR-TABLERO.bat
rem =====================================================
setlocal
cd /d "%~dp0"
set "LOG=%~dp0log_actualizacion.txt"

call :log "==================================================="
call :log "Inicio: %date% %time%"

where git >nul 2>&1
if errorlevel 1 (
  call :log "[ERROR] Git no esta instalado. Se aborta."
  exit /b 1
)
if not exist ".git" (
  call :log "[ERROR] No hay repositorio git en la carpeta. Se aborta."
  exit /b 1
)

rem --- Limpiar bloqueos huerfanos de corridas previas ---
if exist ".git\index.lock"              del /f /q ".git\index.lock"
if exist ".git\HEAD.lock"               del /f /q ".git\HEAD.lock"
if exist ".git\objects\maintenance.lock" del /f /q ".git\objects\maintenance.lock"

call :log "[1/4] BCRA (TAMAR / BADLAR / UVA)..."
python update_bcra_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_bcra_cache.py - se conservan los datos previos."

call :log "[2/4] Indice CAC..."
python update_cac_cache.py >> "%LOG%" 2>&1
if errorlevel 1 call :log "[AVISO] Fallo update_cac_cache.py - se conservan los datos previos."

call :log "[3/4] Generando docs\index.html y version portable..."
python build_publicar.py >> "%LOG%" 2>&1
if errorlevel 1 (
  call :log "[ERROR] Fallo build_publicar.py. No se publica."
  goto :fin
)

call :log "[4/4] Publicando en GitHub Pages..."
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

:log
echo %~1
echo %~1>> "%LOG%"
exit /b 0
