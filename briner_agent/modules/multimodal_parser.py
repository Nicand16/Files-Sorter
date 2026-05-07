import logging
from pathlib import Path
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def analyze_document_content(file_path: str) -> str:
    """
    Lee y resume el contenido preliminar de un documento de texto o datos (soporta .txt, .csv, .md, .json).
    Útil para saber exactamente de qué trata el archivo antes de tomar la decisión de dónde categorizarlo o moverlo.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return "Error: Archivo no encontrado en disco."
            
        # Extracción simple y segura (primeros 1000 caracteres)
        if path.suffix.lower() in ['.txt', '.csv', '.md', '.json', '.log']:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1500)
            logger.info(f"Acción (analyze_document_content): Contenido extraído de {path.name}")
            return f"El contenido inicial del documento es:\n\n{content}\n[...]"
        else:
            return f"Aviso: El archivo {path.name} es un binario o su formato no es legible como texto plano. Analiza basándote exclusivamente en su nombre y extensión."
            
    except Exception as e:
        logger.error(f"Error analizando documento: {e}")
        return f"Error técnico al leer documento: {str(e)}"

def get_parser_tools():
    """Retorna la lista de herramientas de análisis multimodal para LangChain."""
    return [analyze_document_content]
