# Briner en Windows - Desarrollo y Build

Esta guia es para desarrollo local. Para usuarios finales usa `briner_v1.2.0.zip` y `Install.bat`.

## Entorno

```powershell
cd "C:\ruta\a\Files Sorter"
python -m venv briner_agent\.venv
briner_agent\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r briner_agent\requirements.txt
```

## Ejecutar Desde Codigo Fuente

```powershell
cd briner_agent
python main.py --setup
python main.py --once
python main.py
```

Comandos utiles:

```powershell
python main.py --metrics
python main.py --undo-last
python main.py --once --dry-run
```

## Tests

```powershell
cd briner_agent
python -m pytest tests/ -q
```

Resultado esperado para esta release:

```text
50 passed
```

## Build de Ejecutables

Desde `briner_agent`:

```powershell
python -m PyInstaller --clean --noconfirm Briner.spec
python -m PyInstaller --clean --noconfirm BrinerBackground.spec
python -m PyInstaller --clean --noconfirm BrinerMonitor.spec
```

Artefactos esperados:

```text
briner_agent\dist\Briner\Briner.exe
briner_agent\dist\BrinerBackground\BrinerBackground.exe
briner_agent\dist\BrinerMonitor\BrinerMonitor.exe
```

`Briner.exe` tiene consola para setup/diagnostico. `BrinerBackground.exe` corre sin consola. `BrinerMonitor.exe` es la UI para usuarios.

## Crear Release ZIP

Desde la raiz del repo:

```powershell
New-Item -ItemType Directory -Force release\briner_v1.2.0 | Out-Null
Copy-Item -Recurse -Force briner_agent\dist\Briner,briner_agent\dist\BrinerBackground,briner_agent\dist\BrinerMonitor release\briner_v1.2.0\
Copy-Item -Force Install.bat,README.md,README_WINDOWS.md,MANUAL_USO.md release\briner_v1.2.0\
Compress-Archive -Path "release\briner_v1.2.0\*" -DestinationPath "briner_v1.2.0.zip" -Force
```

Validacion minima:

```powershell
Test-Path .\briner_v1.2.0.zip
Test-Path .\briner_agent\dist\Briner\Briner.exe
Test-Path .\briner_agent\dist\BrinerBackground\BrinerBackground.exe
Test-Path .\briner_agent\dist\BrinerMonitor\BrinerMonitor.exe
tar -tf .\briner_v1.2.0.zip | Select-String "README.md|README_WINDOWS.md|MANUAL_USO.md|Install.bat"
```

## Notas de Runtime

- Configuracion del usuario: `%APPDATA%\Briner\user_settings.json`.
- API key: `%APPDATA%\Briner\.env`.
- Historial: `%APPDATA%\Briner\briner.db`.
- Logs: `%APPDATA%\Briner\logs\briner.log`.
- IPC Monitor/Tray/Background: `%APPDATA%\Briner\commands\*.json`.
- Escaneo inmediato legacy: `%APPDATA%\Briner\.force_scan`.

## Modo Realtime Opcional

El modo recomendado para usuarios finales es `interval`. Si necesitas realtime para pruebas, cambia `monitoring.mode` a `realtime` en config o settings.
