from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata


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
            "parcial",
            "quiz",
            "evaluacion",
            "laboratorio",
            "entrega",
            "rubrica",
        ],
    },
    {
        "category": "Universidad y Estudio/Material de Estudio y Modulos",
        "keywords": [
            "modulo",
            "libro",
            "guia",
            "manual",
            "normas apa",
            "glosario",
            "latex",
            "tex",
            "syllabus",
            "clase",
            "lectura",
            "diapositivas",
        ],
    },
    {
        "category": "Universidad y Estudio/Tramites Academicos",
        "keywords": [
            "reglamento",
            "acuerdo",
            "recibo",
            "matricula",
            "diploma",
            "certificado_1002",
            "certificado academico",
            "constancia de estudio",
            "notas",
            "calificaciones",
            "homologacion",
            "inscripcion",
        ],
    },
    {
        "category": "Trabajo y Empleo/CVs y Portafolios",
        "keywords": ["cv", "resume", "hoja de vida", "curriculum", "portfolio", "portafolio"],
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
            "prueba tecnica",
            "ticket",
            "recruiter",
            "reclutador",
            "job offer",
            "contrato laboral",
        ],
    },
    {
        "category": "Documentos Personales/Identificacion e Impuestos",
        "keywords": [
            "cedula",
            "rut",
            "identificacion",
            "passport",
            "pasaporte",
            "visa",
            "dni",
            "tax",
            "impuesto",
            "declaracion de renta",
        ],
    },
    {
        "category": "Documentos Personales/Finanzas y Salud",
        "keywords": [
            "certificado",
            "factura",
            "comprobante",
            "pago",
            "afiliacion",
            "eps",
            "receipt",
            "recibo de pago",
            "banco",
            "extracto",
            "cuenta",
            "medico",
            "salud",
            "historia clinica",
            "laboratorio clinico",
        ],
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
_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[_\-.]+", " ", text.casefold())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text))


def is_document_extension(extension: str | None) -> bool:
    return (extension or "").casefold() in DOCUMENT_EXTENSIONS


def get_taxonomy(config: dict | None = None) -> list[dict]:
    return (config or {}).get("taxonomy", {}).get("categories") or DEFAULT_TAXONOMY


def taxonomy_categories(config: dict | None = None) -> list[str]:
    return [rule["category"] for rule in get_taxonomy(config) if rule.get("category")]


def build_taxonomy_prompt(config: dict | None = None) -> str:
    lines = []
    for index, rule in enumerate(get_taxonomy(config), start=1):
        details = []
        if rule.get("keywords"):
            details.append("Nombre/contenido contiene: " + ", ".join(rule["keywords"]))
        if rule.get("extensions"):
            details.append("Extension es: " + ", ".join(rule["extensions"]))
        lines.append(f"{index}. {rule['category']}: {'; '.join(details)}.")
    lines.append(f"{len(lines) + 1}. Varios: Solo para archivos sin evidencia razonable en nombre, tipo, metadatos ni contenido.")
    return "\n".join(lines)


def _flatten_context(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        parts = []
        for item in value.values():
            parts.extend(_flatten_context(item))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            parts.extend(_flatten_context(item))
        return parts
    return [str(value)]


def metadata_to_search_text(metadata: dict | None) -> str:
    return " ".join(_flatten_context(metadata or {}))


def _keyword_score(keyword: str, normalized_text: str, token_set: set[str]) -> int:
    normalized_keyword = normalize_text(keyword)
    if not normalized_keyword:
        return 0
    keyword_tokens = _tokens(normalized_keyword)
    if not keyword_tokens:
        return 0

    padded_text = f" {normalized_text} "
    if len(keyword_tokens) > 1:
        if f" {normalized_keyword} " in padded_text:
            return 10 + (2 * len(keyword_tokens))
        return 0

    token = next(iter(keyword_tokens))
    if token in token_set:
        return 8 if len(token) > 3 else 6
    return 0


def _confidence_from_score(score: int, extension_match: bool = False) -> float:
    if extension_match:
        return 0.99
    if score >= 20:
        return 0.97
    if score >= 14:
        return 0.93
    if score >= 10:
        return 0.89
    if score >= 8:
        return 0.84
    if score >= 6:
        return 0.78
    return 0.0


def rank_file_categories(
    filename: str,
    extension: str | None = None,
    metadata: dict | None = None,
    config: dict | None = None,
    limit: int | None = None,
) -> list[dict]:
    suffix = (extension or Path(filename).suffix).casefold()
    search_text = " ".join([filename, metadata_to_search_text(metadata)])
    normalized = normalize_text(search_text)
    token_set = _tokens(normalized)
    ranked = []

    for order, rule in enumerate(get_taxonomy(config)):
        category = rule["category"]
        extensions = {item.casefold() for item in rule.get("extensions", [])}
        extension_match = bool(suffix and suffix in extensions)
        score = 100 if extension_match else 0
        matches = []

        for keyword in rule.get("keywords", []):
            keyword_points = _keyword_score(keyword, normalized, token_set)
            if keyword_points:
                score += keyword_points
                matches.append(keyword)

        if score <= 0:
            continue

        reason_parts = []
        if extension_match:
            reason_parts.append(f"extension {suffix}")
        if matches:
            reason_parts.append("keywords: " + ", ".join(matches[:5]))

        ranked.append({
            "category": category,
            "score": score,
            "confidence": _confidence_from_score(score, extension_match),
            "reason": "; ".join(reason_parts),
            "order": order,
        })

    ranked.sort(key=lambda item: (item["score"], item["confidence"], -item["order"]), reverse=True)
    if limit is not None:
        return ranked[:limit]
    return ranked


def _decision_from_ranked(ranked: list[dict], min_confidence: float, context_label: str) -> ClassificationDecision | None:
    if not ranked:
        return None
    best = ranked[0]
    if best["confidence"] < min_confidence:
        return None
    return ClassificationDecision(
        action="move",
        category=best["category"],
        reason=f"{context_label}: {best['reason']}.",
        confidence=best["confidence"],
    )


def classify_file(
    filename: str,
    extension: str | None = None,
    config: dict | None = None,
) -> ClassificationDecision | None:
    suffix = (extension or Path(filename).suffix).casefold()

    if filename.casefold() in {"desktop.ini", ".keep"}:
        return ClassificationDecision(
            action="ignore",
            category=None,
            reason="Archivo de sistema o marcador ignorado.",
            confidence=1.0,
        )

    ranked = rank_file_categories(filename, suffix, None, config)
    decision = _decision_from_ranked(ranked, min_confidence=0.78, context_label="Regla por nombre/extension")
    if decision:
        return decision

    if suffix in DOCUMENT_EXTENSIONS and (config or {}).get("rules", {}).get("fallback_documents_to_varios", False):
        return ClassificationDecision(
            action="move",
            category="Varios",
            reason=f"Documento generico sin regla especifica ({suffix}).",
            confidence=0.7,
        )

    return None


def classify_file_context(
    filename: str,
    extension: str | None = None,
    metadata: dict | None = None,
    config: dict | None = None,
    min_confidence: float = 0.84,
) -> ClassificationDecision | None:
    ranked = rank_file_categories(filename, extension, metadata, config)
    return _decision_from_ranked(ranked, min_confidence=min_confidence, context_label="Regla por metadatos/contenido")
