import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Gestiona la conexión y operaciones CRUD para la base de datos de estado de Briner."""
    
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        # Asegurar que el directorio de la base de datos existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_db()

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path))

    def _initialize_db(self):
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            logger.error(f"No se encontró el archivo de esquema en: {schema_path}")
            return

        with open(schema_path, "r", encoding="utf-8") as f:
            schema_script = f.read()

        try:
            with self._get_connection() as conn:
                conn.executescript(schema_script)
            logger.info(f"Base de datos inicializada/verificada exitosamente en: {self.db_path.name}")
        except sqlite3.Error as e:
            logger.error(f"Error al inicializar la base de datos: {e}")

    def register_file(self, filename: str, filepath: str, extension: str, size_bytes: int, last_modified: float):
        """Registra un nuevo archivo o actualiza su información y lo marca como 'pending'."""
        query = """
        INSERT INTO files (filename, filepath, extension, size_bytes, last_modified)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(filepath) DO UPDATE SET
            filename=excluded.filename,
            extension=excluded.extension,
            size_bytes=excluded.size_bytes,
            last_modified=excluded.last_modified,
            status='pending'
        """
        try:
            with self._get_connection() as conn:
                conn.execute(query, (filename, filepath, extension, size_bytes, last_modified))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al registrar archivo {filepath}: {e}")
            return False

    def remove_file(self, filepath: str):
        """Elimina el registro de un archivo si fue borrado del sistema."""
        query = "DELETE FROM files WHERE filepath = ?"
        try:
            with self._get_connection() as conn:
                conn.execute(query, (filepath,))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al eliminar archivo {filepath}: {e}")
            return False

    def update_file_status(self, filepath: str, status: str):
        """Actualiza el estado de procesamiento del archivo."""
        query = "UPDATE files SET status = ? WHERE filepath = ?"
        try:
            with self._get_connection() as conn:
                conn.execute(query, (status, filepath))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al actualizar estado de {filepath}: {e}")
            return False

    def log_action(self, filepath: str, action_type: str, description: str):
        """Registra una acción que el agente haya tomado sobre un archivo."""
        query = """
        INSERT INTO actions_log (file_id, action_type, description)
        SELECT id, ?, ? FROM files WHERE filepath = ?
        """
        try:
            with self._get_connection() as conn:
                conn.execute(query, (action_type, description, filepath))
                return True
        except sqlite3.Error as e:
            logger.error(f"Error al registrar acción para el archivo {filepath}: {e}")
            return False

    def get_pending_files(self):
        """Obtiene la lista de archivos marcados como 'pending'."""
        query = "SELECT id, filename, filepath, extension FROM files WHERE status = 'pending'"
        try:
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error al obtener archivos pendientes: {e}")
            return []
