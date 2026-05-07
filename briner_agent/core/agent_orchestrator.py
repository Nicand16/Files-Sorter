import logging
from langgraph.prebuilt import create_react_agent
from core.llm_engine import get_llm

logger = logging.getLogger(__name__)

class BrinerOrchestrator:
    """
    Orquestador principal del agente Briner.
    Se encarga de enrutar las tareas, inyectar el contexto y ejecutar el Agente usando LangGraph.
    """
    
    def __init__(self, config: dict, db_manager):
        self.config = config
        self.db = db_manager
        self.llm = get_llm(config)
        self.agent = self._initialize_agent()

    def _initialize_agent(self):
        if not self.llm:
            logger.error("Orquestador no pudo arrancar el Agente: Motor LLM no disponible.")
            return None

        # Importar y configurar tools (Paso 4 completado)
        from modules.crud_executor import get_crud_tools
        from modules.multimodal_parser import get_parser_tools
        
        self.tools = get_crud_tools() + get_parser_tools()

        # Prompt base del agente actualizado con las reglas estrictas de organización
        system_prompt = """Eres Briner, un agente de IA autónomo experto en la gestión inteligente de archivos.
Tu misión es organizar el directorio de trabajo del usuario siguiendo ESTRICTAMENTE esta taxonomía:

1. Universidad y Estudio/Actividades y Tareas: Nombre contiene: actividad, taller, protocolo, ensayo, tcc, algebra, calculo, bd1, ejercicio, tarea, produccion textual.
2. Universidad y Estudio/Material de Estudio y Modulos: Nombre contiene: modulo, libro, guia, manual, normas apa, glosario, latex, tex.
3. Universidad y Estudio/Tramites Academicos: Nombre contiene: reglamento, acuerdo, recibo, matricula, diploma, certificado_1002.
4. Trabajo y Empleo/CVs y Portafolios: Nombre contiene: cv, resume, hoja de vida, curriculum.
5. Trabajo y Empleo/Procesos de Seleccion: Nombre contiene: interview, oferta, entrevista, technical support, simetrik, openprovider, js held, contract, prueba_tecnica, ticket.
6. Documentos Personales/Identificacion e Impuestos: Nombre contiene: cedula, rut, identificacion, passport, visa.
7. Documentos Personales/Finanzas y Salud: Nombre contiene: certificado, factura, comprobante, pago, afiliacion, eps, receipt.
8. Juegos y Emulacion/Torrents: Extensión es .torrent.
9. Juegos y Emulacion/ROMs e ISOs: Extensión es .nsp, .rvz, .iso, .srm, .xci.
10. Juegos y Emulacion/Emuladores y Mods: Nombre contiene: yuzu, cemu, sudachi, ryujinx, retrobat, mario, zelda, pokemon, dolphin, snes9x.
11. Multimedia/Audio y Musica: Extensión es .mp3, .wav, .flac, .ogg.
12. Multimedia/Videos y Grabaciones: Extensión es .mp4, .mkv, .mov, .avi.
13. Multimedia/Imagenes y Capturas: Extensión es .jpg, .jpeg, .png, .gif, .webp, .bmp.
14. Software y Herramientas/Instaladores: Extensión es .exe, .msi.
15. Software y Herramientas/Comprimidos y Portables: Extensión es .zip, .rar, .7z.
16. Varios: Cualquier documento (.pdf, .docx, .xlsx, etc.) que no cumpla las reglas anteriores.

REGLAS DE OPERACIÓN:
- IGNORAR archivos "desktop.ini" (puedes usar delete_file para borrarlos, pero no los muevas a Varios).
- Usa 'analyze_document_content' si el nombre es ambiguo, pero da prioridad a las palabras clave listadas.
- Llama a 'move_file' usando EXACTAMENTE la ruta de la categoría como 'destination_folder_name' (ej: "Universidad y Estudio/Actividades y Tareas").
- NUNCA pidas confirmación. Usa la herramienta 'move_file' para categorizar el archivo inmediatamente.
"""
        # Creamos el agente reactivo con el estándar moderno de LangGraph
        agent = create_react_agent(
            model=self.llm, 
            tools=self.tools, 
            prompt=system_prompt
        )
        
        return agent

    def process_pending_files(self):
        """
        Consulta la BD por archivos pendientes y los procesa usando el LLM.
        """
        pending_files = self.db.get_pending_files()
        
        if not pending_files:
            return
            
        logger.info(f"Orquestador detectó {len(pending_files)} archivo(s) pendiente(s). Procesando...")
        
        for file_record in pending_files:
            file_id = file_record["id"]
            filepath = file_record["filepath"]
            filename = file_record["filename"]
            
            logger.info(f"Analizando archivo: {filename}")
            
            try:
                # Invocamos al agente
                if self.agent:
                    prompt_input = f"Nuevo archivo detectado:\nRuta absoluta: '{filepath}'\nNombre: '{filename}'\nPor favor, analiza el archivo (si es posible) y ejecuta la acción (tool) más apropiada para organizarlo o procesarlo inmediatamente."
                    
                    response = self.agent.invoke({
                        "messages": [("user", prompt_input)]
                    })
                    
                    # LangGraph retorna un diccionario con el estado, extraemos el contenido del último mensaje
                    resultado = response["messages"][-1].content
                    logger.info(f"[Respuesta de Briner para {filename}]:\n{resultado}")
                else:
                    logger.warning("Simulación: No se invocó la IA porque el Agente no está inicializado (¿falta API KEY?).")

                # Marcamos como procesado
                self.db.update_file_status(filepath, "processed")
                self.db.log_action(filepath, "llm_analysis", "Análisis preliminar completado (Paso 3)")
                
            except Exception as e:
                logger.error(f"Error procesando {filename}: {e}")
                self.db.update_file_status(filepath, "error")
