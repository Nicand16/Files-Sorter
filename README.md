# Briner - Organizador automático de archivos

Briner organiza automáticamente los archivos de una carpeta (por ejemplo, `Descargas`) cada hora, moviéndolos a subcarpetas según su tipo. Se ejecuta en segundo plano al iniciar Windows.

## Uso para usuarios finales

1. Descarga o clona este repositorio.
2. Haz doble clic en **`Install.bat`**.
3. Selecciona la carpeta que deseas organizar en el diálogo que aparece.
4. Pega tu API key de Google Gemini cuando se te solicite (gratuita en [aistudio.google.com/apikey](https://aistudio.google.com/apikey)).
5. ¡Listo! Briner se ejecutará automáticamente cada vez que inicies Windows.

No se requiere instalar Python ni ninguna dependencia adicional.

## Carpetas de destino

Los archivos se organizan en estas subcarpetas dentro de la carpeta elegida:

| Carpeta | Contenido |
|---|---|
| `1. Universidad y Estudio` | Tareas, libros, materiales académicos |
| `2. Software y Herramientas` | Instaladores, comprimidos |
| `3. Juegos y Emulación` | ROMs, ISOs, torrents de juegos |
| `4. Multimedia` | Imágenes, videos, audio |
| `5. Trabajo y Empleo` | CVs, contratos, ofertas laborales |
| `6. Documentos Personales` | Cédula, facturas, certificados |
| `7. Varios` | Todo lo que no encaja en otra categoría |

## Clasificación con IA

La API key de Gemini se configura automáticamente durante la instalación. Briner la guarda en `%APPDATA%\Briner\.env`.

Si necesitas cambiarla manualmente, edita ese archivo:

```text
GOOGLE_API_KEY=tu_nueva_api_key
```

Sin API key, Briner funciona usando solo reglas locales por extensión y palabras clave (archivos ambiguos van a `7. Varios`).

## Comandos útiles (con consola)

```powershell
# Verificar que está corriendo
Get-Process BrinerBackground -ErrorAction SilentlyContinue

# Detener temporalmente
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process

# Ejecutar una pasada manual y ver resultados en consola
cd briner_agent\dist\Briner
.\Briner.exe --once

# Simular sin mover archivos
.\Briner.exe --once --dry-run

# Ver métricas
.\Briner.exe --metrics

# Reconfigurar carpeta y API key (o vuelve a ejecutar Install.bat)
.\Briner.exe --setup --watch-dir "C:\nueva\carpeta" --api-key "tu_key"
```

## Logs

```text
%APPDATA%\Briner\logs\briner.log
```

```powershell
Get-Content "$env:APPDATA\Briner\logs\briner.log" -Tail 40
```

## Cambiar la carpeta monitoreada

Vuelve a ejecutar `Install.bat` o edita:

```text
%APPDATA%\Briner\user_settings.json
```

## Para desarrolladores

### Estructura del proyecto

```
Files Sorter/
  Install.bat                    ← instalador para usuarios finales
  briner_agent/
    main.py                      ← punto de entrada
    config.yaml                  ← taxonomía y configuración base
    core/
      settings_manager.py        ← manejo de configuración de usuario
      agent_orchestrator.py      ← orquestador principal
      llm_engine.py              ← motor Gemini (opcional)
    modules/
      periodic_scanner.py        ← escaneo por intervalo
      rules_engine.py            ← clasificación por reglas
      crud_executor.py           ← movimiento de archivos
    db/
      database_manager.py        ← SQLite
      schema.sql
    dist/
      Briner/                    ← exe con consola (setup/debug)
      BrinerBackground/          ← exe sin consola (servicio en fondo)
    build_all.bat                ← reconstruir ambos exes
```

### Instalar dependencias

```powershell
cd briner_agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Ejecutar desde código fuente

```powershell
python briner_agent\main.py --setup
python briner_agent\main.py
```

### Reconstruir los ejecutables

```powershell
briner_agent\build_all.bat
```

O manualmente:

```powershell
cd briner_agent
python -m PyInstaller --clean --noconfirm Briner.spec
python -m PyInstaller --clean --noconfirm BrinerBackground.spec
```

### Pruebas

```powershell
cd briner_agent
python -m pytest -q
```
