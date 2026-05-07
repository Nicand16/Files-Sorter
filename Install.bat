@echo off
setlocal

echo.
echo  =====================================================
echo    Briner - Instalador de organizador de archivos
echo  =====================================================
echo.

set "ROOT=%~dp0"
set "BRINER_EXE=%ROOT%briner_agent\dist\Briner\Briner.exe"
set "BRINER_BG_EXE=%ROOT%briner_agent\dist\BrinerBackground\BrinerBackground.exe"

if not exist "%BRINER_EXE%" (
    echo  ERROR: No se encontro Briner.exe en:
    echo    %BRINER_EXE%
    echo.
    echo  Asegurate de ejecutar este archivo desde la carpeta del proyecto.
    echo  Si descargaste el proyecto de GitHub, verifica que la carpeta
    echo  briner_agent\dist\Briner\ exista y tenga Briner.exe
    echo.
    pause
    exit /b 1
)

:: Verificar integridad minima del bundle
if not exist "%ROOT%briner_agent\dist\Briner\_internal\python314.dll" (
    echo  ERROR: Archivos internos faltantes (_internal\python314.dll).
    echo  La descarga parece incompleta. Descarga el repositorio de nuevo.
    pause
    exit /b 1
)
if not exist "%ROOT%briner_agent\dist\Briner\_internal\_socket.pyd" (
    echo  ERROR: Archivo _socket.pyd faltante.
    echo  La descarga parece incompleta. Descarga el repositorio de nuevo.
    pause
    exit /b 1
)

echo  Se abrira el asistente de configuracion...
echo  Solo necesitaras indicar la carpeta que deseas organizar.
echo.

:: Ejecutar el asistente de configuracion (se cierra solo al terminar)
"%BRINER_EXE%" --setup

if errorlevel 1 (
    echo.
    echo  Ocurrio un error durante la configuracion.
    pause
    exit /b 1
)

:: Iniciar BrinerBackground en segundo plano
if exist "%BRINER_BG_EXE%" (
    echo.
    echo  Iniciando Briner en segundo plano...
    start "" "%BRINER_BG_EXE%" --no-wizard
    echo  Briner esta corriendo. Revisara tu carpeta cada hora.
) else (
    echo.
    echo  Nota: BrinerBackground.exe no encontrado. Briner se iniciara
    echo  automaticamente en el proximo inicio de Windows.
)

echo.
echo  =====================================================
echo    Instalacion completada
echo  =====================================================
echo.
echo  - Briner organizara tu carpeta automaticamente cada hora.
echo  - Se ejecutara en segundo plano al iniciar Windows.
echo  - Para cambiar la carpeta, vuelve a ejecutar Install.bat.
echo  - Los logs se guardan en: %%APPDATA%%\Briner\logs\briner.log
echo.
pause
