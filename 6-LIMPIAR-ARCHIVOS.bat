@echo off
setlocal
chcp 65001 >nul
title GRUPO ELYON - Limpieza de archivos
cd /d "%~dp0"

echo =====================================================
echo  Limpieza de archivos que ya no se usan
echo =====================================================
echo.
echo  Esto NO toca ningun dato del tablero. Solo borra
echo  archivos que quedaron sin funcion:
echo.
echo   - PUBLICAR.txt          reemplazado por FUENTES.md
echo   - log_icc_indec.txt     log de una prueba puntual
echo   - icc_indec_manual.json obsoleto (por si quedo)
echo   - __pycache__           cache de Python, se regenera
echo.
echo  Y saca los logs del repositorio de GitHub, para que
echo  dejen de subirse en cada corrida.
echo.
echo  Al final este mismo archivo se borra solo: ya cumplio
echo  su funcion y no hace falta volver a correrlo.
echo.
pause
echo.

echo [1/3] Sacando archivos del repositorio...
git rm --cached PUBLICAR.txt            >nul 2>&1
git rm --cached log_actualizar.txt      >nul 2>&1
git rm --cached log_icc_indec.txt       >nul 2>&1
git rm --cached icc_indec_manual.json   >nul 2>&1
git rm --cached 6-LIMPIAR-ARCHIVOS.bat  >nul 2>&1
echo    [ok]

echo [2/3] Borrando archivos del disco...
call :borrar "PUBLICAR.txt"
call :borrar "log_icc_indec.txt"
call :borrar "icc_indec_manual.json"
if exist "__pycache__" (
  rmdir /s /q "__pycache__"
  echo    [ok] __pycache__
)

echo [3/3] Publicando la limpieza...
git add -A >nul 2>&1
git commit -m "Limpieza: se unifica la documentacion en FUENTES.md" >nul 2>&1
if errorlevel 1 (
  echo    [INFO] No habia nada para limpiar.
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
echo  Terminado. Toda la documentacion quedo en FUENTES.md
echo =====================================================
echo.
pause

rem  El .bat se borra a si mismo: se lanza un proceso aparte que espera
rem  un segundo a que este termine y recien ahi elimina el archivo.
start "" /b cmd /c "timeout /t 1 >nul & del /f /q ""%~f0"""
exit /b 0


:borrar
if exist %1 (
  del /f /q %1
  echo    [ok] %~1
) else (
  echo    [--] %~1 ya no estaba
)
exit /b 0
