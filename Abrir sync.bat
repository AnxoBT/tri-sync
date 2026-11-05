@echo off
title seriesypelis-sync (cierra esta ventana para apagarlo)
cd /d "%~dp0"
echo Abriendo seriesypelis-sync en el navegador...
echo Cierra esta ventana cuando termines.
python sync.py
if errorlevel 1 pause
