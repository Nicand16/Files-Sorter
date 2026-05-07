import importlib.util
import logging
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 3000
TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".json", ".log", ".yaml", ".yml", ".xml"}


def _trim(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + " [...]"


def _read_text(path: Path, max_chars: int) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as file:
        return file.read(max_chars)


def _read_pdf(path: Path, max_chars: int) -> str:
    if not importlib.util.find_spec("pypdf"):
        return "Aviso: PDF detectado, pero pypdf no esta instalado. Clasifica por nombre, extension y metadatos disponibles."

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages[:5]:
        parts.append(page.extract_text() or "")
        if sum(len(part) for part in parts) >= max_chars:
            break
    return _trim(" ".join(parts), max_chars)


def _xml_text_from_zip(path: Path, members: list[str], max_chars: int) -> str:
    parts = []
    with zipfile.ZipFile(path) as archive:
        for member in members:
            if member not in archive.namelist():
                continue
            data = archive.read(member)
            root = ElementTree.fromstring(data)
            parts.extend(text for text in root.itertext() if text.strip())
            if sum(len(part) for part in parts) >= max_chars:
                break
    return _trim(" ".join(parts), max_chars)


def _read_docx(path: Path, max_chars: int) -> str:
    if importlib.util.find_spec("docx"):
        from docx import Document

        document = Document(str(path))
        text = " ".join(paragraph.text for paragraph in document.paragraphs)
        return _trim(text, max_chars)

    return _xml_text_from_zip(path, ["word/document.xml"], max_chars)


def _read_xlsx(path: Path, max_chars: int) -> str:
    members = ["xl/sharedStrings.xml"]
    with zipfile.ZipFile(path) as archive:
        members.extend(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
    return _xml_text_from_zip(path, members, max_chars)


def _read_pptx(path: Path, max_chars: int) -> str:
    with zipfile.ZipFile(path) as archive:
        members = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
    return _xml_text_from_zip(path, members, max_chars)


def extract_document_content(file_path: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    path = Path(file_path)
    if not path.exists():
        return "Error: Archivo no encontrado en disco."
    if not path.is_file():
        return "Error: La ruta no corresponde a un archivo."

    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_EXTENSIONS:
            content = _read_text(path, max_chars)
        elif suffix == ".pdf":
            content = _read_pdf(path, max_chars)
        elif suffix == ".docx":
            content = _read_docx(path, max_chars)
        elif suffix == ".xlsx":
            content = _read_xlsx(path, max_chars)
        elif suffix == ".pptx":
            content = _read_pptx(path, max_chars)
        else:
            return (
                f"Aviso: El archivo {path.name} tiene formato {suffix or 'sin extension'} "
                "y no es legible por el parser actual. Clasifica por nombre y extension."
            )

        if not content:
            return f"Aviso: No se pudo extraer texto util de {path.name}. Clasifica por nombre y extension."

        logger.info("Accion (analyze_document_content): contenido extraido de %s", path.name)
        return f"El contenido inicial del documento es:\n\n{_trim(content, max_chars)}"
    except Exception as e:
        logger.error("Error analizando documento %s: %s", path, e)
        return f"Error tecnico al leer documento: {str(e)}"


@tool
def analyze_document_content(file_path: str) -> str:
    """
    Extrae texto preliminar de txt/csv/md/json/log/yaml/xml, PDF si pypdf esta instalado,
    y documentos Office modernos (.docx/.xlsx/.pptx) con extraccion parcial segura.
    """
    return extract_document_content(file_path, DEFAULT_MAX_CHARS)


def get_parser_tools():
    """Retorna la lista de herramientas de analisis multimodal para LangChain."""
    return [analyze_document_content]
