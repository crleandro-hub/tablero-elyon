@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Actualizar tablero publicado
cd /d "%~dp0"

echo =====================================================
echo  GRUPO ELYON - Actualizar el tablero publicado
echo =====================================================
echo.

call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  echo.
  echo   Instalalo desde https://www.python.org/downloads/windows/
  echo   IMPORTANTE: tilda "Add python.exe to PATH" en la primera
  echo   pantalla del instalador. Despues cerra esta ventana y
  echo   volve a ejecutar este archivo.
  echo.
  pause
  exit /b 1
)
echo [OK] Python: %PY%

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git no esta instalado. Descargalo de https://git-scm.com/download/win
  pause
  exit /b 1
)
if not exist ".git" (
  echo [ERROR] No hay repositorio git en esta carpeta.
  pause
  exit /b 1
)
echo [OK] Git detectado.
echo.

rem --- Limpiar bloqueos huerfanos de corridas cortadas ---
if exist ".git\index.lock"               del /f /q ".git\index.lock"
if exist ".git\HEAD.lock"                del /f /q ".git\HEAD.lock"
if exist ".git\objects\maintenance.lock" del /f /q ".git\objects\maintenance.lock"

echo [1/4] Actualizando BCRA (TAMAR / BADLAR / UVA)...
%PY% update_bcra_cache.py
if errorlevel 1 echo [AVISO] Fallo - se conservan los datos previos.

echo.
echo [2/4] Actualizando indice CAC...
%PY% update_cac_cache.py
if errorlevel 1 echo [AVISO] Fallo - se conservan los datos previos.

echo.
echo [3/4] Generando docs\index.html y version portable...
%PY% build_publicar.py
if errorlevel 1 (
  echo [ERROR] Fallo build_publicar.py. Cancelado.
  pause
  exit /b 1
)

echo.
echo [4/4] Publicando en GitHub Pages...
git add -A
git commit -m "Actualizacion de indicadores %date% %time%" 2>nul
if errorlevel 1 (
  echo [INFO] No hubo cambios en los datos. Nada para subir.
  echo.
  pause
  exit /b 0
)
git push
if errorlevel 1 (
  echo.
  echo [ERROR] Fallo el push. Revisa la conexion o la autorizacion de GitHub.
  pause
  exit /b 1
)

echo.
echo =====================================================
echo  LISTO - El link publico se actualiza en 1-2 minutos
echo  https://crleandro-hub.github.io/tablero-elyon/
echo =====================================================
echo.
pause
exit /b 0


:buscarpython
rem Deja en PY el comando de Python que funcione, o vacio.
set "PY="
py -3 -c "import sys" >nul 2>&1     && set "PY=py -3"   && exit /b 0
python  -c "import sys" >nul 2>&1   && set "PY=python"  && exit /b 0
python3 -c "import sys" >nul 2>&1   && set "PY=python3" && exit /b 0
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
