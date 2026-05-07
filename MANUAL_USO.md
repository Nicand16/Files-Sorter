# Manual de uso de Briner

Briner es una aplicacion para organizar automaticamente archivos nuevos que llegan a una carpeta, normalmente `Descargas`. La configuracion actual esta pensada para Windows y para ejecutarse en segundo plano al iniciar sesion.

## Estado actual recomendado

La instalacion actual queda preparada asi:

- Carpeta organizada: `C:\Users\tu_usuario\Downloads`
- Modo de monitoreo: `interval`
- Frecuencia de escaneo: cada 1 hora (`3600` segundos)
- Ejecucion en segundo plano: `BrinerBackground.exe`
- Autoarranque: acceso directo en la carpeta Startup del usuario
- IA: Gemini mediante variable `GOOGLE_API_KEY` o `GEMINI_API_KEY` en `.env`

## Como funciona

Briner no vigila la carpeta en tiempo real por defecto. En vez de eso, despierta cada cierto intervalo, revisa los archivos nuevos que estan directamente dentro de la carpeta configurada y los mueve a la categoria correspondiente.

Por defecto no escanea dentro de las carpetas de destino. Esto evita que vuelva a procesar archivos que ya fueron organizados.

Las carpetas de destino actuales son:

- `1. Universidad y Estudio`
- `2. Software y Herramientas`
- `3. Juegos y Emulacion`
- `4. Multimedia`
- `5. Trabajo y Empleo`
- `6. Documentos Personales`
- `7. Varios`

Los archivos ambiguos se clasifican con IA cuando la API key esta disponible. Si no hay IA, Briner usa reglas locales y envia lo que no pueda decidir a `7. Varios`.

## Uso normal

No necesitas abrir nada manualmente para el uso diario. Al iniciar Windows, Briner se ejecuta en segundo plano y revisa `Descargas` cada hora.

Para comprobar que esta corriendo:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue
```

Para detenerlo temporalmente:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process
```

Se volvera a abrir automaticamente la proxima vez que inicies sesion en Windows.

## Ejecutar manualmente con ventana

Si quieres ver los mensajes en consola para diagnostico, usa el ejecutable con ventana:

```powershell
cd "C:\ruta\a\Files Sorter\briner_agent\dist\Briner"
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

## Cambiar la carpeta organizada o el intervalo

La configuracion del ejecutable esta en:

```text
C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\user_settings.json
```

Para revisar cada hora, debe tener:

```json
{
  "monitoring": {
    "workspace_dir": "C:\\Users\\tu_usuario\\Downloads",
    "mode": "interval",
    "poll_interval": 3600,
    "dry_run": false,
    "recursive": false
  }
}
```

`poll_interval` esta en segundos:

- `3600`: cada hora
- `1800`: cada 30 minutos
- `7200`: cada 2 horas

No se recomienda usar intervalos muy bajos. El minimo aceptado por la app es `10`, pero para uso diario conviene `3600`.

Despues de editar el archivo, reinicia Briner:

```powershell
Get-Process BrinerBackground -ErrorAction SilentlyContinue | Stop-Process
Start-Process "C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\BrinerBackground.exe"
```

## Configurar o actualizar la API key de IA

El archivo `.env` debe estar junto al ejecutable:

```text
C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\.env
```

Formato correcto:

```text
GOOGLE_API_KEY=tu_api_key_aqui
```

Tambien se acepta:

```text
GEMINI_API_KEY=tu_api_key_aqui
```

No pongas comillas ni espacios antes o despues del signo `=`.

Despues de cambiar la API key, reinicia BrinerBackground para que lea el nuevo valor.

## Ver logs

Los logs del ejecutable de fondo estan en:

```text
C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\logs\briner.log
```

Para ver las ultimas lineas:

```powershell
Get-Content "C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\logs\briner.log" -Tail 40
```

Mensajes esperados al iniciar correctamente:

```text
Modo activo: interval
Carpeta monitoreada: C:\Users\tu_usuario\Downloads
Intervalo efectivo: 3600 segundo(s)
Credenciales IA cargadas desde .env junto a Briner.exe.
Motor LLM inicializado exitosamente
```

## Autoarranque

Briner se inicia mediante este acceso directo:

```text
C:\Users\tu_usuario\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\Briner File Organizer.lnk
```

Debe apuntar a:

```text
C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\BrinerBackground.exe
```

Si quieres quitar el autoarranque, elimina ese acceso directo.

## Modo realtime opcional

El modo recomendado es `interval`. Solo usa `realtime` si necesitas reaccion instantanea ante cada archivo nuevo.

Para activarlo, cambia `mode` en `user_settings.json`:

```json
{
  "monitoring": {
    "mode": "realtime"
  }
}
```

Luego reinicia Briner. En este modo se usa `watchdog`, por lo que el proceso mantiene vigilancia continua de la carpeta.

## Reglas importantes de uso

- Coloca o descarga archivos directamente en `C:\Users\tu_usuario\Downloads`.
- No pongas archivos nuevos dentro de las carpetas numeradas si quieres que Briner los clasifique.
- Las carpetas numeradas son destinos, no entradas de procesamiento.
- Si un archivo no puede clasificarse con seguridad, puede terminar en `7. Varios`.
- Si `dry_run` esta en `true`, Briner no movera archivos; solo simulara.

## Solucion de problemas

### No mueve archivos

Revisa si hay archivos directamente dentro de `Downloads`. Briner no escanea las carpetas numeradas cuando `recursive` esta en `false`.

Tambien revisa que `dry_run` sea `false`.

### Dice que falta la API key

Verifica que exista este archivo:

```text
C:\ruta\a\Files Sorter\briner_agent\dist\BrinerBackground\.env
```

Y que tenga el formato:

```text
GOOGLE_API_KEY=tu_api_key_aqui
```

Luego reinicia el proceso.

### Quiero probar sin afectar mis archivos

Usa:

```powershell
cd "C:\ruta\a\Files Sorter\briner_agent\dist\Briner"
.\Briner.exe --once --dry-run
```

### Quiero forzar una organizacion ahora mismo

Usa:

```powershell
cd "C:\ruta\a\Files Sorter\briner_agent\dist\Briner"
.\Briner.exe --once
```

### Quiero revisar metricas

Usa:

```powershell
cd "C:\ruta\a\Files Sorter\briner_agent\dist\Briner"
.\Briner.exe --metrics
```

## Archivos principales

- Manual de uso: `MANUAL_USO.md`
- Guia Windows y empaquetado: `README_WINDOWS.md`
- Codigo fuente: `briner_agent`
- Configuracion base: `briner_agent\config.yaml`
- Configuracion del ejecutable de fondo: `briner_agent\dist\BrinerBackground\user_settings.json`
- Ejecutable con consola: `briner_agent\dist\Briner\Briner.exe`
- Ejecutable de fondo: `briner_agent\dist\BrinerBackground\BrinerBackground.exe`
- Logs de fondo: `briner_agent\dist\BrinerBackground\logs\briner.log`
