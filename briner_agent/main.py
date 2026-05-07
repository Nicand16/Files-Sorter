import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import yaml

CODE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else CODE_DIR
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", CODE_DIR)).resolve()
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from core.settings_manager import load_or_create_user_settings, normalize_monitoring_config
from db.database_manager import DatabaseManager
from modules.periodic_scanner import scan_directory_once

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "briner.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("BrinerMain")


def load_environment():
    env_logger = logging.getLogger("BrinerMain")
    env_path = APP_DIR / ".env"
    if load_dotenv:
        load_dotenv(env_path, override=True)
        load_dotenv()

    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        if env_path.exists():
            env_logger.info("Credenciales IA cargadas desde .env junto a Briner.exe.")
        return
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            if "=" in value:
                key, raw_value = value.split("=", 1)
                key = key.strip()
                raw_value = raw_value.strip().strip('"').strip("'")
                if key in {"GOOGLE_API_KEY", "GEMINI_API_KEY"} and raw_value:
                    os.environ[key] = raw_value
                    env_logger.info("Credenciales IA cargadas manualmente desde .env.")
                    return
                continue
            os.environ["GOOGLE_API_KEY"] = value
            env_logger.info("API key cargada desde .env en formato simple.")
            return
    except OSError as exc:
        env_logger.warning("No se pudo leer .env: %s", exc)


load_environment()


def load_config(config_path="config.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        logger.warning("Archivo de configuracion no encontrado en %s. Usando valores por defecto.", config_path)
        return {}

    with open(path, "r", encoding="utf-8") as file:
        try:
            return yaml.safe_load(file) or {}
        except yaml.YAMLError as exc:
            logger.error("Error parseando el archivo YAML: %s", exc)
            return {}


def resolve_app_path(path_value: str | Path, base_dir: Path = APP_DIR) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Briner file organizer")
    parser.add_argument("--once", action="store_true", help="Escanea y procesa una sola vez.")
    parser.add_argument("--no-scan", action="store_true", help="No registra archivos existentes al arrancar.")
    parser.add_argument("--dry-run", action="store_true", help="Propone movimientos sin tocar archivos.")
    parser.add_argument("--metrics", action="store_true", help="Imprime metricas basicas y termina.")
    parser.add_argument("--undo-last", action="store_true", help="Deshace el ultimo movimiento real registrado.")
    parser.add_argument("--setup", action="store_true", help="Fuerza el wizard de configuracion inicial.")
    parser.add_argument("--no-wizard", action="store_true", help="Usa config/defaults sin pedir settings iniciales.")
    return parser


def _run_interval_loop(orchestrator, db_manager, workspace_dir: Path, config: dict, poll_interval: int, once: bool):
    while True:
        try:
            detected = scan_directory_once(workspace_dir, db_manager, config)
            result = orchestrator.process_pending_files()
            logger.info(
                "Ciclo interval terminado. detectados=%s procesados=%s errores=%s",
                detected,
                result.get("processed", 0),
                result.get("errors", 0),
            )
        except Exception as exc:
            logger.exception("Error inesperado en ciclo interval; el servicio continuara: %s", exc)

        if once:
            return
        time.sleep(poll_interval)


def _run_realtime_loop(orchestrator, db_manager, workspace_dir: Path, config: dict, once: bool):
    from modules.file_watcher import DirectoryMonitor

    monitor = DirectoryMonitor(watch_directory=str(workspace_dir), db_manager=db_manager, config=config)
    if not config.get("runtime", {}).get("no_scan", False):
        monitor.scan_existing_files()

    if once:
        orchestrator.process_pending_files()
        return

    monitor.start()
    try:
        while True:
            try:
                result = orchestrator.process_pending_files()
                logger.info(
                    "Ciclo realtime terminado. procesados=%s errores=%s",
                    result.get("processed", 0),
                    result.get("errors", 0),
                )
            except Exception as exc:
                logger.exception("Error inesperado en ciclo realtime; el servicio continuara: %s", exc)
            time.sleep(3)
    finally:
        monitor.stop()


def main():
    args = build_arg_parser().parse_args()
    logger.info("Iniciando Briner - Agente Autonomo de Gestion de Archivos")

    config_path = APP_DIR / "config.yaml"
    if not config_path.exists():
        config_path = RESOURCE_DIR / "config.yaml"
    config = normalize_monitoring_config(load_config(config_path))
    settings_path = APP_DIR / "user_settings.json"
    if args.setup and settings_path.exists():
        settings_path.unlink()

    config = load_or_create_user_settings(
        config,
        settings_path,
        prompt_if_missing=not args.no_wizard,
    )
    if args.dry_run:
        config.setdefault("monitoring", {})["dry_run"] = True
    if args.no_scan:
        config.setdefault("runtime", {})["no_scan"] = True

    monitoring = config.get("monitoring", {})
    workspace_dir = resolve_app_path(monitoring.get("workspace_dir", "./workspace"))
    db_path = resolve_app_path(config.get("database", {}).get("sqlite_path", "./db/briner.db"))
    monitoring["workspace_dir"] = str(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    poll_interval = monitoring.get("poll_interval", 120)
    mode = monitoring.get("mode", "interval")
    dry_run = monitoring.get("dry_run", False)

    logger.info("Modo activo: %s", mode)
    logger.info("Carpeta monitoreada: %s", workspace_dir)
    logger.info("Intervalo efectivo: %s segundo(s)", poll_interval)
    logger.info("Dry-run: %s", dry_run)

    db_manager = DatabaseManager(str(db_path))
    ignored_filenames = {
        name.casefold()
        for name in monitoring.get("ignored_filenames", [".keep", "desktop.ini"])
    }
    db_manager.cleanup_missing_or_ignored(ignored_filenames)
    db_manager.cleanup_pending_outside_scan_scope(
        workspace_dir,
        recursive=monitoring.get("recursive", False),
    )

    if args.metrics:
        print(json.dumps(db_manager.get_metrics(), indent=2, sort_keys=True))
        return

    if args.undo_last:
        from modules.history import undo_last_move

        print(undo_last_move(db_manager, workspace_dir, dry_run=dry_run))
        return

    from core.agent_orchestrator import BrinerOrchestrator

    orchestrator = BrinerOrchestrator(config=config, db_manager=db_manager)

    try:
        if mode == "realtime":
            _run_realtime_loop(orchestrator, db_manager, workspace_dir, config, args.once)
        else:
            _run_interval_loop(orchestrator, db_manager, workspace_dir, config, poll_interval, args.once)
    except KeyboardInterrupt:
        logger.info("Briner se ha detenido correctamente por orden del usuario.")


if __name__ == "__main__":
    main()
