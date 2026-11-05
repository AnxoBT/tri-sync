@echo off
title Tri-Sync (cierra esta ventana para apagarlo)
cd /d "%~dp0"
echo Abriendo Tri-Sync en el navegador...
echo Cierra esta ventana cuando termines.
python sync.py
if errorlevel 1 pause
