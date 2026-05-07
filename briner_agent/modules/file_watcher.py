<<<<<<< HEAD
import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class BrinerEventHandler(FileSystemEventHandler):
    """
    Sincroniza eventos del workspace con SQLite.
    Aplica debounce y evita reprocesar archivos ya movidos a carpetas de categoria.
    """

    def __init__(self, db_manager, watch_directory: str | Path, config: dict | None = None):
        super().__init__()
        self.db = db_manager
        self.watch_directory = Path(watch_directory).resolve()
        self.config = config or {}
        monitoring_config = self.config.get("monitoring", {})
        self.debounce_seconds = float(monitoring_config.get("debounce_seconds", 2))
        self.ignore_existing_categories = monitoring_config.get("ignore_existing_categories", True)
        self.ignored_filenames = {name.casefold() for name in monitoring_config.get("ignored_filenames", [".keep", "desktop.ini"])}
        self._recent_events: dict[str, tuple[float, int, float]] = {}
        self._category_roots = self._build_category_roots()

    def _build_category_roots(self) -> set[Path]:
        roots = set()
        for rule in self.config.get("taxonomy", {}).get("categories", []):
            category = rule.get("category")
            if category:
                roots.add((self.watch_directory / category).resolve())
        roots.add((self.watch_directory / "Varios").resolve())
        return roots

    def _is_ignored_filename(self, filepath: str | Path) -> bool:
        return Path(filepath).name.casefold() in self.ignored_filenames

    def _is_inside_category(self, filepath: str | Path) -> bool:
        if not self.ignore_existing_categories:
            return False
        path = Path(filepath).resolve()
        return any(path == root or root in path.parents for root in self._category_roots)
=======
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import os

# Configuración básica de logging para el módulo
logger = logging.getLogger(__name__)

class BrinerEventHandler(FileSystemEventHandler):
    """
    Manejador de eventos del sistema de archivos para Briner.
    Se encarga de interceptar eventos en el workspace y sincronizar
    el estado en la base de datos local SQLite.
    """

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43

    def _get_file_info(self, filepath):
        path = Path(filepath)
        try:
            stat = path.stat()
            return path.name, str(path.resolve()), path.suffix, stat.st_size, stat.st_mtime
        except FileNotFoundError:
            return path.name, str(path.resolve()), path.suffix, 0, 0.0

<<<<<<< HEAD
    def _should_register(self, filepath: str | Path) -> bool:
        path = Path(filepath)
        if self._is_ignored_filename(path):
            return False
        if self._is_inside_category(path):
            logger.debug("Ignorando archivo ya categorizado: %s", path)
            return False

        try:
            stat = path.stat()
            fingerprint = (stat.st_size, stat.st_mtime)
        except FileNotFoundError:
            fingerprint = (0, 0.0)

        resolved = str(path.resolve())
        now = time.monotonic()
        recent = self._recent_events.get(resolved)
        if recent:
            last_seen, last_size, last_mtime = recent
            if now - last_seen < self.debounce_seconds and (last_size, last_mtime) == fingerprint:
                return False

        self._recent_events[resolved] = (now, fingerprint[0], fingerprint[1])
        return True

    def register_existing_file(self, filepath: str | Path):
        if not self._should_register(filepath):
            return
        info = self._get_file_info(filepath)
        self.db.register_file(*info)

    def on_created(self, event):
        if event.is_directory or not self._should_register(event.src_path):
            return
        logger.info("[CREADO] Archivo detectado: %s", event.src_path)
        self.db.register_file(*self._get_file_info(event.src_path))

    def on_modified(self, event):
        if event.is_directory or not self._should_register(event.src_path):
            return
        logger.info("[MODIFICADO] Archivo actualizado: %s", event.src_path)
        self.db.register_file(*self._get_file_info(event.src_path))

    def on_deleted(self, event):
        if event.is_directory:
            return
        logger.info("[ELIMINADO] Archivo borrado: %s", event.src_path)
        self.db.remove_file(str(Path(event.src_path).resolve()))

    def on_moved(self, event):
        if event.is_directory:
            return
        logger.info("[MOVIDO] Archivo movido de %s a %s", event.src_path, event.dest_path)
        self.db.remove_file(str(Path(event.src_path).resolve()))
        if self._should_register(event.dest_path):
            self.db.register_file(*self._get_file_info(event.dest_path))


class DirectoryMonitor:
    """Configura y arranca watchdog sobre el workspace."""

    def __init__(self, watch_directory: str, db_manager, config: dict | None = None):
        self.watch_directory = Path(watch_directory)
        self.observer = Observer()
        self.event_handler = BrinerEventHandler(db_manager, self.watch_directory, config)

    def scan_existing_files(self):
        self.watch_directory.mkdir(parents=True, exist_ok=True)
        for path in self.watch_directory.rglob("*"):
            if path.is_file():
                self.event_handler.register_existing_file(path)

    def start(self):
        self.watch_directory.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.event_handler, str(self.watch_directory.absolute()), recursive=True)
        self.observer.start()
        logger.info("Monitorizacion en tiempo real iniciada en: %s", self.watch_directory.absolute())

    def stop(self):
        logger.info("Deteniendo monitorizacion de archivos...")
=======
    def on_created(self, event):
        if not event.is_directory:
            if "desktop.ini" in event.src_path.lower():
                return
            logger.info(f"[CREADO] Archivo detectado: {event.src_path}")
            info = self._get_file_info(event.src_path)
            self.db.register_file(*info)

    def on_modified(self, event):
        if not event.is_directory:
            if "desktop.ini" in event.src_path.lower():
                return
            logger.info(f"[MODIFICADO] Archivo actualizado: {event.src_path}")
            info = self._get_file_info(event.src_path)
            self.db.register_file(*info)

    def on_deleted(self, event):
        if not event.is_directory:
            logger.info(f"[ELIMINADO] Archivo borrado: {event.src_path}")
            self.db.remove_file(str(Path(event.src_path).resolve()))

    def on_moved(self, event):
        if not event.is_directory:
            logger.info(f"[MOVIDO] Archivo movido de {event.src_path} a {event.dest_path}")
            self.db.remove_file(str(Path(event.src_path).resolve()))
            info = self._get_file_info(event.dest_path)
            self.db.register_file(*info)

class DirectoryMonitor:
    """
    Clase encargada de configurar y arrancar el observador (Observer)
    de watchdog sobre un directorio específico.
    """

    def __init__(self, watch_directory: str, db_manager):
        self.watch_directory = Path(watch_directory)
        self.observer = Observer()
        self.event_handler = BrinerEventHandler(db_manager)

    def start(self):
        # Asegurar que el directorio a monitorizar existe
        self.watch_directory.mkdir(parents=True, exist_ok=True)
        
        # Programar el observador
        self.observer.schedule(self.event_handler, str(self.watch_directory.absolute()), recursive=True)
        self.observer.start()
        logger.info(f"Monitorización en tiempo real iniciada en: {self.watch_directory.absolute()}")
        # El bucle de espera se traslada a main.py para dar espacio al orquestador

    def stop(self):
        logger.info("Deteniendo monitorización de archivos...")
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43
        self.observer.stop()
        self.observer.join()
