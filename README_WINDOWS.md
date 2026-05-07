# Briner en Windows

Briner organiza archivos por escaneo periodico. El modo recomendado es `interval`, porque no mantiene un watcher en tiempo real y consume menos recursos.

## 1. Instalar dependencias

Desde la raiz del proyecto:

```powershell
cd "C:\ruta\a\Files Sorter"
python -m venv briner_agent\.venv
briner_agent\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r briner_agent\requirements.txt
```

## 2. Configuracion inicial

Ejecuta:

```powershell
python briner_agent\main.py --setup
```

En la primera ejecucion Briner pedira:

- Carpeta a organizar, por ejemplo `C:\Users\tu_usuario\Downloads`.
- Intervalo de escaneo en segundos, minimo `10`, recomendado `3600` para revisar cada hora.
- Si `dry_run` queda activo.

La configuracion se guarda en `briner_agent\user_settings.json`. En ejecuciones siguientes no vuelve a preguntar.

## 3. Ejecutar en modo interval

Una sola pasada:

```powershell
python briner_agent\main.py --once
```

Servicio continuo por escaneo periodico:

```powershell
python briner_agent\main.py
```

Simulacion sin mover archivos:

```powershell
python briner_agent\main.py --dry-run
```

Metricas:

```powershell
python briner_agent\main.py --metrics
```

## 4. Modo realtime opcional

Edita `briner_agent\user_settings.json` o `briner_agent\config.yaml`:

```json
{
  "monitoring": {
    "mode": "realtime"
  }
}
```

El modo realtime usa `watchdog`. El modo predeterminado sigue siendo `interval`.

## 5. Generar EXE con PyInstaller

Recomendado `--onedir`, porque facilita editar `config.yaml` y conservar `db\schema.sql` junto al ejecutable:

```powershell
cd "C:\ruta\a\Files Sorter\briner_agent"
python -m PyInstaller --onedir --name Briner --add-data "config.yaml;." --add-data "db\schema.sql;db" main.py
```

El ejecutable quedara en:

```text
briner_agent\dist\Briner\Briner.exe
```

Antes de instalar autoarranque, ejecuta una vez:

```powershell
briner_agent\dist\Briner\Briner.exe --setup
```

## 6. Autoarranque al iniciar Windows

### Opcion A: Startup folder

Ejecuta:

```powershell
briner_agent\scripts\install_startup.bat
```

Tambien puedes pasar una ruta explicita:

```powershell
briner_agent\scripts\install_startup.bat "C:\ruta\a\Briner.exe"
```

Esto crea un acceso directo en la carpeta `shell:startup` del usuario actual.

### Opcion B: Task Scheduler recomendado

1. Abre Task Scheduler.
2. Create Task.
3. Trigger: `At log on`.
4. Marca `Delay task for: 30 seconds`.
5. Action: `Start a program`.
6. Program: ruta a `Briner.exe`.
7. Start in: carpeta donde esta `Briner.exe`, por ejemplo `...\dist\Briner`.

Task Scheduler es preferible si quieres retraso, reintentos o ejecucion aunque el inicio sea lento.
