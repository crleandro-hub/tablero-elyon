@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Actualizar tablero publicado
cd /d "%~dp0"

echo =====================================================
echo  GRUPO ELYON - Actualizar el tablero publicado
echo =====================================================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git no esta instalado. Ejecuta primero 1-SUBIR-A-GITHUB.bat
  pause
  exit /b 1
)
if not exist ".git" (
  echo [ERROR] Todavia no publicaste por primera vez.
  echo         Ejecuta 1-SUBIR-A-GITHUB.bat
  pause
  exit /b 1
)

echo [1/4] Actualizando indice CAC...
python update_cac_cache.py
if errorlevel 1 echo [AVISO] Fallo update_cac_cache.py - se sigue con los datos actuales.

echo.
echo [2/4] Actualizando datos BCRA...
if exist "update_bcra_cache.py" (
  python update_bcra_cache.py
  if errorlevel 1 echo [AVISO] Fallo update_bcra_cache.py - se sigue con los datos actuales.
)

echo.
echo [3/4] Generando docs\index.html y version portable...
python build_publicar.py
if errorlevel 1 (
  echo [ERROR] Fallo build_publicar.py. Cancelado.
  pause
  exit /b 1
)

echo.
echo [4/4] Subiendo a GitHub...
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
echo =====================================================
echo.
pause
