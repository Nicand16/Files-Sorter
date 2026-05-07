# Briner - Organizador automático de archivos

Briner organiza automáticamente los archivos de una carpeta (por ejemplo, `Descargas`) moviéndolos a subcarpetas según su tipo. Se ejecuta en segundo plano al iniciar Windows y muestra su actividad desde el ícono de la bandeja del sistema.

## Uso para usuarios finales

1. Descarga o clona este repositorio.
2. Haz doble clic en **`Install.bat`**.
3. Selecciona la carpeta que deseas organizar en el diálogo que aparece.
4. Pega tu API key de Google Gemini cuando se te solicite (gratuita en [aistudio.google.com/apikey](https://aistudio.google.com/apikey)).
5. ¡Listo! Briner se ejecutará automáticamente cada vez que inicies Windows.

No se requiere instalar Python ni ninguna dependencia adicional.

## Bandeja del sistema

El ícono de Briner en la barra de tareas indica su estado con colores:

| Color | Significado |
|---|---|
| Verde | Corriendo normalmente |
| Azul | Procesando archivos |
| Rojo | Error activo |

El menú del ícono muestra:
- Estado general y contadores (pendientes, procesados, errores)
- **Últimas 5 acciones por archivo en tiempo real** (`[>]` movido, `[!]` error, `[*]` procesando, `[-]` ignorado)
- Acciones: Forzar escaneo, Ver logs, Abrir carpeta monitoreada, Detener

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

# Ver métricas (incluye latencia de arranque, LLM, caché y por fase)
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

---

## Para desarrolladores

### Arquitectura

Briner usa dos ejecutables que comparten el directorio `%APPDATA%\Briner`:

- **`Briner.exe`** — con consola; para setup inicial y comandos manuales (`--once`, `--dry-run`, `--metrics`, `--setup`).
- **`BrinerBackground.exe`** — sin consola; el servicio en segundo plano que arranca con Windows.

#### Pipeline de clasificación

```
Archivo detectado (watcher / scanner)
         │
    [EventBus: DETECTED]
         │
┌────────────────────┐
│  Fase 1: Reglas    │  ← sin API, instantáneo
│  (extensión /      │
│   palabra clave)   │
└────────┬───────────┘
         │ ¿ambiguo?
   Sí ───┘   No → MOVED / IGNORED
   │
┌──┴───────────────────────────┐
│  Caché de decisiones          │  ← LRU + TTL por (extensión, patrón)
│  (mismo patrón = sin LLM)    │
└──┬───────────────────────────┘
   │ miss → Fase 2
   │ hit  → MOVED (sin llamada a API)
   │
┌──┴───────────────────────────┐
│  Fase 2: LLM por lote        │  ← 1 llamada para N archivos
│  (CircuitBreaker protege)    │
└──┬───────────────────────────┘
   │ falla → Fase 3
   │
┌──┴───────────────────────────┐
│  Fase 3: Agente ReAct        │  ← por archivo, último recurso
└──────────────────────────────┘
```

#### Secuencia de arranque (objetivo: bandeja visible en < 2 s)

```
main() arranca → carga config + settings (sin llamadas a API)
      ↓
Bandeja del sistema aparece (ícono verde)
      ↓
DatabaseManager inicializa SQLite
      ↓
BrinerOrchestrator listo (LLM no inicializado todavía)
      ↓
Ciclo de procesamiento inicia → LLM se inicializa al primer archivo ambiguo
```

#### Estados del Circuit Breaker

```
CLOSED → (N fallos consecutivos) → OPEN → (recovery_seconds) → HALF_OPEN
                                                                    │
                                              éxito del probe → CLOSED
                                              fallo del probe → OPEN
```

Cuando el circuit está `OPEN`, las llamadas a Gemini se saltan y los archivos van a `7. Varios` sin esperar.

### Módulos principales

```
Files Sorter/
  Install.bat                         ← instalador para usuarios finales
  briner_agent/
    main.py                           ← punto de entrada y loops principal/intervalo
    config.yaml                       ← taxonomía y configuración base
    core/
      agent_orchestrator.py           ← pipeline 3 fases + circuit breaker + caché
      llm_engine.py                   ← inicialización de Gemini (lazy)
      settings_manager.py             ← configuración de usuario
    modules/
      file_watcher.py                 ← monitoreo en tiempo real (watchdog)
      periodic_scanner.py             ← escaneo por intervalo
      rules_engine.py                 ← clasificación determinista
      crud_executor.py                ← movimiento seguro de archivos
      tray_icon.py                    ← ícono de bandeja (pystray) + feed en vivo
      multimodal_parser.py            ← extracción de contenido PDF/DOCX/XLSX
      history.py                      ← deshacer último movimiento
    runtime/
      event_bus.py                    ← pub/sub de eventos por archivo (7 estados)
      circuit_breaker.py              ← CLOSED/OPEN/HALF_OPEN para proteger LLM
    classifiers/
      decision_cache.py               ← caché LRU+TTL de decisiones LLM
    infra/
      metrics.py                      ← timers y contadores en proceso (sin deps externas)
    db/
      database_manager.py             ← SQLite (archivos, acciones, eventos de clasificación)
      schema.sql
    tests/
      test_core.py                    ← reglas, movimientos, DB, configuración
      test_event_bus.py               ← pub/sub, estados, short_label
      test_circuit_breaker.py         ← transiciones CLOSED/OPEN/HALF_OPEN
      test_decision_cache.py          ← LRU, TTL, normalización de dígitos
    build_all.bat                     ← reconstruir ambos exes
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
# Primera vez (configura carpeta y API key)
python briner_agent\main.py --setup

# Modo continuo
python briner_agent\main.py

# Una sola pasada en seco
python briner_agent\main.py --once --dry-run

# Ver métricas de rendimiento
python briner_agent\main.py --metrics
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
# 41 tests; 1 fallo esperado en Windows (test de expanduser con home mock)
```

### Configuración avanzada (`config.yaml`)

Parámetros relevantes bajo `processing:`:

| Clave | Por defecto | Descripción |
|---|---|---|
| `llm_batch_size` | `50` | Archivos por llamada LLM |
| `llm_timeout_seconds` | `60` | Timeout por invocación |
| `circuit_breaker_threshold` | `3` | Fallos antes de abrir el circuit |
| `circuit_breaker_recovery_seconds` | `60` | Tiempo hasta probe de recuperación |
| `decision_cache_size` | `200` | Entradas máximas en caché |
| `decision_cache_ttl_seconds` | `3600` | Tiempo de vida de cada entrada |
