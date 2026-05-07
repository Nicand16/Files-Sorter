from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClassificationDecision:
    action: str
    category: str | None
    reason: str
    confidence: float


DEFAULT_TAXONOMY = [
    {
        "category": "Universidad y Estudio/Actividades y Tareas",
        "keywords": [
            "actividad",
            "taller",
            "protocolo",
            "ensayo",
            "tcc",
            "algebra",
            "calculo",
            "bd1",
            "ejercicio",
            "tarea",
            "produccion textual",
        ],
    },
    {
        "category": "Universidad y Estudio/Material de Estudio y Modulos",
        "keywords": ["modulo", "libro", "guia", "manual", "normas apa", "glosario", "latex", "tex"],
    },
    {
        "category": "Universidad y Estudio/Tramites Academicos",
        "keywords": ["reglamento", "acuerdo", "recibo", "matricula", "diploma", "certificado_1002"],
    },
    {
        "category": "Trabajo y Empleo/CVs y Portafolios",
        "keywords": ["cv", "resume", "hoja de vida", "curriculum"],
    },
    {
        "category": "Trabajo y Empleo/Procesos de Seleccion",
        "keywords": [
            "interview",
            "oferta",
            "entrevista",
            "technical support",
            "simetrik",
            "openprovider",
            "js held",
            "contract",
            "prueba_tecnica",
            "ticket",
        ],
    },
    {
        "category": "Documentos Personales/Identificacion e Impuestos",
        "keywords": ["cedula", "rut", "identificacion", "passport", "visa"],
    },
    {
        "category": "Documentos Personales/Finanzas y Salud",
        "keywords": ["certificado", "factura", "comprobante", "pago", "afiliacion", "eps", "receipt"],
    },
    {
        "category": "Juegos y Emulacion/Torrents",
        "extensions": [".torrent"],
    },
    {
        "category": "Juegos y Emulacion/ROMs e ISOs",
        "extensions": [".nsp", ".rvz", ".iso", ".srm", ".xci"],
    },
    {
        "category": "Juegos y Emulacion/Emuladores y Mods",
        "keywords": ["yuzu", "cemu", "sudachi", "ryujinx", "retrobat", "mario", "zelda", "pokemon", "dolphin", "snes9x"],
    },
    {
        "category": "Multimedia/Audio y Musica",
        "extensions": [".mp3", ".wav", ".flac", ".ogg"],
    },
    {
        "category": "Multimedia/Videos y Grabaciones",
        "extensions": [".mp4", ".mkv", ".mov", ".avi"],
    },
    {
        "category": "Multimedia/Imagenes y Capturas",
        "extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
    },
    {
        "category": "Software y Herramientas/Instaladores",
        "extensions": [".exe", ".msi"],
    },
    {
        "category": "Software y Herramientas/Comprimidos y Portables",
        "extensions": [".zip", ".rar", ".7z"],
    },
]

DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods"}


def get_taxonomy(config: dict | None = None) -> list[dict]:
    return (config or {}).get("taxonomy", {}).get("categories") or DEFAULT_TAXONOMY


def build_taxonomy_prompt(config: dict | None = None) -> str:
    lines = []
    for index, rule in enumerate(get_taxonomy(config), start=1):
        details = []
        if rule.get("keywords"):
            details.append("Nombre contiene: " + ", ".join(rule["keywords"]))
        if rule.get("extensions"):
            details.append("Extension es: " + ", ".join(rule["extensions"]))
        lines.append(f"{index}. {rule['category']}: {'; '.join(details)}.")
    lines.append(f"{len(lines) + 1}. Varios: Documentos ambiguos no cubiertos por reglas anteriores.")
    return "\n".join(lines)


def classify_file(
    filename: str,
    extension: str | None = None,
    config: dict | None = None,
) -> ClassificationDecision | None:
    normalized_name = filename.casefold()
    suffix = (extension or Path(filename).suffix).casefold()

    if filename.casefold() in {"desktop.ini", ".keep"}:
        return ClassificationDecision(
            action="ignore",
            category=None,
            reason="Archivo de sistema o marcador ignorado.",
            confidence=1.0,
        )

    for rule in get_taxonomy(config):
        category = rule["category"]
        extensions = {item.casefold() for item in rule.get("extensions", [])}
        if suffix and suffix in extensions:
            return ClassificationDecision(
                action="move",
                category=category,
                reason=f"Extension deterministica {suffix}.",
                confidence=0.99,
            )

        for keyword in rule.get("keywords", []):
            if keyword.casefold() in normalized_name:
                return ClassificationDecision(
                    action="move",
                    category=category,
                    reason=f"Palabra clave deterministica '{keyword}' en el nombre.",
                    confidence=0.95,
                )

    if suffix in DOCUMENT_EXTENSIONS and (config or {}).get("rules", {}).get("fallback_documents_to_varios", False):
        return ClassificationDecision(
            action="move",
            category="Varios",
            reason=f"Documento generico sin regla especifica ({suffix}).",
            confidence=0.7,
        )

    return None
