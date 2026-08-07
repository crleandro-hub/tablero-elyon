@echo off
title GRUPO ELYON - Programar actualizacion diaria
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_programar_tarea.ps1"
