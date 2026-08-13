@echo off
title GRUPO ELYON - Programar actualizacion cada hora (11 a 18)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_programar_tarea.ps1"
