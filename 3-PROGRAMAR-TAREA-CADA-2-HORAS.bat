@echo off
title GRUPO ELYON - Programar actualizacion cada 2 horas (11 a 17)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_programar_tarea.ps1"
