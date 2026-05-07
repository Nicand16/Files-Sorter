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

    def _get_file_info(self, filepath):
        path = Path(filepath)
        try:
            stat = path.stat()
            return path.name, str(path.resolve()), path.suffix, stat.st_size, stat.st_mtime
        except FileNotFoundError:
            return path.name, str(path.resolve()), path.suffix, 0, 0.0

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
        self.observer.stop()
        self.observer.join()
