# Briner — Organizador automático de archivos

Briner organiza automáticamente los archivos de tu carpeta de Descargas (o cualquier carpeta que elijas). Se ejecuta silenciosamente en segundo plano, clasifica cada archivo mediante reglas locales y/o IA (Google Gemini), y los mueve a subcarpetas ordenadas.

## Documentación

| Documento | Descripción |
|---|---|
| [MANUAL_USO.md](MANUAL_USO.md) | Instalación, uso y solución de problemas para el usuario final |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Arquitectura completa, lógica interna y guía técnica para desarrolladores |

## Instalación rápida

1. Descarga `briner_v1.1.0.zip` desde [Releases](https://github.com/Nicand16/Files-Sorter/releases) y extrae todos los archivos.
2. Haz doble clic en **`Install.bat`**.
3. Selecciona tu carpeta de Descargas y pega tu API key de [Google Gemini](https://aistudio.google.com/apikey) (gratuita).

No se requiere instalar Python ni dependencias adicionales.

## Carpetas de destino

| Carpeta | Contenido |
|---|---|
| `1. Universidad y Estudio` | Tareas, libros, materiales académicos |
| `2. Software y Herramientas` | Instaladores, comprimidos |
| `3. Juegos y Emulación` | ROMs, ISOs, torrents |
| `4. Multimedia` | Imágenes, videos, audio |
| `5. Trabajo y Empleo` | CVs, contratos, ofertas |
| `6. Documentos Personales` | Cédula, facturas, certificados |
| `7. Varios` | Todo lo que no encaja en otra categoría |

## Para desarrolladores

```powershell
cd briner_agent
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt

# Configurar y ejecutar desde código fuente
python main.py --setup
python main.py

# Pruebas
python -m pytest tests/ -q    # 41 passed, 1 known failure (expanduser en Python 3.14/Windows)

# Reconstruir executables
build_all.bat
```

Ver [ARCHITECTURE.md](ARCHITECTURE.md) para la descripción completa de módulos, pipeline de clasificación, base de datos, IPC y decisiones de diseño.
