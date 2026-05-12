# Briner - Manual de uso

Briner organiza automaticamente los archivos de una carpeta elegida por el usuario. La instalacion normal no requiere Python ni comandos: solo extraer el zip, ejecutar `Install.bat`, elegir carpeta y pegar la API key de Gemini.

Version: `1.2.0`.

## Instalacion

### Requisitos

- Windows 10 u 11.
- API key gratuita de Google Gemini: <https://aistudio.google.com/apikey>.
- El zip de release completo: `briner_v1.2.0.zip`.

### Pasos

1. Extrae el zip completo en una carpeta.
2. Ejecuta `Install.bat`.
3. Selecciona la carpeta que quieres organizar, por ejemplo `Downloads`.
4. Pega tu API key de Gemini.
5. Briner arranca en segundo plano, crea el acceso directo de inicio con Windows y abre Briner Monitor.

Importante: no ejecutes `Install.bat` dentro del zip sin extraer.

## Uso Diario

Briner se maneja desde dos lugares:

- Icono de bandeja: circulo de color junto al reloj de Windows.
- Briner Monitor: ventana con historial, estado y controles.

No es necesario editar `config.yaml`, `.env` ni `user_settings.json` para uso normal.

## Que Hace Automaticamente

1. Escanea la carpeta monitoreada.
2. Ignora archivos temporales y carpetas ya organizadas.
3. Clasifica por reglas locales cuando hay evidencia clara.
4. Si hay pocos archivos ambiguos, consulta Gemini individualmente con mas contexto.
5. Si hay muchos archivos ambiguos, hace peticiones bulk para reducir costo y cuota.
6. Usa metadatos y contenido parcial de documentos cuando es posible.
7. Mueve archivos a carpetas numeradas.
8. Aprende de decisiones recientes guardadas en SQLite para evitar llamadas repetidas.

## Carpetas Creadas

| Carpeta | Uso |
|---|---|
| `1. Universidad y Estudio` | Tareas, modulos, libros, tramites academicos |
| `2. Software y Herramientas` | Instaladores, comprimidos, herramientas |
| `3. Juegos y Emulacion` | ROMs, ISOs, torrents, emuladores |
| `4. Multimedia` | Imagenes, videos y audio |
| `5. Trabajo y Empleo` | CVs, contratos, ofertas y procesos laborales |
| `6. Documentos Personales` | Identificacion, impuestos, salud y finanzas |
| `7. Varios\Documentos por Revisar` | Documentos sin evidencia suficiente |
| `_Briner Quarantine` | Archivos basura o temporales retirados sin borrado permanente |

## Seguridad de Archivos

Briner no borra archivos permanentemente. La herramienta interna `delete_file` fue reemplazada por cuarentena:

```text
_Briner Quarantine\AAAA-MM
```

Si algo termina en cuarentena por error, puedes moverlo manualmente de vuelta.

## Icono de Bandeja

| Color | Estado |
|---|---|
| Verde | Corriendo normalmente |
| Azul | Procesando |
| Rojo | Error activo |

Menu de clic derecho:

- Abrir monitor en tiempo real.
- Ver logs.
- Abrir carpeta monitoreada.
- Abrir documentos por revisar.
- Forzar escaneo ahora.
- Cambiar carpeta.
- Pausar/Reanudar.
- Deshacer ultimo movimiento.
- Cambiar API key.
- Detener Briner.

## Briner Monitor

Briner Monitor permite manejar la app sin comandos:

- Ver pendientes, procesados y errores.
- Revisar los ultimos eventos.
- Forzar escaneo.
- Cambiar carpeta monitoreada.
- Pausar o reanudar.
- Deshacer ultimo movimiento.
- Abrir `Documentos por Revisar`.
- Abrir logs.
- Cambiar API key.

Cuando cambias la API key desde Monitor, BrinerBackground la recarga automaticamente mediante IPC. No hace falta reiniciar.

## Cambiar Carpeta Monitoreada

Opcion recomendada:

1. Abre Briner Monitor.
2. Pulsa `Cambiar carpeta`.
3. Selecciona la nueva carpeta.
4. Briner aplica el cambio en el siguiente ciclo inmediato.

Tambien puedes hacerlo desde el icono de bandeja con `Cambiar carpeta...`.

Si la carpeta anterior deja de existir, Briner se pausa y espera a que configures una carpeta valida.

## Cambiar API Key

Opcion recomendada:

1. Abre Briner Monitor o el menu de bandeja.
2. Pulsa `Cambiar API key`.
3. Pega la nueva clave.
4. Briner guarda `.env`, reinicia el cliente Gemini y limpia el circuit breaker.

## Pausar, Reanudar y Forzar Escaneo

- `Pausar`: detiene temporalmente la organizacion.
- `Reanudar`: vuelve a procesar.
- `Forzar escaneo`: revisa la carpeta sin esperar el intervalo de una hora.

## Deshacer Ultimo Movimiento

Desde Monitor o bandeja usa `Deshacer`. Briner mueve de vuelta el ultimo archivo movido y registra el evento en el historial.

## Donde Guarda Datos

En modo instalado, todo vive en:

```text
%APPDATA%\Briner
```

| Archivo/carpeta | Descripcion |
|---|---|
| `.env` | API key de Gemini |
| `user_settings.json` | Carpeta monitoreada y opciones basicas |
| `briner.db` | Historial SQLite |
| `logs\briner.log` | Logs tecnicos |
| `commands\*.json` | Comandos pendientes entre Monitor/Tray y Background |
| `.force_scan` | Senal simple de escaneo inmediato |

## Solucion de Problemas

### No veo el icono

Haz clic en la flecha de iconos ocultos junto al reloj de Windows. Si no aparece, abre Briner Monitor desde el escritorio.

### Hay muchos pendientes

Es normal en el primer arranque. Briner procesa por lotes hasta ponerse al dia.

### Gemini dice cuota excedida

Briner abre circuit breaker y reintenta automaticamente. Puedes esperar o cambiar API key.

### API key invalida

Usa `Cambiar API key` desde Monitor o bandeja. No reinicies manualmente.

### Quiero revisar decisiones dudosas

Abre `Documentos por Revisar` desde Monitor o bandeja. Los documentos ambiguos van ahi en vez de perderse dentro de `Varios`.

### Quiero recuperar algo de cuarentena

Abre la carpeta monitoreada y busca:

```text
_Briner Quarantine
```

Mueve el archivo manualmente a donde corresponda.

## Comandos Avanzados

Desde `Briner\Briner.exe`:

```powershell
.\Briner.exe --once
.\Briner.exe --once --dry-run
.\Briner.exe --metrics
.\Briner.exe --undo-last
.\Briner.exe --setup --watch-dir "D:\Descargas" --api-key "AIza..."
```

Estos comandos son para diagnostico o soporte; el uso normal se hace desde Monitor o bandeja.
