<<<<<<< HEAD
import logging
import shutil
import threading
from pathlib import Path

=======
import shutil
from pathlib import Path
import logging
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

<<<<<<< HEAD
INVALID_FOLDER_CHARS = set('<>:"\\|?*')
_thread_local = threading.local()


def _resolve_inside_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def normalize_destination(destination_folder_name: str, destination_aliases: dict | None = None) -> str:
    destination_aliases = destination_aliases or {}
    normalized = destination_folder_name.replace("\\", "/").strip("/")
    for logical_root, real_root in destination_aliases.items():
        if normalized == logical_root:
            return real_root
        if normalized.startswith(f"{logical_root}/"):
            return f"{real_root}/{normalized[len(logical_root) + 1:]}"
    return destination_folder_name


def _validate_destination(destination_folder_name: str) -> Path:
    if destination_folder_name in ("", "."):
        return Path(".")

    destination = Path(destination_folder_name)
    if destination.is_absolute():
        raise ValueError("El destino no puede ser una ruta absoluta.")

    parts = destination.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("El destino contiene segmentos no permitidos.")

    for part in parts:
        if any(char in INVALID_FOLDER_CHARS for char in part):
            raise ValueError(f"El segmento de destino '{part}' contiene caracteres invalidos.")

    return destination


def _unique_destination(dest_path: Path) -> Path:
    if not dest_path.exists():
        return dest_path

    stem = dest_path.stem
    suffix = dest_path.suffix
    parent = dest_path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_file_secure(
    source_path: str,
    destination_folder_name: str,
    workspace_root: str | Path,
    dry_run: bool = False,
    destination_aliases: dict | None = None,
) -> dict:
    """Move a file into a validated folder under workspace_root."""
    try:
        src = Path(source_path)
        if not src.exists():
            return {"ok": False, "message": f"Error: El archivo {source_path} no existe en el disco."}
        if not src.is_file():
            return {"ok": False, "message": "Error: La ruta origen no es un archivo."}

        workspace = Path(workspace_root).resolve()
        if not _resolve_inside_workspace(src, workspace):
            return {"ok": False, "message": "Error: El archivo origen esta fuera del workspace."}

        destination_folder_name = normalize_destination(destination_folder_name, destination_aliases)
        safe_destination = _validate_destination(destination_folder_name)
        dest_dir = (workspace / safe_destination).resolve()
        if not _resolve_inside_workspace(dest_dir, workspace):
            return {"ok": False, "message": "Error: El destino resuelto sale del workspace."}

        dest_path = _unique_destination(dest_dir / src.name)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "old_path": str(src.resolve()),
                "new_path": str(dest_path),
                "message": f"Dry-run: {src.name} se moveria a {dest_path}",
            }

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest_path))
        logger.info("Accion (move_file): %s movido a %s/", src.name, destination_folder_name)
        return {
            "ok": True,
            "dry_run": False,
            "old_path": str(src.resolve()),
            "new_path": str(dest_path.resolve()),
            "message": f"Exito: Archivo reubicado exitosamente a la ruta {dest_path}",
        }
    except ValueError as e:
        return {"ok": False, "message": f"Error de validacion al mover archivo: {str(e)}"}
    except Exception as e:
        logger.error("Error en move_file: %s", e)
        return {"ok": False, "message": f"Error critico al mover archivo: {str(e)}"}


def _record_thread_move(result: dict):
    if not result.get("ok"):
        return
    moves = getattr(_thread_local, "moves", None)
    if moves is None:
        moves = []
        _thread_local.moves = moves
    moves.append(result)


def consume_thread_moves() -> list[dict]:
    moves = list(getattr(_thread_local, "moves", []))
    _thread_local.moves = []
    return moves


def build_move_file_tool(
    workspace_root: str | Path,
    dry_run: bool = False,
    destination_aliases: dict | None = None,
):
    @tool
    def move_file(source_path: str, destination_folder_name: str) -> str:
        """
        Mueve un archivo desde source_path a una carpeta validada bajo el workspace.
        destination_folder_name debe ser una ruta relativa de categoria, nunca absoluta.
        """
        result = move_file_secure(
            source_path,
            destination_folder_name,
            workspace_root,
            dry_run,
            destination_aliases,
        )
        _record_thread_move(result)
        return result["message"]

    return move_file

=======
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
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43

@tool
def delete_file(file_path: str) -> str:
    """
    Elimina permanentemente un archivo del sistema.
<<<<<<< HEAD
    Usar exclusivamente para borrar archivos basura, temporales o inutiles.
=======
    Útil EXCLUSIVAMENTE para borrar archivos basura, temporales o inútiles.
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43
    """
    try:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()
<<<<<<< HEAD
            logger.info("Accion (delete_file): %s eliminado.", path.name)
            return "Exito: Archivo eliminado del sistema."
        return "Error: El archivo no fue encontrado o es una carpeta."
    except Exception as e:
        return f"Error al eliminar: {str(e)}"


def get_crud_tools(
    workspace_root: str | Path = ".",
    dry_run: bool = False,
    destination_aliases: dict | None = None,
):
    """Retorna la lista de herramientas CRUD para LangChain."""
    return [build_move_file_tool(workspace_root, dry_run, destination_aliases), delete_file]
=======
            logger.info(f"Acción (delete_file): {path.name} eliminado.")
            return f"Éxito: Archivo eliminado del sistema."
        return f"Error: El archivo no fue encontrado o es una carpeta."
    except Exception as e:
        return f"Error al eliminar: {str(e)}"

def get_crud_tools():
    """Retorna la lista de herramientas CRUD para LangChain."""
    return [move_file, delete_file]
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43
