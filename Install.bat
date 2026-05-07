@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

echo.
echo  =====================================================
echo    Briner - Instalador de organizador de archivos
echo  =====================================================
echo.

set "ROOT=%~dp0"
set "BRINER_EXE=%ROOT%briner_agent\dist\Briner\Briner.exe"
set "BRINER_BG_EXE=%ROOT%briner_agent\dist\BrinerBackground\BrinerBackground.exe"
set "BRINER_MON_EXE=%ROOT%briner_agent\dist\BrinerMonitor\BrinerMonitor.exe"

:: --- Verificar archivos necesarios ---
if not exist "%BRINER_EXE%" (
    echo  ERROR: No se encontro Briner.exe en:
    echo    %BRINER_EXE%
    echo.
    echo  Asegurate de ejecutar este archivo desde la carpeta del proyecto.
    echo  Si descargaste el proyecto de GitHub, verifica que exista:
    echo    briner_agent\dist\Briner\Briner.exe
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%briner_agent\dist\Briner\_internal\python314.dll" (
    echo  ERROR: Archivos internos faltantes ^(_internal\python314.dll^).
    echo  La descarga parece incompleta. Descarga el repositorio de nuevo.
    echo.
    pause
    exit /b 1
)

if not exist "%ROOT%briner_agent\dist\Briner\_internal\_socket.pyd" (
    echo  ERROR: Archivo _socket.pyd faltante.
    echo  La descarga parece incompleta. Descarga el repositorio de nuevo.
    echo.
    pause
    exit /b 1
)

:: --- Seleccion de carpeta ---
echo  Selecciona la carpeta que deseas que Briner organice.
echo  ^(Abriendo dialogo de seleccion -- puede tardar unos segundos^)
echo.

set "WATCH_DIR="
set "PS_TMP=%TEMP%\briner_picker_%RANDOM%.ps1"

:: Escribir script PS a fichero temporal para evitar problemas de escape
(
    echo Add-Type -AssemblyName System.Windows.Forms
    echo [System.Windows.Forms.Application]::EnableVisualStyles^(^)
    echo $anchor = New-Object System.Windows.Forms.Form
    echo $anchor.TopMost = $true
    echo $anchor.WindowState = 'Minimized'
    echo $anchor.ShowInTaskbar = $false
    echo $anchor.Show^(^)
    echo $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    echo $dlg.Description = 'Selecciona la carpeta que Briner organizara automaticamente'
    echo $dlg.ShowNewFolderButton = $true
    echo if ^($dlg.ShowDialog^($anchor^) -eq 'OK'^) ^{ Write-Output $dlg.SelectedPath ^}
    echo $anchor.Dispose^(^)
) > "%PS_TMP%"

for /f "usebackq delims=" %%F in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_TMP%"`) do (
    set "WATCH_DIR=%%F"
)
del "%PS_TMP%" >nul 2>&1

:: Si el dialogo fallo o fue cancelado, pedir ruta por texto
if "!WATCH_DIR!"=="" (
    echo  No se selecciono carpeta en el dialogo.
    echo  Escribe la ruta de la carpeta directamente:
    echo.
    set /p "WATCH_DIR=  Carpeta ^(ej: C:\Users\tu_usuario\Downloads^): "
    set "WATCH_DIR=!WATCH_DIR:"=!"
)

if "!WATCH_DIR!"=="" (
    echo.
    echo  No se indico ninguna carpeta. Instalacion cancelada.
    echo.
    pause
    exit /b 1
)

echo.
echo  Carpeta seleccionada: !WATCH_DIR!
echo.

:: --- API key de Gemini ---
echo  Necesitas una API key de Google Gemini ^(gratuita^).
echo  Obtenla en: https://aistudio.google.com/apikey
echo.
set /p "GEMINI_KEY=  Pega tu API key aqui: "
set "GEMINI_KEY=!GEMINI_KEY: =!"

if "!GEMINI_KEY!"=="" (
    echo.
    echo  No se ingreso ninguna API key. Instalacion cancelada.
    echo.
    pause
    exit /b 1
)
echo.

:: --- Guardar API key en APPDATA\Briner\.env ---
if not exist "%APPDATA%\Briner" mkdir "%APPDATA%\Briner"
echo GOOGLE_API_KEY=!GEMINI_KEY!> "%APPDATA%\Briner\.env"

:: --- Configurar Briner ---
echo  Configurando Briner...
"%BRINER_EXE%" --setup --watch-dir "!WATCH_DIR!"
set "SETUP_ERR=!ERRORLEVEL!"

if !SETUP_ERR! neq 0 (
    echo.
    echo  ERROR ^(!SETUP_ERR!^) al configurar Briner.
    echo  Revisa los logs en: %APPDATA%\Briner\logs\briner.log
    echo.
    pause
    exit /b 1
)

:: --- Iniciar en segundo plano ---
if exist "%BRINER_BG_EXE%" (
    echo.
    echo  Iniciando Briner en segundo plano...
    start "" "%BRINER_BG_EXE%" --no-wizard
    echo  Briner esta corriendo. Revisara tu carpeta cada hora.
) else (
    echo.
    echo  Nota: BrinerBackground.exe no encontrado junto a Briner.exe.
    echo  Briner se iniciara automaticamente en el proximo inicio de Windows.
)

:: --- Acceso directo al monitor en el Escritorio ---
if exist "%BRINER_MON_EXE%" (
    set "MON_EXE_STR=!BRINER_MON_EXE!"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$desktop = [Environment]::GetFolderPath('Desktop'); ^
         $lnk = Join-Path $desktop 'Briner Monitor.lnk'; ^
         $shell = New-Object -ComObject WScript.Shell; ^
         $link = $shell.CreateShortcut($lnk); ^
         $link.TargetPath = '!MON_EXE_STR!'; ^
         $link.Description = 'Ver actividad de Briner en tiempo real'; ^
         $link.Save()"
    echo.
    echo  Acceso directo "Briner Monitor" creado en el Escritorio.
)

echo.
echo  =====================================================
echo    Instalacion completada
echo  =====================================================
echo.
echo  Carpeta monitoreada : !WATCH_DIR!
echo  Frecuencia          : cada hora
echo  Inicio automatico   : al arrancar Windows
echo  Logs                : %APPDATA%\Briner\logs\briner.log
echo  Monitor             : "Briner Monitor" en el Escritorio
echo.
pause
