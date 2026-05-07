import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import yaml

CODE_DIR = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else CODE_DIR
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", CODE_DIR)).resolve()


def get_briner_data_dir(*, is_frozen: bool, home: Path | None = None) -> Path:
    """Return a writable app-data directory for Briner on any OS."""
    home_dir = Path.home() if home is None else Path(home)
    override = os.environ.get("BRINER_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if is_frozen:
        appdata = os.environ.get("APPDATA")
        if appdata:
            return (Path(appdata) / "Briner").resolve()
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return (Path(xdg_data) / "Briner").resolve()
        return (home_dir / ".local" / "share" / "Briner").resolve()

    return CODE_DIR


# State files (settings, db, logs) go to per-user app data when frozen so both exes share them.
APPDATA_DIR = get_briner_data_dir(is_frozen=IS_FROZEN)
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from core.settings_manager import load_or_create_user_settings, normalize_monitoring_config
from db.database_manager import DatabaseManager
from modules.periodic_scanner import scan_directory_once

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

LOG_DIR = APPDATA_DIR / "logs"
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
    # When frozen, check APPDATA first (shared between Briner and BrinerBackground), then next to the exe.
    env_paths = [APPDATA_DIR / ".env", APP_DIR / ".env"] if IS_FROZEN else [APP_DIR / ".env"]

    if load_dotenv:
        for ep in env_paths:
            load_dotenv(ep, override=False)
        load_dotenv()

    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        env_logger.info("Credenciales IA cargadas.")
        return

    for env_path in env_paths:
        if not env_path.exists():
            continue
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
                        env_logger.info("Credenciales IA cargadas manualmente desde .env en %s.", env_path.parent)
                        return
                    continue
                os.environ["GOOGLE_API_KEY"] = value
                env_logger.info("API key cargada desde .env en formato simple.")
                return
        except OSError as exc:
            env_logger.warning("No se pudo leer .env en %s: %s", env_path, exc)


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


def _find_background_exe() -> Path | None:
    """Localiza BrinerBackground.exe junto a Briner.exe cuando corre como ejecutable."""
    if not IS_FROZEN:
        return None
    candidate = Path(sys.executable).parent.parent / "BrinerBackground" / "BrinerBackground.exe"
    return candidate if candidate.exists() else None


def _install_startup_shortcut() -> bool:
    """Crea el acceso directo en la carpeta Startup de Windows para BrinerBackground.exe."""
    bg_exe = _find_background_exe()
    if not bg_exe:
        logger.warning("BrinerBackground.exe no encontrado. Instala el inicio automatico manualmente.")
        return False

    bg_exe_str = str(bg_exe).replace("'", "''")
    working_dir = str(bg_exe.parent).replace("'", "''")
    ps_cmd = (
        "$startup = [Environment]::GetFolderPath('Startup'); "
        "$lnk = Join-Path $startup 'Briner.lnk'; "
        "$shell = New-Object -ComObject WScript.Shell; "
        "$link = $shell.CreateShortcut($lnk); "
        f"$link.TargetPath = '{bg_exe_str}'; "
        f"$link.WorkingDirectory = '{working_dir}'; "
        "$link.Arguments = '--no-wizard'; "
        "$link.WindowStyle = 7; "
        "$link.Save(); "
        "Write-Output 'SHORTCUT_OK'"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if "SHORTCUT_OK" in result.stdout:
            logger.info("Acceso directo de inicio creado: %s", bg_exe)
            return True
        logger.warning("PowerShell no confirmo el acceso directo. stderr=%s", result.stderr.strip())
        return False
    except Exception as exc:
        logger.error("Error al crear acceso directo de inicio: %s", exc)
        return False


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Briner file organizer")
    parser.add_argument("--once", action="store_true", help="Escanea y procesa una sola vez.")
    parser.add_argument("--no-scan", action="store_true", help="No registra archivos existentes al arrancar.")
    parser.add_argument("--dry-run", action="store_true", help="Propone movimientos sin tocar archivos.")
    parser.add_argument("--metrics", action="store_true", help="Imprime metricas basicas y termina.")
    parser.add_argument("--undo-last", action="store_true", help="Deshace el ultimo movimiento real registrado.")
    parser.add_argument("--setup", action="store_true", help="Fuerza el wizard de configuracion inicial.")
    parser.add_argument("--no-wizard", action="store_true", help="Usa config/defaults sin pedir settings iniciales.")
    parser.add_argument("--watch-dir", default=None, help="Carpeta a monitorear (omite el wizard interactivo).")
    parser.add_argument("--api-key", default=None, help="API key de Google Gemini a guardar en APPDATA.")
    return parser


def _run_interval_loop(orchestrator, db_manager, workspace_dir: Path, config: dict, poll_interval: int, once: bool, stop_event=None, force_scan_event=None, tray=None):
    logger.info("Modo interval: ejecutando escaneo inicial inmediato.")
    processed_total = 0
    errors_total = 0
    while True:
        if stop_event and stop_event.is_set():
            break
        if tray:
            tray.update_stats(status="Procesando...", pending=0, processed_total=processed_total, errors_total=errors_total, processing=True)
        try:
            detected = scan_directory_once(workspace_dir, db_manager, config)
            if tray:
                result = orchestrator.process_pending_files(
                    tray=tray,
                    base_processed_total=processed_total,
                    base_errors_total=errors_total,
                )
            else:
                result = orchestrator.process_pending_files()
            processed_total += result.get("processed", 0)
            errors_total += result.get("errors", 0)
            last_cycle = datetime.now().strftime("%H:%M:%S")
            logger.info(
                "Ciclo interval terminado. detectados=%s procesados=%s errores=%s",
                detected,
                result.get("processed", 0),
                result.get("errors", 0),
            )
            if tray:
                tray.update_stats(
                    status="Corriendo",
                    pending=result.get("pending", 0),
                    processed_total=processed_total,
                    errors_total=errors_total,
                    last_cycle=last_cycle,
                )
        except Exception as exc:
            logger.exception("Error inesperado en ciclo interval; el servicio continuara: %s", exc)
            if tray:
                tray.update_stats(
                    status="Error en ciclo",
                    processed_total=processed_total,
                    errors_total=errors_total,
                    error=True,
                    error_message=str(exc),
                )

        if once:
            return
        logger.info("Modo interval: esperando %s segundo(s) para el siguiente escaneo.", poll_interval)
        if tray:
            tray.update_stats(status="Esperando...", pending=0, processed_total=processed_total, errors_total=errors_total)
        deadline = time.monotonic() + poll_interval
        while time.monotonic() < deadline:
            if stop_event and (stop_event.is_set() or force_scan_event.is_set()):
                break
            time.sleep(1)
        if force_scan_event:
            force_scan_event.clear()
        if stop_event and stop_event.is_set():
            break


def _run_realtime_loop(orchestrator, db_manager, workspace_dir: Path, config: dict, once: bool, stop_event=None, tray=None):
    from modules.file_watcher import DirectoryMonitor

    monitor = DirectoryMonitor(watch_directory=str(workspace_dir), db_manager=db_manager, config=config)
    if not config.get("runtime", {}).get("no_scan", False):
        monitor.scan_existing_files()

    if once:
        orchestrator.process_pending_files()
        return

    processed_total = 0
    errors_total = 0
    monitor.start()
    if tray:
        tray.update_stats(status="Corriendo (tiempo real)", processed_total=0, errors_total=0)
    try:
        while not (stop_event and stop_event.is_set()):
            try:
                if tray:
                    result = orchestrator.process_pending_files(
                        tray=tray,
                        base_processed_total=processed_total,
                        base_errors_total=errors_total,
                    )
                else:
                    result = orchestrator.process_pending_files()
                processed_total += result.get("processed", 0)
                errors_total += result.get("errors", 0)
                if result.get("processed", 0) > 0:
                    last_cycle = datetime.now().strftime("%H:%M:%S")
                    logger.info(
                        "Ciclo realtime terminado. procesados=%s errores=%s",
                        result.get("processed", 0),
                        result.get("errors", 0),
                    )
                    if tray:
                        tray.update_stats(
                            status="Corriendo (tiempo real)",
                            pending=result.get("pending", 0),
                            processed_total=processed_total,
                            errors_total=errors_total,
                            last_cycle=last_cycle,
                        )
            except Exception as exc:
                logger.exception("Error inesperado en ciclo realtime; el servicio continuara: %s", exc)
                if tray:
                    tray.update_stats(
                        status="Error en ciclo",
                        processed_total=processed_total,
                        errors_total=errors_total,
                        error=True,
                        error_message=str(exc),
                    )
            if stop_event:
                stop_event.wait(timeout=3)
            else:
                time.sleep(3)
    finally:
        monitor.stop()


def _run_startup_checks(workspace_dir: Path, orchestrator, tray=None) -> bool:
    errors = []

    if not workspace_dir.exists():
        errors.append(f"La carpeta monitoreada no existe: {workspace_dir}")
    elif not workspace_dir.is_dir():
        errors.append(f"La ruta monitoreada no es una carpeta: {workspace_dir}")

    has_api_key = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    if not has_api_key:
        errors.append("Falta GOOGLE_API_KEY/GEMINI_API_KEY en el entorno o .env.")
    elif not orchestrator.llm:
        errors.append("La API key existe, pero el motor LLM no pudo inicializarse.")
    else:
        try:
            response = orchestrator._invoke_llm_with_timeout("Responde exactamente: OK", timeout_seconds=60)
            logger.info("Verificacion LLM de arranque OK: %.80s", getattr(response, "content", ""))
            orchestrator._record_api_success()
        except Exception as exc:
            errors.append(f"No hay conexion funcional con Gemini al arrancar: {exc}")

    if errors:
        message = " | ".join(errors)
        logger.error("Verificacion de arranque fallida: %s", message)
        if tray and hasattr(tray, "set_error"):
            tray.set_error(message, notify=True)
        return False

    logger.info("Verificacion de arranque completada correctamente.")
    return True


def main():
    args = build_arg_parser().parse_args()
    logger.info("Iniciando Briner - Agente Autonomo de Gestion de Archivos")

    config_path = APP_DIR / "config.yaml"
    if not config_path.exists():
        config_path = RESOURCE_DIR / "config.yaml"
    config = normalize_monitoring_config(load_config(config_path))

    # Settings path: shared via APPDATA when frozen so both exes see the same config.
    settings_path = APPDATA_DIR / "user_settings.json"
    settings_existed = settings_path.exists()
    if args.setup and settings_existed:
        settings_path.unlink()
        settings_existed = False

    config = load_or_create_user_settings(
        config,
        settings_path,
        prompt_if_missing=not args.no_wizard,
        default_dir=getattr(args, 'watch_dir', None),
    )

    # Guardar API key en APPDATA si fue provista via --api-key
    if args.api_key:
        env_path = APPDATA_DIR / ".env"
        env_path.write_text(f"GOOGLE_API_KEY={args.api_key}\n", encoding="utf-8")
        os.environ["GOOGLE_API_KEY"] = args.api_key
        logger.info("API key guardada en %s", env_path)

    # On first-time setup (frozen exe), auto-install Windows startup shortcut and exit.
    if IS_FROZEN and not settings_existed and settings_path.exists():
        logger.info("Primera configuracion detectada. Instalando inicio automatico...")
        ok = _install_startup_shortcut()
        if ok:
            print("\n  Inicio automatico instalado. Briner se ejecutara al iniciar Windows.")
        else:
            print("\n  No se pudo instalar el inicio automatico.")
            print("  Puedes hacerlo manualmente ejecutando:")
            print("    briner_agent\\scripts\\install_startup.bat")
        if args.setup:
            print("\nConfiguracion completada. Puedes cerrar esta ventana.\n")
            return

    if args.dry_run:
        config.setdefault("monitoring", {})["dry_run"] = True
    if args.no_scan:
        config.setdefault("runtime", {})["no_scan"] = True

    monitoring = config.get("monitoring", {})
    workspace_dir = resolve_app_path(monitoring.get("workspace_dir", "./workspace"))
    # DB path: APPDATA when frozen (shared), local db folder when running as script.
    if IS_FROZEN:
        db_path = APPDATA_DIR / "briner.db"
    else:
        db_path = resolve_app_path(config.get("database", {}).get("sqlite_path", "./db/briner.db"))
    monitoring["workspace_dir"] = str(workspace_dir)
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

    orchestrator = BrinerOrchestrator(config=config, db_manager=db_manager, workspace_dir=workspace_dir)
    logger.info("=== Briner configuracion activa ===")
    logger.info("Workspace: %s | Existe: %s", workspace_dir, workspace_dir.exists())
    logger.info("Dry-run: %s | Modo: %s | Recursivo: %s", dry_run, mode, monitoring.get("recursive", False))
    logger.info("LLM: %s | Agente ReAct: %s", orchestrator.llm is not None, orchestrator.agent is not None)
    logger.info("===================================")

    stop_event = threading.Event()
    force_scan_event = threading.Event()
    tray = None
    if not args.once:
        try:
            from modules.tray_icon import BrinerTrayIcon
            tray = BrinerTrayIcon(
                workspace_dir=workspace_dir,
                appdata_dir=APPDATA_DIR,
                stop_event=stop_event,
                force_scan_event=force_scan_event,
            )
            tray.start()
            orchestrator.set_tray(tray)
        except Exception as exc:
            logger.warning("No se pudo iniciar el icono de bandeja del sistema: %s", exc)
            tray = None

    _run_startup_checks(workspace_dir, orchestrator, tray=tray)

    try:
        if mode == "realtime":
            _run_realtime_loop(orchestrator, db_manager, workspace_dir, config, args.once, stop_event=stop_event, tray=tray)
        else:
            _run_interval_loop(orchestrator, db_manager, workspace_dir, config, poll_interval, args.once, stop_event=stop_event, force_scan_event=force_scan_event, tray=tray)
    except KeyboardInterrupt:
        logger.info("Briner se ha detenido correctamente por orden del usuario.")
    finally:
        if tray:
            tray.stop()


if __name__ == "__main__":
    main()
