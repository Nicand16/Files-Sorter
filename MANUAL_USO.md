# Manual de uso de Briner

Briner organiza automáticamente los archivos de tu carpeta de Descargas (o cualquier carpeta que elijas). Se ejecuta silenciosamente en segundo plano y revisa la carpeta cada hora.

## Instalación (primera vez)

1. Descarga el proyecto de GitHub.
2. Haz doble clic en **`Install.bat`**.
3. Selecciona la carpeta que deseas organizar en el diálogo que aparece.
4. Pega tu API key de Google Gemini cuando se te solicite (gratuita en [aistudio.google.com/apikey](https://aistudio.google.com/apikey)).
5. ¡Listo! Briner se ejecutará automáticamente al iniciar Windows.

## Carpetas de destino

Briner crea estas subcarpetas dentro de la carpeta que elegiste:

- `1. Universidad y Estudio`
- `2. Software y Herramientas`
- `3. Juegos y Emulacion`
- `4. Multimedia`
- `5. Trabajo y Empleo`
- `6. Documentos Personales`
- `7. Varios`

## Cómo funciona

Briner escanea la carpeta cada hora (modo `interval`). Solo procesa archivos directamente dentro de la carpeta raíz, nunca dentro de las subcarpetas numeradas. Si un archivo ya fue organizado no lo vuelve a mover.

Los archivos se clasifican primero por extensión y palabras clave en el nombre. Si la clasificación es ambigua y hay una API key configurada, se usa Gemini (IA). De lo contrario, el archivo va a `7. Varios`.

## Uso normal

No necesitas hacer nada. Al iniciar Windows, Briner arranca en segundo plano y revisa tu carpeta cada hora.

Para verificar que está corriendo:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue
```

Para detenerlo temporalmente:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process
```

Se volverá a iniciar automáticamente la próxima vez que abras Windows.

## Diagnóstico con consola

Para ver los mensajes en tiempo real mientras Briner trabaja:

```powershell
cd briner_agent\dist\Briner
.\Briner.exe
```

Para hacer una sola pasada y salir:

```powershell
.\Briner.exe --once
```

Para simular sin mover archivos:

```powershell
.\Briner.exe --once --dry-run
```

Para ver métricas:

```powershell
.\Briner.exe --metrics
```

## Cambiar la carpeta monitoreada

La forma más sencilla es volver a ejecutar `Install.bat` — pedirá la nueva carpeta y confirmará la API key.

También puedes hacerlo directamente:

```powershell
briner_agent\dist\Briner\Briner.exe --setup --watch-dir "C:\nueva\carpeta" --api-key "tu_key"
```

Los cambios se aplican de inmediato.

## Archivos de configuración

Todos los archivos de estado se guardan en:

```text
%APPDATA%\Briner\
  user_settings.json     ← carpeta y configuración
  briner.db              ← base de datos de historial
  logs\
    briner.log           ← registro de actividad
```

Para cambiar la carpeta manualmente edita `user_settings.json`:

```json
{
  "monitoring": {
    "workspace_dir": "C:\\Users\\tu_usuario\\Downloads",
    "mode": "interval",
    "poll_interval": 3600,
    "dry_run": false
  }
}
```

`poll_interval` es en segundos (`3600` = cada hora, `1800` = cada 30 min).

Después de editar, reinicia Briner:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process
Start-Process "briner_agent\dist\BrinerBackground\BrinerBackground.exe" -ArgumentList "--no-wizard"
```

## Clasificación con IA

La API key de Gemini se configura automáticamente durante la instalación y se guarda en:

```text
%APPDATA%\Briner\.env
```

Si necesitas cambiarla, edita ese archivo:

```text
GOOGLE_API_KEY=tu_nueva_api_key
```

Sin comillas ni espacios alrededor del `=`. Reinicia BrinerBackground para que tome efecto:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process
Start-Process "briner_agent\dist\BrinerBackground\BrinerBackground.exe" -ArgumentList "--no-wizard"
```

Sin API key, los archivos ambiguos se mueven a `7. Varios`.

## Ver logs

```powershell
Get-Content "$env:APPDATA\Briner\logs\briner.log" -Tail 40
```

Mensajes esperados al iniciar correctamente:

```text
Iniciando Briner - Agente Autonomo de Gestion de Archivos
Modo activo: interval
Carpeta monitoreada: C:\Users\tu_usuario\Downloads
Intervalo efectivo: 3600 segundo(s)
```

## Autoarranque

El inicio automático se instala durante la configuración inicial. El acceso directo se encuentra en:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Briner.lnk
```

Para quitar el autoarranque, elimina ese acceso directo.

Para reinstalarlo manualmente:

```powershell
briner_agent\scripts\install_startup.bat
```

## Reglas de uso

- Coloca los archivos directamente en la carpeta raíz configurada.
- No pongas archivos nuevos dentro de las carpetas numeradas.
- Si `dry_run` está en `true`, Briner no mueve archivos, solo simula.

## Solución de problemas

### No mueve archivos

Verifica que haya archivos directamente dentro de tu carpeta (no en subcarpetas numeradas) y que `dry_run` sea `false` en `user_settings.json`.

### Dice que falta la API key

Es normal. Briner funciona sin API key usando solo reglas locales. Si quieres IA, crea `%APPDATA%\Briner\.env` con tu `GOOGLE_API_KEY`.

### Quiero probar sin afectar mis archivos

```powershell
briner_agent\dist\Briner\Briner.exe --once --dry-run
```

### Quiero forzar una organización ahora mismo

```powershell
briner_agent\dist\Briner\Briner.exe --once
```
