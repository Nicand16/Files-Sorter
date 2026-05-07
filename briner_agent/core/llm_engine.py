<<<<<<< HEAD
import logging
import os

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

logger = logging.getLogger(__name__)


def get_llm(config: dict):
    """Inicializa y retorna el modelo LLM si sus dependencias y credenciales existen."""
    llm_config = config.get("llm", {})
    model_name = llm_config.get("model", "gemini-1.5-pro")
    temperature = llm_config.get("temperature", 0.2)

    if not ChatGoogleGenerativeAI:
        logger.warning("langchain_google_genai no esta instalado. Motor LLM deshabilitado.")
        return None

    if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        logger.warning("Falta GOOGLE_API_KEY/GEMINI_API_KEY. Motor LLM deshabilitado.")
        return None
=======
import os
import logging
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

def get_llm(config: dict):
    """
    Inicializa y retorna la instancia del modelo de lenguaje.
    Utiliza LangChain para abstraer la conexión con el motor IA.
    """
    llm_config = config.get("llm", {})
    model_name = llm_config.get("model", "gemini-1.5-pro")
    temperature = llm_config.get("temperature", 0.2)
    
    if not os.environ.get("GOOGLE_API_KEY"):
        logger.warning("Falta GOOGLE_API_KEY en variables de entorno. Las llamadas a la IA podrían fallar.")
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43

    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
<<<<<<< HEAD
            max_output_tokens=8192,
        )
        logger.info("Motor LLM inicializado exitosamente (Modelo: %s)", model_name)
        return llm
    except Exception as e:
        logger.error("Error al inicializar el motor LLM: %s", e)
=======
            max_output_tokens=8192
        )
        logger.info(f"Motor LLM inicializado exitosamente (Modelo: {model_name})")
        return llm
    except Exception as e:
        logger.error(f"Error al inicializar el motor LLM: {e}")
>>>>>>> c99e90658353d10d9e83ae9765273f8409660b43
        return None
