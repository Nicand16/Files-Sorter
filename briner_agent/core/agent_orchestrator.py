import json
import logging
import re
import threading
from pathlib import Path

try:
    from langgraph.prebuilt import create_react_agent
except ImportError:
    create_react_agent = None

from core.llm_engine import get_llm
from modules.crud_executor import consume_thread_moves, move_file_secure
from modules.rules_engine import build_taxonomy_prompt, classify_file

logger = logging.getLogger(__name__)

# Extensiones cuyo contenido puede ayudar al LLM a clasificar
_BATCH_READABLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".txt", ".csv", ".md", ".json", ".log", ".yaml", ".yml", ".xml",
}
# Chars de preview por archivo en llamadas por lote (mucho menor que el modo individual)
_BATCH_CONTENT_MAX_CHARS = 300


def _resolve_workspace(base_dir: Path, workspace_value: str | Path) -> Path:
    path = Path(workspace_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


class BrinerOrchestrator:
    """
    Orquestador principal del agente Briner.

    Flujo de procesamiento en 3 fases:
      1. Reglas deterministicas (sin API) — extension/keyword → movimiento directo.
      2. Clasificacion por lote (1 API call para todos los archivos ambiguos del ciclo).
      3. Fallback ReAct por archivo — solo si el lote falla.
    """

    def __init__(self, config: dict, db_manager):
        self.config = config
        self.db = db_manager
        base_dir = Path(__file__).resolve().parents[1]
        workspace_rel_dir = config.get("monitoring", {}).get("workspace_dir", "./workspace")
        self.workspace_root = _resolve_workspace(base_dir, workspace_rel_dir)
        self.dry_run = config.get("monitoring", {}).get("dry_run", config.get("app", {}).get("dry_run", False))
        self.destination_aliases = config.get("monitoring", {}).get("destination_aliases", {})
        self.max_files_per_cycle = max(1, int(config.get("processing", {}).get("max_files_per_cycle", 25)))
        self.llm_batch_size = max(1, int(config.get("processing", {}).get("llm_batch_size", 15)))
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

    # ------------------------------------------------------------------ #
    # Fase 1: reglas deterministicas                                       #
    # ------------------------------------------------------------------ #

    def _process_with_rule(self, filepath: str, filename: str, extension: str | None) -> bool:
        """Intenta clasificar con reglas deterministicas. Retorna True si fue manejado."""
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
            return True

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
        return True

    # ------------------------------------------------------------------ #
    # Helpers de movimiento                                                #
    # ------------------------------------------------------------------ #

    def _apply_move(self, filepath: str, category: str, decision_source: str, reason: str):
        """Mueve un archivo a la categoria indicada y registra el evento en DB."""
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
            decision_source=decision_source,
            action="move",
            old_path=move_result.get("old_path", filepath),
            new_path=move_result.get("new_path"),
            category=category,
            reason=reason,
            confidence=None,
            dry_run=move_result.get("dry_run", False),
        )
        self.db.log_action(filepath, f"{decision_source}_move", move_result["message"])
        if move_result.get("dry_run"):
            logger.info("Dry-run: %s permanece pendiente.", Path(filepath).name)
        else:
            self.db.update_file_path(filepath, move_result["new_path"], "processed")
        logger.info(move_result["message"])

    def _move_to_fallback_category(self, filepath: str, category: str, reason: str):
        self._apply_move(filepath, category, "system", reason)

    # ------------------------------------------------------------------ #
    # Fase 2: clasificacion por lote                                       #
    # ------------------------------------------------------------------ #

    def _classify_batch_with_llm(self, files: list[dict]) -> list[dict] | None:
        """
        Clasifica un lote de archivos ambiguos en una sola llamada al LLM.
        Pre-lee contenido de documentos localmente para incluirlo en el prompt.
        Retorna list[{filepath, category}] o None si falla.
        """
        from modules.multimodal_parser import extract_document_content

        file_infos = []
        for f in files:
            info = {"filepath": f["filepath"], "filename": f["filename"]}
            ext = (f.get("extension") or "").lower()
            if ext in _BATCH_READABLE_EXTENSIONS and Path(f["filepath"]).exists():
                try:
                    info["content_preview"] = extract_document_content(f["filepath"], _BATCH_CONTENT_MAX_CHARS)
                except Exception:
                    pass
            file_infos.append(info)

        taxonomy = build_taxonomy_prompt(self.config)
        files_json = json.dumps(file_infos, ensure_ascii=False, indent=2)

        prompt = (
            "Eres un clasificador de archivos. Clasifica cada archivo segun la taxonomia.\n"
            "Responde EXCLUSIVAMENTE con un JSON array valido, sin texto adicional ni bloques markdown.\n\n"
            f"Taxonomia:\n{taxonomy}\n\n"
            "Formato de respuesta (un objeto por archivo):\n"
            '[{"filepath": "<ruta exacta>", "category": "<categoria de la taxonomia o Varios>"}]\n\n'
            f"Archivos a clasificar:\n{files_json}"
        )

        try:
            response = self.llm.invoke(prompt)
            text = response.content.strip()
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                logger.warning("Batch LLM no retorno JSON valido. Respuesta: %.200s", text)
                return None
            results = json.loads(match.group())
            if not isinstance(results, list):
                return None
            logger.info("Batch LLM clasifico %d/%d archivos en una sola llamada.", len(results), len(files))
            return results
        except Exception as e:
            logger.error("Error en clasificacion por lote: %s", e)
            return None

    # ------------------------------------------------------------------ #
    # Fase 3: fallback ReAct individual                                    #
    # ------------------------------------------------------------------ #

    def _process_file_with_agent(self, filepath: str, filename: str) -> str:
        """Procesa un archivo con el agente ReAct. El path debe estar ya claimed."""
        logger.info("Fallback ReAct para archivo ambiguo: %s", filename)
        prompt_input = (
            "Nuevo archivo detectado:\n"
            f"Ruta absoluta: '{filepath}'\n"
            f"Nombre: '{filename}'\n"
            "Por favor, analiza el archivo (si es posible) y ejecuta la accion "
            "(tool) mas apropiada para organizarlo o procesarlo inmediatamente."
        )
        try:
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
                    reason="Movimiento ejecutado por agente LLM (fallback individual).",
                    confidence=None,
                    dry_run=last_move.get("dry_run", False),
                )
                self.db.log_action(filepath, "llm_move", last_move["message"])
                if not last_move.get("dry_run"):
                    self.db.update_file_path(filepath, last_move["new_path"], "processed")
            else:
                self.db.update_file_status(filepath, "processed")
                self.db.log_action(filepath, "llm_analysis", "Analisis preliminar completado.")
            return "processed"
        except Exception as e:
            logger.error("Error en agente ReAct para %s: %s", filename, e)
            self.db.update_file_status(filepath, "error")
            return "error"

    # ------------------------------------------------------------------ #
    # Procesamiento de archivos ambiguos (fases 2 + 3)                    #
    # ------------------------------------------------------------------ #

    def _process_ambiguous_batch(self, files: list[dict], result: dict):
        """
        Intenta clasificar el chunk con una sola llamada LLM.
        Si falla, usa el agente ReAct por archivo como fallback.
        Libera los paths reclamados al terminar.
        """
        if self.llm:
            classifications = self._classify_batch_with_llm(files)
            if classifications is not None:
                by_path = {c["filepath"]: c.get("category", "Varios") for c in classifications if "filepath" in c}
                for f in files:
                    filepath = f["filepath"]
                    category = by_path.get(filepath, "Varios")
                    try:
                        self._apply_move(filepath, category, "llm_batch", "Clasificacion en lote por LLM.")
                        result["processed"] += 1
                    except Exception as e:
                        logger.error("Error aplicando movimiento de lote para %s: %s", f["filename"], e)
                        self.db.update_file_status(filepath, "error")
                        result["errors"] += 1
                    finally:
                        self._release_path(filepath)
                return

        # Fallback: archivo por archivo con ReAct (o Varios si no hay LLM)
        for f in files:
            filepath = f["filepath"]
            try:
                if self.agent:
                    status = self._process_file_with_agent(filepath, f["filename"])
                    if status == "processed":
                        result["processed"] += 1
                    else:
                        result["errors"] += 1
                else:
                    self._apply_move(filepath, "Varios", "system", "Sin agente LLM disponible.")
                    result["processed"] += 1
            except Exception as e:
                logger.error("Error en fallback individual para %s: %s", f["filename"], e)
                self.db.update_file_status(filepath, "error")
                result["errors"] += 1
            finally:
                self._release_path(filepath)

    # ------------------------------------------------------------------ #
    # Control de concurrencia                                              #
    # ------------------------------------------------------------------ #

    def _claim_path(self, filepath: str) -> bool:
        with self._active_paths_lock:
            if filepath in self._active_paths:
                return False
            self._active_paths.add(filepath)
            return True

    def _release_path(self, filepath: str):
        with self._active_paths_lock:
            self._active_paths.discard(filepath)

    # ------------------------------------------------------------------ #
    # Punto de entrada del ciclo de procesamiento                          #
    # ------------------------------------------------------------------ #

    def process_pending_files(self):
        """Consulta la BD por archivos pendientes y los procesa en 3 fases."""
        pending_files = self.db.get_pending_files(limit=self.max_files_per_cycle)
        result = {"pending": len(pending_files), "processed": 0, "errors": 0, "skipped": 0}

        if not pending_files:
            return result

        logger.info("Orquestador detecto %s archivo(s) pendiente(s). Procesando...", len(pending_files))

        # Fase 1: reglas deterministicas — sin API, rapido
        ambiguous = []
        for file_record in pending_files:
            filepath = file_record["filepath"]
            filename = file_record["filename"]
            if not self._claim_path(filepath):
                logger.debug("Archivo ya en procesamiento: %s", filename)
                result["skipped"] += 1
                continue
            try:
                rule_result = self._process_with_rule(filepath, filename, file_record.get("extension"))
                if rule_result:
                    result["processed"] += 1
                    self._release_path(filepath)
                else:
                    ambiguous.append(file_record)  # path sigue claimed hasta el lote
            except Exception as e:
                logger.error("Error en regla para %s: %s", filename, e)
                self.db.update_file_status(filepath, "error")
                self._release_path(filepath)
                result["errors"] += 1

        if not ambiguous:
            return result

        logger.info(
            "%d archivo(s) ambiguo(s) → clasificacion por lote (chunks de %d).",
            len(ambiguous),
            self.llm_batch_size,
        )

        # Fases 2+3: lote LLM con fallback ReAct
        for i in range(0, len(ambiguous), self.llm_batch_size):
            chunk = ambiguous[i : i + self.llm_batch_size]
            self._process_ambiguous_batch(chunk, result)

        return result
