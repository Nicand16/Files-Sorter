import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from runtime.event_bus import FileEvent, FileState, bus

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

    def _get_file_info(self, filepath):
        path = Path(filepath)
        try:
            stat = path.stat()
            return path.name, str(path.resolve()), path.suffix, stat.st_size, stat.st_mtime
        except FileNotFoundError:
            return path.name, str(path.resolve()), path.suffix, 0, 0.0

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
        if self.db.register_file(*info):
            bus.publish(FileEvent(
                state=FileState.DETECTED,
                filepath=str(Path(filepath).resolve()),
                filename=Path(filepath).name,
            ))

    def on_created(self, event):
        if event.is_directory or not self._should_register(event.src_path):
            return
        logger.info("[CREADO] Archivo detectado: %s", event.src_path)
        if self.db.register_file(*self._get_file_info(event.src_path)):
            bus.publish(FileEvent(
                state=FileState.DETECTED,
                filepath=str(Path(event.src_path).resolve()),
                filename=Path(event.src_path).name,
            ))

    def on_modified(self, event):
        if event.is_directory or not self._should_register(event.src_path):
            return
        logger.info("[MODIFICADO] Archivo actualizado: %s", event.src_path)
        if self.db.register_file(*self._get_file_info(event.src_path)):
            bus.publish(FileEvent(
                state=FileState.DETECTED,
                filepath=str(Path(event.src_path).resolve()),
                filename=Path(event.src_path).name,
            ))

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
        self.observer.stop()
        self.observer.join()
