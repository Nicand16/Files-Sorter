import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from langgraph.prebuilt import create_react_agent
except ImportError:
    create_react_agent = None

from core.llm_engine import get_llm
from modules.crud_executor import consume_thread_moves, move_file_secure
from modules.rules_engine import build_taxonomy_prompt, classify_file

logger = logging.getLogger(__name__)


def _resolve_workspace(base_dir: Path, workspace_value: str | Path) -> Path:
    path = Path(workspace_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


class BrinerOrchestrator:
    """
    Orquestador principal del agente Briner.
    Enruta primero por reglas deterministicas y usa el LLM solo para casos ambiguos.
    """

    def __init__(self, config: dict, db_manager):
        self.config = config
        self.db = db_manager
        base_dir = Path(__file__).resolve().parents[1]
        workspace_rel_dir = config.get("monitoring", {}).get("workspace_dir", "./workspace")
        self.workspace_root = _resolve_workspace(base_dir, workspace_rel_dir)
        self.dry_run = config.get("monitoring", {}).get("dry_run", config.get("app", {}).get("dry_run", False))
        self.destination_aliases = config.get("monitoring", {}).get("destination_aliases", {})
        self.max_workers = max(1, int(config.get("processing", {}).get("max_workers", 1)))
        self.max_files_per_cycle = max(1, int(config.get("processing", {}).get("max_files_per_cycle", 25)))
        self._active_paths: set[str] = set()
        self._active_paths_lock = threading.Lock()
        self.llm = get_llm(config)
        self.agent = self._initialize_agent()

    def _initialize_agent(self):
        if not create_react_agent:
            logger.warning("LangGraph no esta instalado. Briner correra solo con reglas y fallback local.")
            return None
        if not self.llm:
            logger.error("Orquestador no pudo arrancar el Agente: Motor LLM no disponible.")
            return None

        from modules.crud_executor import get_crud_tools
        from modules.multimodal_parser import get_parser_tools

        self.tools = get_crud_tools(self.workspace_root, self.dry_run, self.destination_aliases) + get_parser_tools()

        taxonomy_prompt = build_taxonomy_prompt(self.config)
        system_prompt = f"""Eres Briner, un agente de IA autonomo experto en la gestion inteligente de archivos.
Tu mision es organizar el directorio de trabajo del usuario siguiendo ESTRICTAMENTE esta taxonomia:

{taxonomy_prompt}

REGLAS DE OPERACION:
- IGNORAR archivos "desktop.ini" (puedes usar delete_file para borrarlos, pero no los muevas a Varios).
- Usa 'analyze_document_content' si el nombre es ambiguo, pero da prioridad a las palabras clave listadas.
- Llama a 'move_file' usando EXACTAMENTE la ruta de la categoria como 'destination_folder_name' (ej: "Universidad y Estudio/Actividades y Tareas").
- NUNCA pidas confirmacion. Usa la herramienta 'move_file' para categorizar el archivo inmediatamente.
"""
        return create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=system_prompt,
        )

    def _process_with_rule(self, filepath: str, filename: str, extension: str | None) -> bool:
        decision = classify_file(filename, extension, self.config)
        if not decision:
            return False

        if decision.action == "ignore":
            self.db.log_classification_event(
                filepath=filepath,
                decision_source="rule",
                action="ignore",
                old_path=filepath,
                reason=decision.reason,
                confidence=decision.confidence,
                dry_run=self.dry_run,
            )
            self.db.update_file_status(filepath, "processed")
            return "processed"

        move_result = move_file_secure(
            source_path=filepath,
            destination_folder_name=decision.category or "Varios",
            workspace_root=self.workspace_root,
            dry_run=self.dry_run,
            destination_aliases=self.destination_aliases,
        )
        if not move_result["ok"]:
            raise RuntimeError(move_result["message"])

        self.db.log_classification_event(
            filepath=filepath,
            decision_source="rule",
            action="move",
            old_path=move_result.get("old_path", filepath),
            new_path=move_result.get("new_path"),
            category=decision.category,
            reason=decision.reason,
            confidence=decision.confidence,
            dry_run=move_result.get("dry_run", False),
        )
        self.db.log_action(filepath, "rule_move", move_result["message"])
        if move_result.get("dry_run"):
            logger.info("Dry-run activo: %s permanece pendiente para ejecucion real futura.", filename)
        else:
            self.db.update_file_path(filepath, move_result["new_path"], "processed")
        logger.info(move_result["message"])
        return "processed"

    def _move_to_fallback_category(self, filepath: str, category: str, reason: str):
        move_result = move_file_secure(
            source_path=filepath,
            destination_folder_name=category,
            workspace_root=self.workspace_root,
            dry_run=self.dry_run,
            destination_aliases=self.destination_aliases,
        )
        if not move_result["ok"]:
            raise RuntimeError(move_result["message"])

        self.db.log_classification_event(
            filepath=filepath,
            decision_source="system",
            action="move",
            old_path=move_result.get("old_path", filepath),
            new_path=move_result.get("new_path"),
            category=category,
            reason=reason,
            confidence=0.5,
            dry_run=move_result.get("dry_run", False),
        )
        self.db.log_action(filepath, "fallback_move", move_result["message"])
        if move_result.get("dry_run"):
            logger.info("Dry-run activo: %s permanece pendiente para ejecucion real futura.", Path(filepath).name)
        else:
            self.db.update_file_path(filepath, move_result["new_path"], "processed")
        logger.info(move_result["message"])

    def _claim_path(self, filepath: str) -> bool:
        with self._active_paths_lock:
            if filepath in self._active_paths:
                return False
            self._active_paths.add(filepath)
            return True

    def _release_path(self, filepath: str):
        with self._active_paths_lock:
            self._active_paths.discard(filepath)

    def _process_file_record(self, file_record: dict) -> str:
        filepath = file_record["filepath"]
        filename = file_record["filename"]
        extension = file_record.get("extension")

        if not self._claim_path(filepath):
            logger.debug("Archivo ya en procesamiento: %s", filepath)
            return "skipped"

        try:
            logger.info("Analizando archivo: %s", filename)

            try:
                rule_result = self._process_with_rule(filepath, filename, extension)
                if rule_result:
                    return rule_result

                if self.agent:
                    logger.info("Invocando LLM para archivo ambiguo: %s", filename)
                    prompt_input = (
                        "Nuevo archivo detectado:\n"
                        f"Ruta absoluta: '{filepath}'\n"
                        f"Nombre: '{filename}'\n"
                        "Por favor, analiza el archivo (si es posible) y ejecuta la accion "
                        "(tool) mas apropiada para organizarlo o procesarlo inmediatamente."
                    )

                    consume_thread_moves()
                    response = self.agent.invoke({"messages": [("user", prompt_input)]})
                    resultado = response["messages"][-1].content
                    logger.info("[Respuesta de Briner para %s]:\n%s", filename, resultado)
                    tool_moves = consume_thread_moves()
                    if tool_moves:
                        last_move = tool_moves[-1]
                        self.db.log_classification_event(
                            filepath=filepath,
                            decision_source="llm",
                            action="move",
                            old_path=last_move.get("old_path", filepath),
                            new_path=last_move.get("new_path"),
                            category=None,
                            reason="Movimiento ejecutado por agente LLM.",
                            confidence=None,
                            dry_run=last_move.get("dry_run", False),
                        )
                        self.db.log_action(filepath, "llm_move", last_move["message"])
                        if last_move.get("dry_run"):
                            logger.info("Dry-run activo: %s permanece pendiente para ejecucion real futura.", filename)
                        else:
                            self.db.update_file_path(filepath, last_move["new_path"], "processed")
                        return "processed"
                else:
                    self._move_to_fallback_category(
                        filepath,
                        "Varios",
                        "Archivo ambiguo movido a fallback porque el agente LLM no esta disponible.",
                    )
                    return "processed"

                self.db.update_file_status(filepath, "processed")
                self.db.log_action(filepath, "llm_analysis", "Analisis preliminar completado.")
                self.db.log_classification_event(
                    filepath=filepath,
                    decision_source="llm",
                    action="analysis",
                    old_path=filepath,
                    reason="Procesado por agente LLM; ver actions_log para respuesta textual.",
                    confidence=None,
                    dry_run=self.dry_run,
                )
                return "processed"

            except Exception as e:
                logger.error("Error procesando %s: %s", filename, e)
                self.db.update_file_status(filepath, "error")
                return "error"
        finally:
            self._release_path(filepath)

    def process_pending_files(self):
        """Consulta la BD por archivos pendientes y los procesa."""
        pending_files = self.db.get_pending_files(limit=self.max_files_per_cycle)
        result = {"pending": len(pending_files), "processed": 0, "errors": 0, "skipped": 0}

        if not pending_files:
            return result

        logger.info("Orquestador detecto %s archivo(s) pendiente(s). Procesando...", len(pending_files))

        if self.max_workers == 1 or len(pending_files) == 1:
            for file_record in pending_files:
                status = self._process_file_record(file_record)
                if status == "error":
                    result["errors"] += 1
                elif status == "skipped":
                    result["skipped"] += 1
                else:
                    result["processed"] += 1
            return result

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._process_file_record, file_record) for file_record in pending_files]
            for future in as_completed(futures):
                status = future.result()
                if status == "error":
                    result["errors"] += 1
                elif status == "skipped":
                    result["skipped"] += 1
                else:
                    result["processed"] += 1
        return result
