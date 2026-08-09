@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Limpieza de archivos
cd /d "%~dp0"

echo =====================================================
echo  Limpieza de archivos que no hacen falta
echo =====================================================
echo.
echo  Esto NO toca ningun dato del tablero. Solo:
echo.
echo   1. Saca los archivos de log del repositorio de GitHub
echo      (se siguen generando en tu PC, pero dejan de subirse)
echo   2. Borra icc_indec_manual.json, que quedo obsoleto
echo   3. Borra la carpeta __pycache__, que se regenera sola
echo.
echo  Se ejecuta UNA sola vez. Si lo corres de nuevo no pasa nada.
echo.
pause
echo.

rem --- 1) Destrackear los logs, sin borrarlos del disco ---
echo [1/4] Sacando los logs del repositorio...
git rm --cached log_actualizar.txt  >nul 2>&1
git rm --cached log_icc_indec.txt   >nul 2>&1
git rm --cached icc_indec_manual.json >nul 2>&1
echo    [ok]

rem --- 2) Borrar el JSON obsoleto ---
echo [2/4] Borrando archivos obsoletos...
if exist "icc_indec_manual.json" (
  del /f /q "icc_indec_manual.json"
  echo    [ok] icc_indec_manual.json borrado
) else (
  echo    [ok] icc_indec_manual.json ya no estaba
)

rem --- 3) Borrar el cache de Python ---
echo [3/4] Borrando __pycache__...
if exist "__pycache__" (
  rmdir /s /q "__pycache__"
  echo    [ok] __pycache__ borrado
) else (
  echo    [ok] __pycache__ ya no estaba
)

rem --- 4) Registrar el cambio en GitHub ---
echo [4/4] Publicando la limpieza...
git add -A >nul 2>&1
git commit -m "Limpieza: se sacan logs y archivos obsoletos del repositorio" >nul 2>&1
if errorlevel 1 (
  echo    [INFO] No habia nada para limpiar. Ya estaba todo en orden.
) else (
  git push >nul 2>&1
  if errorlevel 1 (
    echo    [AVISO] No se pudo hacer push. Revisa la conexion.
  ) else (
    echo    [ok] Listo y publicado.
  )
)

echo.
echo =====================================================
echo  Terminado. Podes cerrar esta ventana.
echo =====================================================
echo.
pause
exit /b 0
