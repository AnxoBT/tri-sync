@echo off
title Tri-Sync (cierra esta ventana para apagarlo)
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo No encuentro Python. Instalalo desde https://www.python.org/downloads/
  echo  ^(marca "Add python.exe to PATH" al instalar^) y vuelve a abrir Tri-Sync.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

python -c "import tzdata" >nul 2>nul
if errorlevel 1 (
  echo Primera vez: instalando lo necesario...
  python -m pip install --quiet -r requirements.txt
)

rem Primera vez: crea el acceso directo "Tri-Sync" en el escritorio (con su icono)
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $l=Join-Path $d 'Tri-Sync.lnk'; if (-not (Test-Path $l)) { $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath='%~f0'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0web\logo.ico,0'; $s.Description='Revisar Dixmax, Letterboxd y Serializd'; $s.Save(); Write-Host 'Acceso directo Tri-Sync creado en el escritorio.' }"

echo Abriendo Tri-Sync en el navegador...
echo Cierra esta ventana cuando termines.
python sync.py
if errorlevel 1 pause
