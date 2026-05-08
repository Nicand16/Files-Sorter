# Briner — Arquitectura y guía técnica

Este documento describe en detalle la lógica, estructura y decisiones de diseño de Briner. Está pensado como referencia completa para que un desarrollador o un LLM pueda entender qué hace cada parte del sistema y cómo modificarla.

---

## Qué hace Briner

Briner es un agente autónomo de organización de archivos para Windows. Monitorea una carpeta configurada por el usuario (típicamente Descargas), clasifica cada archivo nuevo mediante reglas deterministas y/o IA (Google Gemini), y lo mueve a una subcarpeta de destino según su tipo. Se ejecuta en segundo plano, arranca con Windows, y expone su estado mediante un ícono en la bandeja del sistema y una ventana de monitoreo.

---

## Componentes del sistema

El sistema se distribuye como tres ejecutables independientes que comparten un directorio de datos en `%APPDATA%\Briner\`:

### `Briner.exe` — Consola de configuración y diagnóstico
- Tiene consola visible (stdout/stderr).
- Se usa para: configuración inicial (`--setup`), pasadas manuales (`--once`), diagnóstico (`--metrics`), deshacer último movimiento (`--undo-last`).
- Comparte exactamente el mismo código fuente (`main.py`) que BrinerBackground; la diferencia es solo `console=True` en el spec de PyInstaller.

### `BrinerBackground.exe` — Servicio en segundo plano
- Sin consola visible (`console=False`).
- Se lanza con `--no-wizard` para evitar el wizard interactivo.
- Es el proceso que realmente organiza los archivos de forma continua.
- Arranca con Windows mediante un acceso directo en `Startup`.
- Corre el ícono de la bandeja del sistema en el hilo principal (requisito de Win32) y el loop de procesamiento en un hilo daemon.

### `BrinerMonitor.exe` — Ventana de monitoreo
- Sin consola visible; interfaz gráfica Tkinter + pystray.
- Lee la base de datos SQLite compartida en modo solo lectura.
- Muestra los últimos 100 eventos de clasificación, contadores y estado.
- Se comunica con BrinerBackground mediante un archivo centinela (`.force_scan`) para forzar escaneos.
- Minimizar oculta la ventana a la bandeja del sistema (no a la barra de tareas).
- Código fuente: `briner_agent/monitor.py` (archivo independiente, no comparte código con `main.py`).

---

## Árbol de archivos

```
Files Sorter/
├── Install.bat                          ← Instalador de usuario final
├── MANUAL_USO.md                        ← Manual de usuario
├── ARCHITECTURE.md                      ← Este archivo
├── README.md                            ← Resumen del proyecto
└── briner_agent/
    ├── main.py                          ← Punto de entrada único (Briner.exe y BrinerBackground.exe)
    ├── monitor.py                       ← Punto de entrada de BrinerMonitor.exe
    ├── config.yaml                      ← Configuración base + taxonomía (se empaqueta en el exe)
    ├── requirements.txt
    ├── build_all.bat                    ← Compila los 3 exes con PyInstaller
    ├── Briner.spec                      ← Spec PyInstaller para Briner.exe (console=True)
    ├── BrinerBackground.spec            ← Spec PyInstaller para BrinerBackground.exe (console=False)
    ├── BrinerMonitor.spec               ← Spec PyInstaller para BrinerMonitor.exe (console=False)
    ├── rthook_fix_socket.py             ← Runtime hook para socket en exes frozen
    ├── core/
    │   ├── agent_orchestrator.py        ← Pipeline de clasificación 3 fases + circuit breaker
    │   ├── llm_engine.py                ← Inicialización lazy de Gemini via LangChain
    │   └── settings_manager.py          ← Carga y merge de config.yaml + user_settings.json
    ├── modules/
    │   ├── periodic_scanner.py          ← scan_directory_once(): rglob + registro en DB
    │   ├── file_watcher.py              ← Monitoreo en tiempo real con watchdog (modo realtime)
    │   ├── rules_engine.py              ← Clasificación determinista por extensión y keyword
    │   ├── crud_executor.py             ← Movimiento seguro de archivos (resolve colisiones)
    │   ├── tray_icon.py                 ← Ícono de bandeja (pystray) + "Cambiar API key"
    │   ├── multimodal_parser.py         ← Extracción de texto de PDF/DOCX/XLSX para contexto LLM
    │   └── history.py                   ← Registro y deshacer último movimiento
    ├── classifiers/
    │   └── decision_cache.py            ← Caché LRU + TTL de decisiones LLM por patrón de nombre
    ├── runtime/
    │   ├── event_bus.py                 ← Pub/sub de FileEvent (7 estados por archivo)
    │   └── circuit_breaker.py           ← CLOSED/OPEN/HALF_OPEN para proteger llamadas a Gemini
    ├── infra/
    │   └── metrics.py                   ← Contadores y timers en proceso (sin dependencias externas)
    ├── db/
    │   ├── database_manager.py          ← CRUD SQLite: files, actions_log, classification_events
    │   └── schema.sql                   ← Esquema de la base de datos
    ├── scripts/
    │   └── install_startup.bat          ← Instala acceso directo en Startup de Windows
    └── tests/
        ├── test_core.py                 ← Reglas, movimientos, DB, config, loop de intervalo
        ├── test_event_bus.py            ← Pub/sub, estados, short_label
        ├── test_circuit_breaker.py      ← Transiciones CLOSED/OPEN/HALF_OPEN
        └── test_decision_cache.py       ← LRU, TTL, normalización de dígitos en nombres
```

---

## Directorio de datos compartido (`%APPDATA%\Briner\`)

Todos los archivos de estado se guardan aquí. Tanto `Briner.exe` como `BrinerBackground.exe` y `BrinerMonitor.exe` apuntan al mismo directorio.

```
%APPDATA%\Briner\
├── .env                    ← GOOGLE_API_KEY=...  (cargado con python-dotenv)
├── user_settings.json      ← Carpeta monitoreada, intervalo, modo, dry_run
├── briner.db               ← Base de datos SQLite
├── .force_scan             ← Archivo centinela IPC: BrinerMonitor lo crea, BrinerBackground lo consume
└── logs/
    └── briner.log          ← Log de actividad (INFO+)
```

En modo dev (sin frozen), `APPDATA_DIR` apunta al propio directorio `briner_agent/` y la DB se ubica en `briner_agent/db/briner.db`.

---

## Base de datos SQLite

### Tabla `files`
Registro de cada archivo visto por Briner.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | INTEGER PK | Autoincremental |
| `filename` | TEXT | Nombre del archivo |
| `filepath` | TEXT UNIQUE | Ruta absoluta |
| `extension` | TEXT | Extensión (`.pdf`, `.jpg`...) |
| `size_bytes` | INTEGER | Tamaño en bytes |
| `status` | TEXT | `pending` → `processed` / `error` |
| `retry_count` | INTEGER | Intentos fallidos |
| `last_modified` | TIMESTAMP | mtime del sistema de archivos |
| `created_at` | TIMESTAMP | Cuándo se registró en la DB |

### Tabla `classification_events`
Auditoría de cada decisión de clasificación.

| Columna | Descripción |
|---|---|
| `file_id` | FK a `files.id` |
| `decision_source` | `rule` / `llm` / `system` |
| `action` | `move` / `error` / `skip` |
| `old_path` | Ruta original |
| `new_path` | Ruta de destino |
| `category` | Categoría asignada |
| `reason` | Justificación (texto libre) |
| `confidence` | Confianza 0–1 (solo LLM) |
| `dry_run` | 1 si fue simulación |

### Tabla `actions_log`
Log genérico de acciones (usado para auditoría adicional).

---

## Sistema de configuración

La configuración se construye en dos capas que se fusionan:

### Capa 1: `config.yaml` (base, inmutable para el usuario)
Empaquetado dentro del exe por PyInstaller (`datas=[('config.yaml', '.')]`). Contiene:
- **`monitoring`**: `mode`, `poll_interval`, `recursive: false` (solo archivos en la raíz de la carpeta configurada, no en subcarpetas), `ignored_patterns`, `destination_aliases` (mapeo de categoría a nombre de carpeta con número).
- **`processing`**: `max_files_per_cycle` (500), `llm_batch_size` (50), `llm_timeout_seconds` (60), `circuit_breaker_threshold` (3), `circuit_breaker_recovery_seconds` (60), `decision_cache_size` (200), `decision_cache_ttl_seconds` (3600).
- **`taxonomy`**: lista de reglas deterministas (categoría + extensiones / palabras clave).
- **`llm`**: `model` (`gemini-2.5-flash`), `temperature` (0.2).

### Capa 2: `user_settings.json` (carpeta del usuario)
Creado por `--setup` o `Install.bat`. Contiene solo:
```json
{
  "monitoring": {
    "mode": "interval",
    "workspace_dir": "D:\\Descargas",
    "poll_interval": 3600,
    "dry_run": false
  }
}
```

### Fusión (`merge_settings` en `settings_manager.py`)
Se hace un merge sección a sección (shallow update): los valores de `user_settings.json` sobreescriben los de `config.yaml` solo para las claves que aparecen en el JSON. La sección `processing`, `taxonomy`, `llm` y `rules` siempre vienen íntegras de `config.yaml`.

### Ruta de carga en frozen exe
```python
config_path = APP_DIR / "config.yaml"          # junto al exe → no existe en dist/
if not config_path.exists():
    config_path = RESOURCE_DIR / "config.yaml"  # sys._MEIPASS → _internal/ → existe
```

---

## Pipeline de procesamiento

### Modo `interval` (por defecto)

```
_run_interval_loop()
    │
    ├─ [needs_scan=True] scan_directory_once()
    │       └─ rglob workspace/, registra cada archivo como 'pending' en DB
    │          (omite archivos en carpetas de categorías ya existentes)
    │
    ├─ orchestrator.process_pending_files()   ← hasta max_files_per_cycle (500)
    │       └─ ver pipeline 3 fases abajo
    │
    └─ ¿quedan pendientes en DB?
          Sí → needs_scan=False, esperar 3 s, repetir  (modo catch-up)
          No → needs_scan=True, esperar poll_interval (3600 s), repetir
```

El modo catch-up (necesario para carpetas con decenas de miles de archivos) evita tanto el escaneo de disco redundante como la espera de 1 hora entre lotes.

### Modo `realtime` (alternativo)

```
_run_realtime_loop()
    │
    ├─ DirectoryMonitor.scan_existing_files()   ← escaneo inicial
    ├─ DirectoryMonitor.start()                  ← watchdog observa cambios en tiempo real
    │       └─ BrinerEventHandler.on_created()  → register_file() en DB
    │
    └─ loop cada 3 s:
            ├─ check .force_scan sentinel
            └─ orchestrator.process_pending_files()
```

### Pipeline de clasificación 3 fases (`agent_orchestrator.py`)

```
get_pending_files(limit=500)
         │
    [Fase 1: Reglas deterministas]
    Para cada archivo:
         ├─ classify_file() en rules_engine.py
         │       ├─ match por extensión (config taxonomy)
         │       └─ match por keywords en filename (casefold)
         │
         ├─ ¿match encontrado?
         │       Sí → move_file_secure() → status='processed' → MOVED
         │       No → archivo pasa a lista `ambiguous`
         │
    [Fase 2: Clasificación LLM por lote]
    Para cada chunk de llm_batch_size (50) archivos ambiguos:
         ├─ decision_cache.get(extension, filename_pattern)
         │       Hit  → usar decisión cacheada, sin llamada a API
         │       Miss → continuar
         │
         ├─ multimodal_parser.extract() para archivos legibles (PDF, DOCX...)
         │       ← hasta 300 chars de contenido por archivo
         │
         ├─ build_taxonomy_prompt() → prompt con lista de archivos + contenido parcial
         ├─ circuit.before_call()   ← lanza CircuitOpenError si OPEN
         ├─ llm.invoke(prompt)      ← 1 llamada a Gemini para todo el chunk
         ├─ parsear JSON de respuesta
         ├─ decision_cache.set() para cada decisión nueva
         ├─ move_file_secure() para cada archivo → status='processed'
         └─ time.sleep(2) entre chunks  ← pace para respetar límite 15 req/min Gemini
         │
    [Fase 3: Fallback ReAct por archivo]
    Solo si el lote LLM falla completamente:
         └─ Agente LangGraph ReAct, 1 archivo a la vez (último recurso)
```

### Movimiento de archivos (`crud_executor.py`)

- Resuelve el alias de categoría: `"Multimedia"` → `"4. Multimedia"` (según `destination_aliases` en config.yaml).
- Construye la ruta de destino: `workspace/4. Multimedia/Imagenes y Capturas/foto.jpg`.
- Si existe un archivo con el mismo nombre, añade sufijo numérico: `foto (1).jpg`.
- Registra el evento en `classification_events`.
- Actualiza `files.status` a `'processed'`.

---

## Comunicación entre procesos (IPC)

### Archivo centinela `.force_scan`
- **Creador:** BrinerMonitor (botón "⚡ Forzar escaneo") o el ícono de bandeja (opción "Forzar escaneo ahora").
- **Consumidor:** BrinerBackground, que lo comprueba en cada iteración del sleep loop (cada 1 segundo en modo interval, cada iteración del loop en modo realtime).
- **Efecto:** interrumpe el sleep de `poll_interval` y lanza un ciclo inmediato.
- **Ruta:** `%APPDATA%\Briner\.force_scan`

### Base de datos SQLite (compartida)
BrinerMonitor accede a la DB en modo solo lectura (`mode=ro` en la URI de conexión) para mostrar el estado. BrinerBackground tiene acceso de escritura.

---

## Circuit Breaker (`runtime/circuit_breaker.py`)

Protege las llamadas a la API de Gemini contra fallos en cascada.

```
CLOSED ──(3 fallos consecutivos)──► OPEN ──(60 s)──► HALF_OPEN
                                                           │
                                          éxito del probe ──► CLOSED
                                          fallo del probe ──► OPEN
```

- **CLOSED:** todas las llamadas LLM pasan normalmente.
- **OPEN:** todas las llamadas LLM son rechazadas con `CircuitOpenError`. Los archivos ambiguos quedan como `pending` (no se marcan como error) y se procesan en el siguiente ciclo cuando el circuit se recupere.
- **HALF_OPEN:** se permite una sola llamada de prueba.

El circuit breaker se resetea (`record_success()`) cuando el usuario cambia la API key desde el menú de la bandeja, permitiendo la recuperación inmediata.

---

## Caché de decisiones LRU (`classifiers/decision_cache.py`)

Evita llamadas repetidas a la API para archivos con el mismo patrón de nombre.

- **Clave:** `(extension, patrón_normalizado)` — los dígitos del nombre se normalizan a `#` para que `foto_001.jpg` y `foto_002.jpg` compartan la misma entrada.
- **Capacidad:** 200 entradas (LRU — la menos usada se descarta).
- **TTL:** 3600 segundos.
- **Efecto:** clasificar 1000 fotos solo requiere 1 llamada LLM si todas tienen el mismo patrón de nombre.

---

## Event Bus (`runtime/event_bus.py`)

Pub/sub desacoplado para comunicar el estado de cada archivo entre el orchestrator y el ícono de bandeja.

**7 estados posibles:**
```
DETECTED → QUEUED → PROCESSING → CLASSIFIED → MOVED
                                            ↘ IGNORED
                                            ↘ ERROR
```

El ícono de bandeja se suscribe (`bus.subscribe`) y muestra las últimas 5 acciones en el menú contextual. Cuando se muestra el ícono, se descarga del bus (`bus.unsubscribe`).

---

## Ícono de bandeja (`modules/tray_icon.py`)

- Usa `pystray` para el ícono y menú del sistema.
- En exes frozen con `console=False`, `pystray.Icon.run()` **debe ejecutarse en el hilo principal** (requisito de Win32). Por eso `main.py` llama a `tray.run_main_thread()` desde el hilo principal y lanza el loop de procesamiento en un hilo daemon.
- El método `_change_api_key()` muestra un `InputBox` de VisualBasic via PowerShell (sin dependencias UI propias), guarda la clave en `.env`, la inyecta en `os.environ`, y llama al callback `on_api_key_changed` que resetea el LLM lazy del orchestrator.

---

## LLM — Inicialización lazy (`core/llm_engine.py`)

El modelo Gemini **no se inicializa al arrancar**. Se inicializa en el primer archivo ambiguo que necesite clasificación LLM. Esto permite:
- Bandeja visible en < 2 segundos aunque la API key sea inválida.
- Resetear el modelo tras un cambio de API key simplemente poniendo `_llm_initialized = False`.

El orchestrator mantiene:
```python
self._llm_obj = None
self._llm_initialized = False
self._llm_init_lock = threading.Lock()
self.agent = None  # agente ReAct, también lazy
```

---

## Modo dry-run

Cuando `dry_run=True` en la configuración, Briner clasifica normalmente pero **no mueve** ningún archivo. Los eventos se registran en `classification_events` con `dry_run=1`. Útil para verificar la taxonomía antes de aplicarla.

---

## Argumentos de línea de comandos (`main.py`)

| Argumento | Descripción |
|---|---|
| `--setup` | Reconfigura desde cero (borra user_settings.json y pide datos) |
| `--watch-dir PATH` | Carpeta a monitorear (usada con `--setup`) |
| `--api-key KEY` | Guarda la API key en `.env` |
| `--no-wizard` | No muestra el wizard interactivo (modo servicio) |
| `--once` | Ejecuta un solo ciclo y sale |
| `--dry-run` | No mueve archivos, solo simula |
| `--no-scan` | Salta el escaneo inicial del directorio |
| `--metrics` | Imprime métricas y sale |
| `--undo-last` | Deshace el último movimiento registrado |

---

## Sistema de build (PyInstaller)

Los tres specs de PyInstaller viven en `briner_agent/`:

### `BrinerBackground.spec`
- `console=False`
- `datas=[('config.yaml', '.'), ('db/schema.sql', 'db')]` — empaqueta la configuración base y el schema SQL dentro del exe.
- `hiddenimports` incluye: `langchain_google_genai`, `langgraph`, `pystray._win32`, `PIL`, todos los módulos locales de `infra`, `runtime`, `classifiers`.
- `runtime_hooks=['rthook_fix_socket.py']` — workaround para socket en exes frozen en Windows.

### `Briner.spec`
- Idéntico a BrinerBackground excepto `console=True`.

### `BrinerMonitor.spec`
- `console=False`
- Sin LangChain ni LangGraph (excluidos explícitamente).
- Solo necesita: `sqlite3`, `tkinter`, `pystray`, `PIL`.

### Comando de build
```powershell
cd briner_agent
python -m PyInstaller --clean --noconfirm BrinerBackground.spec
python -m PyInstaller --clean --noconfirm Briner.spec
python -m PyInstaller --clean --noconfirm BrinerMonitor.spec
```
O simplemente: `build_all.bat`

### Crear zip de release
```powershell
Compress-Archive -Path "briner_agent\dist\Briner","briner_agent\dist\BrinerBackground","briner_agent\dist\BrinerMonitor","Install.bat" -DestinationPath "briner_vX.X.X.zip" -Force
```
El zip coloca las 3 carpetas y `Install.bat` al mismo nivel raíz.

---

## Tests

```powershell
cd briner_agent
python -m pytest tests/ -q
# Resultado esperado: 41 passed, 1 failed
# El fallo conocido: test_get_briner_data_dir_honors_override
# (expanduser con home mock falla en Python 3.14 en Windows — bug de entorno, no de la app)
```

### Cobertura por archivo de test

| Archivo | Qué prueba |
|---|---|
| `test_core.py` | scan_directory_once (ignora categorías, ignora patrones), _run_interval_loop (escanea antes de dormir), DatabaseManager, settings merge, arg parser |
| `test_event_bus.py` | pub/sub, múltiples suscriptores, desuscripción, short_label por estado |
| `test_circuit_breaker.py` | Transiciones CLOSED→OPEN→HALF_OPEN→CLOSED, probe exitoso/fallido |
| `test_decision_cache.py` | LRU eviction, TTL, normalización de dígitos en nombres de archivo |

---

## Flujo de instalación (Install.bat)

1. Verifica existencia de `Briner\Briner.exe`, `Briner\_internal\python314.dll`, `Briner\_internal\_socket.pyd`.
2. Muestra diálogo de selección de carpeta (PowerShell + Windows.Forms en archivo .ps1 temporal).
3. Pide la API key por consola.
4. Crea `%APPDATA%\Briner\.env` con `GOOGLE_API_KEY=...`.
5. Ejecuta `Briner.exe --setup --watch-dir "..."` → crea `user_settings.json` + instala acceso directo en Startup.
6. Mata cualquier instancia anterior de `BrinerBackground.exe`.
7. Lanza `BrinerBackground.exe --no-wizard` en segundo plano.
8. Crea acceso directo "Briner Monitor" en el Escritorio.
9. Lanza `BrinerMonitor.exe`.

---

## Decisiones de diseño relevantes

| Decisión | Motivo |
|---|---|
| 3 ejecutables separados | Briner.exe necesita consola para el setup interactivo; BrinerBackground necesita `console=False` para no flashear ventanas al arrancar con Windows; BrinerMonitor es puro UI sin dependencias de LangChain. |
| LLM inicialización lazy | La bandeja del sistema aparece en < 2 s aunque la API no esté disponible. Un error de API key no impide arrancar. |
| Sentinel file para IPC | Comunicación simple entre procesos sin sockets, sin HTTP, sin dependencias extras. Compatible con frozen exes. |
| Catch-up mode | Con carpetas de 70k+ archivos, dormir 1 hora entre lotes tomaría semanas. El catch-up procesa de forma continua hasta quedar al día. |
| 2s entre chunks LLM | La API gratuita de Gemini tiene límite de 15 req/min. Sin pausa, 3 fallos consecutivos abren el circuit breaker y bloquean la clasificación el resto del ciclo. |
| Decision cache con normalización de dígitos | Fotos de WhatsApp siguen patrones como `IMG_001.jpg`, `IMG_002.jpg`. Normalizar los dígitos a `#` permite reusar decisiones entre miles de fotos similares. |
| SQLite compartida en APPDATA | Briner.exe, BrinerBackground.exe y BrinerMonitor.exe deben leer/escribir el mismo estado. APPDATA es el punto común entre los 3 procesos independientemente de dónde estén instalados. |
