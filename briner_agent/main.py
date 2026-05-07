import yaml
import logging
from pathlib import Path
from dotenv import load_dotenv
from modules.file_watcher import DirectoryMonitor
from db.database_manager import DatabaseManager

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración del sistema de logging principal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BrinerMain")

def load_config(config_path="config.yaml") -> dict:
    """Carga la configuración desde el archivo YAML."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Archivo de configuración no encontrado en {config_path}. Usando valores por defecto.")
        return {}
    
    with open(path, "r", encoding="utf-8") as file:
        try:
            return yaml.safe_load(file)
        except yaml.YAMLError as exc:
            logger.error(f"Error parseando el archivo YAML: {exc}")
            return {}

def main():
    logger.info("Iniciando Briner - Agente Autónomo de Gestión de Archivos")

    # 1. Cargar Configuración
    # Como ejecutamos desde la raíz del proyecto, resolvemos rutas relativas
    base_dir = Path(__file__).parent
    config_path = base_dir / "config.yaml"
    config = load_config(config_path)
    
    workspace_rel_dir = config.get("monitoring", {}).get("workspace_dir", "./workspace")
    workspace_dir = (base_dir / workspace_rel_dir).resolve()
    
    db_rel_path = config.get("database", {}).get("sqlite_path", "./db/briner.db")
    db_path = (base_dir / db_rel_path).resolve()

    # 2. Inicializar Base de Datos (Paso 2)
    db_manager = DatabaseManager(str(db_path))

    # 3. Inicializar Orquestador de IA (Paso 3)
    from core.agent_orchestrator import BrinerOrchestrator
    orchestrator = BrinerOrchestrator(config=config, db_manager=db_manager)

    # 4. Inicializar y Arrancar Monitorización
    monitor = DirectoryMonitor(watch_directory=str(workspace_dir), db_manager=db_manager)
    monitor.start()
    
    import time
    try:
        # Bucle principal: El orquestador revisa y procesa archivos pendientes
        while True:
            orchestrator.process_pending_files()
            time.sleep(3) # Pausa entre ciclos de orquestación
    except KeyboardInterrupt:
        logger.info("Briner se ha detenido correctamente por orden del usuario.")
        monitor.stop()

if __name__ == "__main__":
    main()
