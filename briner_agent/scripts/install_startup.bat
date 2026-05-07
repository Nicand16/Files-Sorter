@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_EXE=%SCRIPT_DIR%..\dist\Briner\Briner.exe"

if "%~1"=="" (
    set "BRINER_EXE=%DEFAULT_EXE%"
) else (
    set "BRINER_EXE=%~1"
)

for %%I in ("%BRINER_EXE%") do set "BRINER_EXE=%%~fI"

if not exist "%BRINER_EXE%" (
    echo No se encontro Briner.exe en:
    echo   %BRINER_EXE%
    echo.
    echo Genera primero el exe con PyInstaller o pasa la ruta como argumento:
    echo   install_startup.bat "C:\ruta\a\Briner.exe"
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$startup=[Environment]::GetFolderPath('Startup');" ^
  "$shortcut=Join-Path $startup 'Briner.lnk';" ^
  "$shell=New-Object -ComObject WScript.Shell;" ^
  "$link=$shell.CreateShortcut($shortcut);" ^
  "$link.TargetPath='%BRINER_EXE%';" ^
  "$link.WorkingDirectory=Split-Path '%BRINER_EXE%';" ^
  "$link.Arguments='';" ^
  "$link.Save();" ^
  "Write-Host 'Acceso directo creado en:' $shortcut"

if errorlevel 1 (
    echo No se pudo crear el acceso directo de inicio.
    exit /b 1
)

echo Briner se ejecutara al iniciar sesion del usuario actual.
exit /b 0
