@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Actualizar tablero publicado
cd /d "%~dp0"

set "LOG=%~dp0log_actualizar.txt"

echo =====================================================
echo  GRUPO ELYON - Actualizar el tablero publicado
echo =====================================================
echo.
echo  Todo queda registrado en log_actualizar.txt.
echo  Al final se muestra el detalle completo en pantalla.
echo.

echo ===================================================== > "%LOG%"
echo  Actualizacion manual - %date% %time% >> "%LOG%"
echo ===================================================== >> "%LOG%"

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
echo Python: %PY% >> "%LOG%"

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

rem =====================================================
rem  FUENTES DE DATOS
rem  Si una falla se conserva el cache anterior y se sigue:
rem  mejor un dato viejo que el tablero roto. verificar.py
rem  avisa despues si algo quedo atrasado.
rem =====================================================
call :paso  1 "BCRA (TAMAR / BADLAR / UVA)"          update_bcra_cache.py
call :paso  2 "Serie historica UVA"                  update_uva_cache.py
call :paso  3 "Indice CAC"                           update_cac_cache.py
call :paso  4 "MERVAL (pesos y dolares)"             update_merval_cache.py
call :paso  5 "REM del BCRA (inflacion esperada)"    update_rem_cache.py
call :paso  6 "Riesgo pais (Rava Bursatil)"          update_riesgo_cache.py
call :paso  7 "Caucion 1/7/14 dias (Rava Bursatil)"  update_caucion_cache.py
call :paso  8 "Dolar futuro (Matba Rofex)"           update_rofex_cache.py
call :paso  9 "Acciones del panel lider (BYMA)"      update_acciones_cache.py
call :paso 10 "Tipo de cambio (respaldo)"            update_dolar_cache.py
call :paso 11 "ISAC e insumos (INDEC)"               update_isac_cache.py
call :paso 12 "ICC de Cordoba"                       update_icc_cba_cache.py
call :paso 13 "Registro General de Cordoba"          update_rgp_cba_cache.py
call :paso 14 "ICC del INDEC (Gran Buenos Aires)"    update_icc_indec_cache.py
call :paso 15 "Indice Construya"                     update_construya_cache.py
call :paso 16 "Costo del m2 (APYMECO)"                update_apymeco_cache.py

rem =====================================================
rem  ARMADO
rem =====================================================
echo [17/19] Generando docs\index.html y version portable...
echo. >> "%LOG%"
echo --- [17/19] BUILD_PUBLICAR --- >> "%LOG%"
%PY% build_publicar.py >> "%LOG%" 2>&1
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo    [ERROR] Fallo build_publicar.py. Cancelado.
  goto :mostrarlog
)
echo    [ok]

rem =====================================================
rem  VERIFICACION
rem  0 = todo bien   1 = datos con problemas, no publicar
rem  2 = se cayo el verificador, es un bug suyo: se publica igual
rem =====================================================
echo [18/19] Verificando frescura e integridad de los datos...
echo. >> "%LOG%"
echo --- [18/19] VERIFICAR --- >> "%LOG%"
%PY% verificar.py >> "%LOG%" 2>&1
set "RC=%errorlevel%"
if "%RC%"=="1" (
  echo    [ERROR] La verificacion encontro problemas en los datos. NO se publica.
  goto :mostrarlog
)
if "%RC%"=="2" (
  echo    [AVISO] verificar.py no pudo completarse. Se publica igual.
) else (
  echo    [ok]
)

rem =====================================================
rem  PUBLICACION
rem =====================================================
echo [19/19] Publicando en GitHub Pages...
echo. >> "%LOG%"
echo --- [19/19] GIT --- >> "%LOG%"
git add -A >> "%LOG%" 2>&1
git commit -m "Actualizacion de indicadores %date%" >> "%LOG%" 2>&1
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo    [INFO] No hubo cambios en los datos. Nada para subir.
  goto :mostrarlog
)
git push >> "%LOG%" 2>&1
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo    [ERROR] Fallo el push. Revisa la conexion o las credenciales de git.
  goto :mostrarlog
)
echo    [ok] Publicado. El link se refresca en 1-2 minutos.

:mostrarlog
echo.
echo =====================================================
echo  DETALLE COMPLETO
echo =====================================================
type "%LOG%"
echo.
echo =====================================================
echo  Fin. El detalle quedo guardado en log_actualizar.txt
echo =====================================================
echo.
pause
exit /b 0


rem --- Corre un update y avisa, sin frenar el ciclo ---
:paso
echo [%~1/19] Actualizando %~2...
echo. >> "%LOG%"
echo --- [%~1/19] %~2 --- >> "%LOG%"
%PY% %~3 >> "%LOG%" 2>&1
if errorlevel 1 (
  echo    [AVISO] Fallo - se conservan los datos previos.
) else (
  echo    [ok]
)
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
