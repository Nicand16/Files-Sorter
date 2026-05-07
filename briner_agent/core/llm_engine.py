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

    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=8192,
        )
        logger.info("Motor LLM inicializado exitosamente (Modelo: %s)", model_name)
        return llm
    except Exception as e:
        logger.error("Error al inicializar el motor LLM: %s", e)
        return None
