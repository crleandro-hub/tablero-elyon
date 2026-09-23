@echo off
title GRUPO ELYON - Se puede automatizar el indice CIFRAS?
cd /d "%~dp0"
echo.
call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  pause
  exit /b 1
)
%PY% probar_cifras.py
echo.
pause
exit /b 0

:buscarpython
set "PY="
py -3 -c "import sys" >nul 2>&1     && set "PY=py -3"      && exit /b 0
python  -c "import sys" >nul 2>&1   && set "PY=python"     && exit /b 0
python3 -c "import sys" >nul 2>&1   && set "PY=python3"    && exit /b 0
exit /b 0
