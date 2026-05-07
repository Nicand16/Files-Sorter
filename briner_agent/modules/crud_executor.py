import shutil
from pathlib import Path
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def move_file(source_path: str, destination_folder_name: str) -> str:
    """
    Mueve un archivo desde source_path a una nueva carpeta llamada destination_folder_name.
    Crea la carpeta de destino automáticamente si no existe.
    IMPORTANTE: destination_folder_name debe ser solo un nombre lógico de carpeta (ej: 'Facturas', 'Imágenes', 'Reportes'), NO una ruta absoluta.
    """
    try:
        src = Path(source_path)
        if not src.exists():
            return f"Error: El archivo {source_path} no existe en el disco."
            
        # Creamos la carpeta destino en el mismo directorio donde reside actualmente el archivo (el workspace)
        dest_dir = src.parent / destination_folder_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        dest_path = dest_dir / src.name
        
        shutil.move(str(src), str(dest_path))
        logger.info(f"Acción (move_file): {src.name} movido a {destination_folder_name}/")
        return f"Éxito: Archivo reubicado exitosamente a la ruta {dest_path}"
    except Exception as e:
        logger.error(f"Error en move_file: {e}")
        return f"Error crítico al mover archivo: {str(e)}"

@tool
def delete_file(file_path: str) -> str:
    """
    Elimina permanentemente un archivo del sistema.
    Útil EXCLUSIVAMENTE para borrar archivos basura, temporales o inútiles.
    """
    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
            logger.info(f"Acción (delete_file): {path.name} eliminado.")
            return f"Éxito: Archivo eliminado del sistema."
        return f"Error: El archivo no fue encontrado o es una carpeta."
    except Exception as e:
        return f"Error al eliminar: {str(e)}"

def get_crud_tools():
    """Retorna la lista de herramientas CRUD para LangChain."""
    return [move_file, delete_file]
