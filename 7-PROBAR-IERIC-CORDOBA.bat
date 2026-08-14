@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Probar fuente IERIC Cordoba
cd /d "%~dp0"

echo =====================================================
echo  Prueba de la fuente: IERIC - series de Cordoba
echo =====================================================
echo.
echo  Abre la pagina de series estadisticas de Cordoba del
echo  IERIC, baja las planillas que cuelgan de ahi y muestra
echo  que tienen adentro: hojas, columnas, periodo cubierto.
echo.
echo  NO escribe ningun cache, NO toca el tablero y NO publica
echo  nada en GitHub. Es solo para mirar.
echo.
echo  Todo queda guardado en log_ieric_cordoba.txt, asi que no
echo  hace falta que copies nada: alcanza con decirle a Claude
echo  que ya lo corriste y el lee el archivo.
echo.

set "LOG=%~dp0log_ieric_cordoba.txt"
echo ===================================================== > "%LOG%"
echo  Prueba IERIC Cordoba - %date% %time% >> "%LOG%"
echo ===================================================== >> "%LOG%"

call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  echo [ERROR] No se encontro Python en esta PC. >> "%LOG%"
  pause
  exit /b 1
)
echo [OK] Python: %PY%
echo Python usado: %PY% >> "%LOG%"
echo.

echo -----------------------------------------------------
echo  Bajando y leyendo las planillas del IERIC
echo  (puede tardar un minuto: son varios archivos)
echo -----------------------------------------------------
echo. >> "%LOG%"
%PY% probar_ieric_cordoba.py >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
type "%LOG%"
echo.

if not "%RC%"=="0" (
  echo =====================================================
  echo  Termino con errores. El detalle esta en:
  echo    log_ieric_cordoba.txt
  echo  Decile a Claude que ya lo corriste y el lo lee solo.
  echo =====================================================
  echo.
  pause
  exit /b %RC%
)

echo =====================================================
echo  Listo. No se modifico nada del tablero.
echo.
echo  Las planillas bajadas quedaron en la carpeta
echo    _diagnostico_ieric\
echo  por si las queres abrir a mano con Excel.
echo.
echo  Decile a Claude que ya lo corriste.
echo =====================================================
echo.
pause
exit /b 0


:buscarpython
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
exit /b 0
