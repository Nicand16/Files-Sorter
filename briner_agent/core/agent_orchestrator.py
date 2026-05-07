import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

try:
    from langgraph.prebuilt import create_react_agent
except ImportError:
    create_react_agent = None

from core.llm_engine import get_llm
from infra.metrics import (
    M_CACHE_HITS,
    M_CACHE_MISSES,
    M_CYCLE_DURATION,
    M_FILES_ERRORS,
    M_FILES_PROCESSED,
    M_LLM_CALL,
    M_LLM_CALLS_TOTAL,
    M_LLM_FAILURES_TOTAL,
    M_PHASE1_DURATION,
    M_PHASE2_DURATION,
    M_PHASE3_DURATION,
    metrics,
)
from modules.crud_executor import consume_thread_moves, move_file_secure
from modules.rules_engine import build_taxonomy_prompt, classify_file
from runtime.event_bus import FileEvent, FileState, bus

logger = logging.getLogger(__name__)

# Extensiones cuyo contenido puede ayudar al LLM a clasificar
_BATCH_READABLE_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".txt", ".csv", ".md", ".json", ".log", ".yaml", ".yml", ".xml",
}
# Chars de preview por archivo en llamadas por lote (mucho menor que el modo individual)
_BATCH_CONTENT_MAX_CHARS = 300


class MoveFailureError(RuntimeError):
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


def _resolve_workspace(workspace_value: str | Path) -> Path:
    path = Path(workspace_value).expanduser()
    return path.resolve()


class BrinerOrchestrator:
    """
    Orquestador principal del agente Briner.

    Flujo de procesamiento en 3 fases:
      1. Reglas deterministicas (sin API) — extension/keyword → movimiento directo.
      2. Clasificacion por lote (1 API call para todos los archivos ambiguos del ciclo).
      3. Fallback ReAct por archivo — solo si el lote falla.
    """

    def __init__(self, config: dict, db_manager, workspace_dir=None):
        self.config = config
        self.db = db_manager
        if workspace_dir is not None:
            self.workspace_root = Path(workspace_dir).expanduser().resolve()
            workspace_source = "main"
        else:
            workspace_rel_dir = config.get("monitoring", {}).get("workspace_dir", "./workspace")
            self.workspace_root = _resolve_workspace(workspace_rel_dir)
            workspace_source = "config"
        self.config.setdefault("monitoring", {})["workspace_dir"] = str(self.workspace_root)
        logger.info(
            "Workspace root: %s (source=%s, existe=%s)",
            self.workspace_root,
            workspace_source,
            self.workspace_root.exists(),
        )
        self.dry_run = config.get("monitoring", {}).get("dry_run", config.get("app", {}).get("dry_run", False))
        self.destination_aliases = config.get("monitoring", {}).get("destination_aliases", {})
        self.max_files_per_cycle = max(1, int(config.get("processing", {}).get("max_files_per_cycle", 25)))
        self.llm_batch_size = max(1, int(config.get("processing", {}).get("llm_batch_size", 15)))
        self.llm_timeout_seconds = int(config.get("processing", {}).get("llm_timeout_seconds", 60))
        self._active_paths: set[str] = set()
        self._active_paths_lock = threading.Lock()
        self._tray = None
        self._consecutive_api_failures = 0
        # Lazy LLM init: do NOT call get_llm() at construction time
        self._llm_obj = None
        self._llm_initialized = False
        self._llm_init_lock = threading.Lock()
        self.agent = None  # set lazily when LLM first initializes
        # Circuit breaker replaces the bare consecutive-failures counter
        from runtime.circuit_breaker import CircuitBreaker
        cb_threshold = int(config.get("processing", {}).get("circuit_breaker_threshold", 3))
        cb_recovery = float(config.get("processing", {}).get("circuit_breaker_recovery_seconds", 60.0))
        self._circuit = CircuitBreaker("gemini", cb_threshold, cb_recovery)
        # Decision cache: avoids redundant LLM calls for files with same extension+stem pattern
        from classifiers.decision_cache import DecisionCache
        cache_size = int(config.get("processing", {}).get("decision_cache_size", 200))
        cache_ttl = float(config.get("processing", {}).get("decision_cache_ttl_seconds", 3600.0))
        self._cache = DecisionCache(max_size=cache_size, ttl_seconds=cache_ttl)

    @property
    def llm(self):
        if self._llm_initialized:
            return self._llm_obj
        with self._llm_init_lock:
            if not self._llm_initialized:
                logger.info("Inicializando LLM (primer uso)...")
                self._llm_obj = get_llm(self.config)
                self._llm_initialized = True
                if self._llm_obj:
                    logger.info("LLM inicializado correctamente.")
                    self.agent = self._initialize_agent()
                else:
                    logger.warning("LLM no disponible (API key ausente o error de init).")
        return self._llm_obj

    def set_tray(self, tray):
        self._tray = tray

    def _emit(self, state: FileState, filepath: str, filename: str, **kwargs):
        bus.publish(FileEvent(state=state, filepath=filepath, filename=filename, **kwargs))

    def _notify_error(self, message: str, notify: bool = True):
        logger.error(message)
        if self._tray and hasattr(self._tray, "set_error"):
            self._tray.set_error(message, notify=notify)

    def _record_api_failure(self, message: str):
        metrics.inc(M_LLM_FAILURES_TOTAL)
        self._consecutive_api_failures += 1
        self._circuit.record_failure(message)
        from runtime.circuit_breaker import CircuitState
        if self._circuit.state == CircuitState.OPEN:
            self._notify_error(
                f"Gemini circuit ABIERTO tras {self._consecutive_api_failures} fallo(s). Ultimo: {message}",
                notify=True,
            )

    def _record_api_success(self):
        self._consecutive_api_failures = 0
        self._circuit.record_success()

    def _invoke_llm_with_timeout(self, prompt, timeout_seconds: int | None = None):
        from runtime.circuit_breaker import CircuitOpenError
        self._circuit.before_call()  # raises CircuitOpenError if OPEN
        timeout = timeout_seconds or self.llm_timeout_seconds
        metrics.inc(M_LLM_CALLS_TOTAL)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="BrinerLLMInvoke")
        future = executor.submit(self.llm.invoke, prompt)
        try:
            with metrics.span(M_LLM_CALL):
                return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            message = f"Timeout de LLM despues de {timeout} segundos."
            self._record_api_failure(message)
            raise TimeoutError(message)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _handle_move_failure(self, filepath: str, move_result: dict):
        message = move_result.get("message", "Error desconocido al mover archivo.")
        if move_result.get("error_code") == "workspace_mismatch":
            self._notify_error(f"Workspace mismatch al mover '{Path(filepath).name}': {message}", notify=True)
        raise MoveFailureError(message, move_result.get("error_code"))

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
        logger.info("Regla para '%s': accion=%s categoria=%s dry_run=%s", filename, decision.action, decision.category, self.dry_run)

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
            self._emit(FileState.IGNORED, filepath, filename, decision_source="rule", reason=decision.reason)
            return True

        move_result = move_file_secure(
            source_path=filepath,
            destination_folder_name=decision.category or "Varios",
            workspace_root=self.workspace_root,
            dry_run=self.dry_run,
            destination_aliases=self.destination_aliases,
        )
        if not move_result["ok"]:
            self._handle_move_failure(filepath, move_result)

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
        self._emit(FileState.MOVED, filepath, filename, category=decision.category, decision_source="rule")
        return True

    # ------------------------------------------------------------------ #
    # Helpers de movimiento                                                #
    # ------------------------------------------------------------------ #

    def _apply_move(self, filepath: str, category: str, decision_source: str, reason: str):
        """Mueve un archivo a la categoria indicada y registra el evento en DB."""
        filename = Path(filepath).name
        move_result = move_file_secure(
            source_path=filepath,
            destination_folder_name=category,
            workspace_root=self.workspace_root,
            dry_run=self.dry_run,
            destination_aliases=self.destination_aliases,
        )
        if not move_result["ok"]:
            self._handle_move_failure(filepath, move_result)

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
            logger.info("Dry-run: %s permanece pendiente.", filename)
        else:
            self.db.update_file_path(filepath, move_result["new_path"], "processed")
        logger.info(move_result["message"])
        self._emit(FileState.MOVED, filepath, filename, category=category, decision_source=decision_source)

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

        def _extract_preview(f):
            info = {"filepath": f["filepath"], "filename": f["filename"]}
            ext = (f.get("extension") or "").lower()
            if ext in _BATCH_READABLE_EXTENSIONS and Path(f["filepath"]).exists():
                try:
                    info["content_preview"] = extract_document_content(f["filepath"], _BATCH_CONTENT_MAX_CHARS)
                except Exception:
                    pass
            return info

        with ThreadPoolExecutor(max_workers=8) as pool:
            file_infos = list(pool.map(_extract_preview, files))

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
            response = self._invoke_llm_with_timeout(prompt, timeout_seconds=60)
            text = response.content.strip()
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                logger.warning("Batch LLM no retorno JSON valido. Respuesta: %.200s", text)
                return None
            results = json.loads(match.group())
            if not isinstance(results, list):
                return None
            self._record_api_success()
            logger.info("Batch LLM clasifico %d/%d archivos en una sola llamada.", len(results), len(files))
            return results
        except TimeoutError as e:
            logger.error("Timeout en clasificacion por lote: %s", e)
            return None
        except Exception as e:
            from runtime.circuit_breaker import CircuitOpenError
            if isinstance(e, CircuitOpenError):
                logger.warning("Batch LLM saltado (circuit ABIERTO): %s", e)
            else:
                logger.error("Error en clasificacion por lote: %s", e)
                self._record_api_failure(str(e))
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
            successful_moves = [move for move in tool_moves if move.get("ok")]
            if successful_moves:
                last_move = successful_moves[-1]
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
                self._record_api_success()
            elif tool_moves:
                self._handle_move_failure(filepath, tool_moves[-1])
            else:
                self.db.update_file_status(filepath, "processed")
                self.db.log_action(filepath, "llm_analysis", "Analisis preliminar completado.")
                self._record_api_success()
            return "processed"
        except MoveFailureError as e:
            logger.error("Movimiento fallido en agente ReAct para %s: %s", filename, e)
            self.db.update_file_status(filepath, "error")
            self._emit(FileState.ERROR, filepath, filename, reason=str(e))
            return "error"
        except Exception as e:
            from runtime.circuit_breaker import CircuitOpenError
            if isinstance(e, CircuitOpenError):
                logger.warning("ReAct saltado (circuit ABIERTO): %s — moviendo a Varios.", e)
                try:
                    self._apply_move(filepath, "Varios", "system", f"Circuit abierto: {e}")
                    return "processed"
                except Exception as e2:
                    logger.error("Fallback a Varios fallo para %s: %s", filename, e2)
            else:
                logger.error("Error en agente ReAct para %s: %s", filename, e)
                self._record_api_failure(str(e))
            self.db.update_file_status(filepath, "error")
            self._emit(FileState.ERROR, filepath, filename, reason=str(e))
            return "error"

    # ------------------------------------------------------------------ #
    # Procesamiento de archivos ambiguos (fases 2 + 3)                    #
    # ------------------------------------------------------------------ #

    def _update_tray_progress(
        self,
        tray,
        status: str,
        result: dict,
        base_processed_total: int,
        base_errors_total: int,
        pending: int = 0,
    ):
        if tray and hasattr(tray, "update_stats"):
            tray.update_stats(
                status=status,
                pending=pending,
                processed_total=base_processed_total + result.get("processed", 0),
                errors_total=base_errors_total + result.get("errors", 0),
                processing=True,
            )

    def _process_ambiguous_batch(
        self,
        files: list[dict],
        result: dict,
        tray=None,
        base_processed_total: int = 0,
        base_errors_total: int = 0,
    ):
        """
        Intenta clasificar el chunk con una sola llamada LLM.
        Consulta el cache de decisiones primero para evitar llamadas redundantes.
        Si el LLM falla, usa el agente ReAct por archivo como fallback.
        Libera los paths reclamados al terminar.
        """
        # --- Decision cache: apply hits immediately, send misses to LLM ---
        cache_hits = []
        cache_misses = []
        for f in files:
            cached = self._cache.get(f["filename"], f.get("extension") or "")
            if cached is not None:
                cache_hits.append((f, cached))
                metrics.inc(M_CACHE_HITS)
            else:
                cache_misses.append(f)
                metrics.inc(M_CACHE_MISSES)

        for f, category in cache_hits:
            filepath = f["filepath"]
            try:
                self._apply_move(filepath, category, "cache", "Categoria del cache de decisiones.")
                result["processed"] += 1
            except Exception as e:
                logger.error("Error aplicando cache hit para %s: %s", f["filename"], e)
                self.db.update_file_status(filepath, "error")
                result["errors"] += 1
                self._emit(FileState.ERROR, filepath, f["filename"], reason=str(e))
            finally:
                self._release_path(filepath)

        if not cache_misses:
            return
        files = cache_misses

        if self.llm:
            self._update_tray_progress(
                tray,
                f"LLM: clasificando {len(files)} ambiguos",
                result,
                base_processed_total,
                base_errors_total,
                pending=len(files),
            )
            classifications = self._classify_batch_with_llm(files)
            if classifications is not None:
                by_path = {c["filepath"]: c.get("category", "Varios") for c in classifications if "filepath" in c}
                successful = 0
                for f in files:
                    filepath = f["filepath"]
                    category = by_path.get(filepath, "Varios")
                    try:
                        self._apply_move(filepath, category, "llm_batch", "Clasificacion en lote por LLM.")
                        self._cache.put(f["filename"], f.get("extension") or "", category, "llm_batch")
                        result["processed"] += 1
                        successful += 1
                    except Exception as e:
                        logger.error("Error aplicando movimiento de lote para %s: %s", f["filename"], e)
                        self.db.update_file_status(filepath, "error")
                        result["errors"] += 1
                        self._emit(FileState.ERROR, filepath, f["filename"], reason=str(e))
                    finally:
                        self._release_path(filepath)
                self._update_tray_progress(
                    tray,
                    f"LLM: {successful}/{len(files)} clasificados",
                    result,
                    base_processed_total,
                    base_errors_total,
                    pending=0,
                )
                return
            self._update_tray_progress(
                tray,
                f"LLM fallo; fallback para {len(files)} archivos",
                result,
                base_processed_total,
                base_errors_total,
                pending=len(files),
            )

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
            except MoveFailureError as e:
                logger.error("Movimiento fallido en fallback individual para %s: %s", f["filename"], e)
                self.db.update_file_status(filepath, "error")
                result["errors"] += 1
                self._emit(FileState.ERROR, filepath, f["filename"], reason=str(e))
            except Exception as e:
                logger.error("Error en fallback individual para %s: %s — moviendo a Varios.", f["filename"], e)
                try:
                    self._apply_move(filepath, "Varios", "system", f"Error LLM: {e}")
                    result["processed"] += 1
                except Exception as e2:
                    logger.error("Fallback a Varios tambien fallo para %s: %s", f["filename"], e2)
                    self.db.update_file_status(filepath, "error")
                    result["errors"] += 1
                    self._emit(FileState.ERROR, filepath, f["filename"], reason=str(e2))
            finally:
                self._release_path(filepath)

        self._update_tray_progress(
            tray,
            f"Fallback: {len(files)} archivos revisados",
            result,
            base_processed_total,
            base_errors_total,
            pending=0,
        )

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

    def process_pending_files(self, tray=None, base_processed_total: int = 0, base_errors_total: int = 0):
        """Consulta la BD por archivos pendientes y los procesa en 3 fases."""
        with metrics.span(M_CYCLE_DURATION):
            return self._process_pending_files_inner(tray, base_processed_total, base_errors_total)

    def _process_pending_files_inner(self, tray=None, base_processed_total: int = 0, base_errors_total: int = 0):
        pending_files = self.db.get_pending_files(limit=self.max_files_per_cycle)
        result = {"pending": len(pending_files), "processed": 0, "errors": 0, "skipped": 0}

        logger.info("Pendientes en BD: %s (limite ciclo: %s)", len(pending_files), self.max_files_per_cycle)
        if not pending_files:
            logger.info("Sin archivos pendientes. Esperando proximo ciclo.")
            return result

        logger.info("Orquestador detecto %s archivo(s) pendiente(s). Procesando...", len(pending_files))

        # Fase 1: reglas deterministicas — sin API, rapido
        ambiguous = []
        with metrics.span(M_PHASE1_DURATION):
            for file_record in pending_files:
                filepath = file_record["filepath"]
                filename = file_record["filename"]
                self._emit(FileState.QUEUED, filepath, filename)
                if not self._claim_path(filepath):
                    logger.debug("Archivo ya en procesamiento: %s", filename)
                    result["skipped"] += 1
                    continue
                self._emit(FileState.PROCESSING, filepath, filename)
                try:
                    rule_result = self._process_with_rule(filepath, filename, file_record.get("extension"))
                    if rule_result:
                        result["processed"] += 1
                        metrics.inc(M_FILES_PROCESSED)
                        self._release_path(filepath)
                    else:
                        ambiguous.append(file_record)  # path sigue claimed hasta el lote
                except Exception as e:
                    logger.error("Error en regla para %s: %s", filename, e)
                    self.db.update_file_status(filepath, "error")
                    self._release_path(filepath)
                    result["errors"] += 1
                    metrics.inc(M_FILES_ERRORS)
                    self._emit(FileState.ERROR, filepath, filename, reason=str(e))

        self._update_tray_progress(
            tray,
            f"Reglas: {result['processed']} clasificados; {len(ambiguous)} ambiguos",
            result,
            base_processed_total,
            base_errors_total,
            pending=len(ambiguous),
        )

        if not ambiguous:
            return result

        logger.info(
            "%d archivo(s) ambiguo(s) → clasificacion por lote (chunks de %d).",
            len(ambiguous),
            self.llm_batch_size,
        )

        # Fases 2+3: lote LLM con fallback ReAct
        _phase23_start = __import__("time").perf_counter()
        _time = __import__("time")
        for i in range(0, len(ambiguous), self.llm_batch_size):
            chunk = ambiguous[i : i + self.llm_batch_size]
            _chunk_processed_before = result["processed"]
            _chunk_errors_before = result["errors"]
            self._process_ambiguous_batch(
                chunk,
                result,
                tray=tray,
                base_processed_total=base_processed_total,
                base_errors_total=base_errors_total,
            )
            metrics.inc(M_FILES_PROCESSED, result["processed"] - _chunk_processed_before)
            metrics.inc(M_FILES_ERRORS, result["errors"] - _chunk_errors_before)
            # Pace API calls to stay within Gemini free-tier rate limits (15 req/min)
            if i + self.llm_batch_size < len(ambiguous):
                _time.sleep(2)
        metrics.record(M_PHASE2_DURATION, __import__("time").perf_counter() - _phase23_start)

        return result
