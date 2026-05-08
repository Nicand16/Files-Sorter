# Briner — Manual de uso

Briner organiza automáticamente los archivos de cualquier carpeta (típicamente Descargas). Se ejecuta silenciosamente en segundo plano, clasifica cada archivo usando reglas locales y/o inteligencia artificial (Google Gemini), y los mueve a subcarpetas ordenadas.

---

## Instalación

### Requisitos
- Windows 10 u 11
- API key de Google Gemini (gratuita en [aistudio.google.com/apikey](https://aistudio.google.com/apikey))
- No se necesita Python ni ninguna dependencia adicional

### Pasos
1. Descarga `briner_v1.1.0.zip` desde la sección [Releases](https://github.com/Nicand16/Files-Sorter/releases) de GitHub y extrae **todos** los archivos en una carpeta.
2. Haz doble clic en **`Install.bat`**.
3. Selecciona la carpeta que deseas organizar en el diálogo que aparece (ej. `C:\Users\tu_usuario\Downloads`).
4. Pega tu API key de Google Gemini cuando se te solicite.
5. Listo. Briner arranca de inmediato y se configurará para iniciarse automáticamente con Windows.

> **Importante:** extrae el zip antes de ejecutar `Install.bat`. No lo abras desde dentro del zip sin extraer.

---

## Qué hace Briner tras la instalación

### Primer arranque

Al iniciar por primera vez sobre una carpeta con muchos archivos, Briner:

1. **Escanea** todos los archivos de la carpeta y los registra en su base de datos como "pendientes". El contador de pendientes en el monitor crece durante esta fase.
2. **Procesa** los archivos por lotes de hasta 500 a la vez, moviéndolos a sus carpetas correspondientes.
3. **Continúa** procesando el siguiente lote inmediatamente (modo "ponerse al día") hasta que no quede ningún archivo pendiente.
4. Una vez al día procesados, espera 1 hora y repite el escaneo para detectar archivos nuevos.

### Uso continuo

Cada hora Briner escanea la carpeta raíz (no las subcarpetas de destino), detecta archivos nuevos y los clasifica. Los archivos ya organizados no se tocan.

---

## Carpetas de destino

Briner crea estas subcarpetas dentro de la carpeta que configuraste:

| Carpeta | Qué contiene |
|---|---|
| `1. Universidad y Estudio` | Tareas, libros, módulos, trámites académicos |
| `2. Software y Herramientas` | Instaladores (`.exe`, `.msi`), portátiles, comprimidos |
| `3. Juegos y Emulación` | ROMs, ISOs, torrents de juegos, emuladores |
| `4. Multimedia` | Imágenes, videos, audio |
| `5. Trabajo y Empleo` | CVs, contratos, ofertas laborales |
| `6. Documentos Personales` | Cédula, RUT, facturas, certificados, recibos |
| `7. Varios` | Todo lo que no encaja en otra categoría |

---

## Cómo se clasifican los archivos

Briner usa un proceso en tres fases:

1. **Reglas locales (sin internet):** extensión del archivo (`.pdf`, `.exe`, `.jpg`...) y palabras clave en el nombre (`cv`, `factura`, `modulo`...). Rápido e instantáneo.
2. **IA por lote (Gemini):** para los archivos que las reglas no pueden clasificar con certeza, Briner envía un grupo de hasta 50 archivos en una sola llamada a la API y recibe las categorías para todos. Si ya clasificó un archivo con el mismo patrón antes, usa la caché (sin llamar a la API de nuevo).
3. **Fallback individual:** si el lote falla, intenta clasificar cada archivo ambiguo por separado.

Si no hay API key o la IA falla, los archivos ambiguos van a `7. Varios`.

---

## Ícono de la bandeja del sistema

Al arrancar, Briner muestra un círculo de color en la bandeja del sistema (esquina inferior derecha, junto a WiFi y volumen). Si no lo ves, haz clic en la flecha `∧` para ver los íconos ocultos.

| Color | Significado |
|---|---|
| Verde | Corriendo normalmente |
| Azul | Procesando archivos activamente |
| Rojo | Error activo (ver menú para detalles) |

### Menú del ícono (clic derecho)

- **Estado y contadores** — archivos pendientes, procesados totales, errores, hora del último ciclo.
- **Últimas 5 acciones** — feed en vivo de los archivos más recientes (`[>]` movido, `[!]` error, `[*]` procesando, `[-]` ignorado).
- **Abrir monitor en tiempo real** — abre la ventana BrinerMonitor con el historial completo.
- **Ver logs** — abre el archivo de log en el explorador.
- **Abrir carpeta monitoreada** — abre la carpeta en el explorador.
- **Forzar escaneo ahora** — lanza un ciclo inmediato sin esperar la hora.
- **Cambiar API key...** — abre un cuadro de diálogo para pegar una nueva API key de Gemini. Briner la guarda y la aplica sin necesidad de reiniciar.
- **Detener Briner** — apaga el servicio (no vuelve a arrancar hasta el próximo inicio de Windows o si lo lanzas manualmente).

---

## Ventana BrinerMonitor

La ventana de monitoreo muestra en tiempo real la actividad de Briner. Puedes abrirla desde el acceso directo "Briner Monitor" en el Escritorio o desde el menú de la bandeja.

- **Indicador verde/gris/rojo** — estado actual del servicio.
- **Pendientes / Procesados / Errores** — contadores del total acumulado en la base de datos.
- **Tabla de eventos** — los últimos 100 movimientos con hora, nombre de archivo, categoría, fuente de decisión, acción y modo (dry-run o real).
- **⚡ Forzar escaneo** — señaliza a BrinerBackground para que procese de inmediato.
- **↺ Actualizar ahora** — refresca la tabla al instante (se refresca automáticamente cada 3 segundos).
- **Abrir logs** — abre la carpeta de logs.

Minimizar la ventana la oculta a la bandeja del sistema (no a la barra de tareas). Para cerrarla completamente usa el menú de la bandeja → Cerrar.

---

## Cambiar la API key

### Desde la bandeja (más fácil)
Clic derecho en el ícono de Briner → **Cambiar API key...** → pega la nueva clave → Aceptar.
Briner la guarda y recarga el modelo sin reiniciar.

### Manualmente
Edita el archivo `%APPDATA%\Briner\.env`:
```
GOOGLE_API_KEY=tu_nueva_api_key
```
Luego reinicia BrinerBackground (o usa "Detener Briner" y vuelve a lanzarlo).

---

## Cambiar la carpeta monitoreada

La forma más sencilla es volver a ejecutar `Install.bat` — pedirá la nueva carpeta y confirmará la API key.

También puedes editar `%APPDATA%\Briner\user_settings.json`:
```json
{
  "monitoring": {
    "workspace_dir": "D:\\MiCarpeta",
    "mode": "interval",
    "poll_interval": 3600,
    "dry_run": false
  }
}
```
Después reinicia BrinerBackground.

---

## Archivos de configuración

Todos los datos de Briner se guardan en `%APPDATA%\Briner\`:

| Archivo | Descripción |
|---|---|
| `.env` | API key de Gemini (`GOOGLE_API_KEY=...`) |
| `user_settings.json` | Carpeta monitoreada, intervalo, modo |
| `briner.db` | Base de datos SQLite con historial de archivos |
| `logs\briner.log` | Registro de actividad detallado |

---

## Logs

```powershell
Get-Content "$env:APPDATA\Briner\logs\briner.log" -Tail 50
```

Mensajes normales al arrancar correctamente:
```
Iniciando Briner - Agente Autonomo de Gestion de Archivos
Modo activo: interval
Carpeta monitoreada: D:\Descargas
Intervalo efectivo: 3600 segundo(s)
LLM: lazy (se inicializara al primer archivo ambiguo)
```

---

## Autoarranque con Windows

El acceso directo de inicio automático se instala durante la primera configuración en:
```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Briner.lnk
```

Para quitar el autoarranque: elimina ese acceso directo.

---

## Comandos avanzados (desde consola)

Todos los comandos se ejecutan desde `briner_agent\dist\Briner\`:

```powershell
# Una sola pasada de clasificación y sale
.\Briner.exe --once

# Simular sin mover archivos (modo seguro para probar)
.\Briner.exe --once --dry-run

# Ver métricas de rendimiento (latencia LLM, caché, fases)
.\Briner.exe --metrics

# Reconfigurar carpeta y API key
.\Briner.exe --setup --watch-dir "D:\MiCarpeta" --api-key "AIza..."

# Deshacer el último movimiento realizado
.\Briner.exe --undo-last
```

---

## Solución de problemas

### Briner no mueve archivos
- Verifica que los archivos estén directamente en la carpeta raíz (no en subcarpetas numeradas).
- Revisa que `dry_run` sea `false` en `user_settings.json`.
- Revisa el log: `Get-Content "$env:APPDATA\Briner\logs\briner.log" -Tail 30`.

### El monitor muestra muchos pendientes y no avanza
Esto es normal en el primer arranque con muchos archivos. Briner procesa en lotes continuos (modo "ponerse al día") sin esperas entre lotes. Para carpetas con decenas de miles de archivos puede tardar varias horas. El ícono de la bandeja debería estar azul mientras trabaja.

### Error de API key / ícono rojo
Usa el menú → **Cambiar API key...** y pega una clave válida de [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Briner funciona sin API key, pero los archivos ambiguos irán a `7. Varios`.

### Quiero probar sin arriesgar mis archivos
```powershell
briner_agent\dist\Briner\Briner.exe --once --dry-run
```
No mueve nada — solo muestra qué haría en el log y la consola.

### Reinstalar desde cero
Vuelve a ejecutar `Install.bat`. El instalador cierra cualquier instancia anterior y comienza limpio.
