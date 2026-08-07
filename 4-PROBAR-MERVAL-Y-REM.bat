@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Probar MERVAL y REM
cd /d "%~dp0"

echo =====================================================
echo  Prueba de las fuentes de MERVAL y REM
echo =====================================================
echo.
echo  Este archivo NO publica nada en GitHub. Solo actualiza
echo  los datos y regenera el tablero para que puedas verlos.
echo.

call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  pause
  exit /b 1
)
echo [OK] Python: %PY%
echo.

echo -----------------------------------------------------
echo  MERVAL  (prueba Yahoo, Rava y Stooq en ese orden)
echo -----------------------------------------------------
%PY% update_merval_cache.py
echo.

echo -----------------------------------------------------
echo  REM  (planilla oficial del BCRA)
echo -----------------------------------------------------
%PY% update_rem_cache.py
echo.

echo -----------------------------------------------------
echo  Regenerando el tablero con los datos nuevos
echo -----------------------------------------------------
%PY% build_publicar.py
echo.

echo =====================================================
echo  Listo. Abri tablero_elyon_portable.html para verlo.
echo  Si alguna fuente fallo, arriba figura el motivo.
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
