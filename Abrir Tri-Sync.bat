@echo off
title Tri-Sync
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

rem Python sin consola (pythonw) para abrir Tri-Sync sin la ventana negra
for /f "delims=" %%P in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%P"

rem Acceso directo "Tri-Sync" en el escritorio (se crea o actualiza): abre la web sin ventana negra
powershell -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Tri-Sync.lnk'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath=$env:PYW; $s.Arguments='\"%~dp0sync.py\"'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0web\logo.ico,0'; $s.Description='Revisar Dixmax, Letterboxd y Serializd'; $s.Save()"

start "" "%PYW%" sync.py
exit /b 0
