@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Probar ICC del INDEC
cd /d "%~dp0"

echo =====================================================
echo  Prueba de la fuente: ICC del INDEC (Gran Buenos Aires)
echo =====================================================
echo.
echo  Baja el Excel de series del INDEC y arma icc_indec_cache.js.
echo  NO publica nada en GitHub: solo genera los datos y regenera
echo  el tablero para que puedas verlo.
echo.
echo  Todo lo que pase queda guardado en log_icc_indec.txt, asi que
echo  no hace falta que copies nada: alcanza con decirle a Claude
echo  que ya lo corriste y el lee el archivo.
echo.

set "LOG=%~dp0log_icc_indec.txt"
echo ===================================================== > "%LOG%"
echo  Prueba ICC INDEC - %date% %time% >> "%LOG%"
echo ===================================================== >> "%LOG%"

call :buscarpython
if not defined PY (
  echo [ERROR] No se encontro Python en esta PC.
  pause
  exit /b 1
)
echo [OK] Python: %PY%
echo Python usado: %PY% >> "%LOG%"
echo.

echo -----------------------------------------------------
echo  Dependencias (pandas y xlrd, que hacen falta para .xls)
echo -----------------------------------------------------
echo. >> "%LOG%"
echo --- DEPENDENCIAS --- >> "%LOG%"
%PY% -c "import sys,pandas;print('[OK] pandas',pandas.__version__,'|',sys.executable)" >> "%LOG%" 2>&1
%PY% -c "import xlrd;print('[OK] xlrd',xlrd.__version__)" >> "%LOG%" 2>&1
type "%LOG%" | findstr /C:"pandas" /C:"xlrd" /C:"Error" /C:"error"
echo.

echo -----------------------------------------------------
echo  ICC INDEC  (esto puede tardar unos segundos)
echo -----------------------------------------------------
echo. >> "%LOG%"
echo --- UPDATE_ICC_INDEC_CACHE --- >> "%LOG%"
%PY% update_icc_indec_cache.py >> "%LOG%" 2>&1
type "%LOG%"
echo.

if not exist "icc_indec_cache.js" (
  echo =====================================================
  echo  No se genero icc_indec_cache.js.
  echo  El detalle quedo en:  log_icc_indec.txt
  echo  Decile a Claude que ya lo corriste y el lo lee solo.
  echo =====================================================
  echo.
  pause
  exit /b 1
)

echo -----------------------------------------------------
echo  Regenerando el tablero con los datos nuevos
echo -----------------------------------------------------
echo. >> "%LOG%"
echo --- BUILD_PUBLICAR --- >> "%LOG%"
%PY% build_publicar.py >> "%LOG%" 2>&1
type "%LOG%" | findstr /C:"[OK]" /C:"[AVISO]" /C:"[ERROR]"
echo.

echo =====================================================
echo  Listo. Abri tablero_elyon_portable.html y fijate la
echo  seccion "Indice ICC INDEC", despues del ICC Cordoba.
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
