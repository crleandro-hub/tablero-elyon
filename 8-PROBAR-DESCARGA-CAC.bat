@echo off
title GRUPO ELYON - Probar la descarga del indice CAC
cd /d "%~dp0"
echo.
echo =====================================================
echo  Prueba: bajar la serie del CAC desde cifrasonline
echo =====================================================
echo.
echo  Esto NO toca el tablero. Solo mira que publica la
echo  pagina y, si lo que hay ahi llega mas lejos que tu
echo  Excel, lo reemplaza (el anterior queda guardado en
echo  la carpeta _cac_backup).
echo.
call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  pause
  exit /b 1
)
%PY% update_cac_cache.py --descargar
echo.
pause
exit /b 0

:buscarpython
set "PY="
py -3 -c "import sys" >nul 2>&1     && set "PY=py -3"      && exit /b 0
python  -c "import sys" >nul 2>&1   && set "PY=python"     && exit /b 0
python3 -c "import sys" >nul 2>&1   && set "PY=python3"    && exit /b 0
exit /b 0
