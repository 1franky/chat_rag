"""Detección de mime type "real" (mira los bytes del archivo, no la
extensión) — plan.md, Fase 3: "Detectar mime type real (no confiar en la
extensión)".

Dos casos especiales, porque libmagic por sí solo no alcanza:

- DOCX/PPTX/XLSX son archivos ZIP; la calidad de la detección específica
  ("es un .docx", no solo "es un zip") depende de qué tan actualizada esté
  la base de firmas de la libmagic instalada — se probó en este mismo
  entorno y devuelve `application/octet-stream` a secas. Se resuelve
  mirando adentro del zip (mismo truco que usa libmagic internamente,
  pero sin depender de su versión).
- CSV/Markdown/texto plano son indistinguibles a nivel de bytes (no hay
  magic number posible) — ahí sí se cae a la extensión como desempate.

El import de `magic` es perezoso a propósito: la lib de sistema libmagic1
solo está instalada en chat-worker (que es quien de verdad detecta mime
types, al procesar la ingesta) y no en chat-web — si `import magic` fuera
top-level, chat-web reventaría al arrancar con ImportError, solo porque
apps.ingesta.views importa apps.ingesta.tasks transitivamente.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

_EXTENSION_FALLBACK = {
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}

# Mime types que libmagic devuelve para cualquier archivo de puro texto,
# sin poder distinguir csv/md/txt entre sí.
_AMBIGUOUS_TEXT_TYPES = {"text/plain", "application/csv", "text/csv"}

# libmagic puede devolver cualquiera de estos para un OOXML según qué tan
# actualizada esté su base de firmas — de "genérico" a "ni siquiera lo
# reconoce como zip".
_ZIP_LIKE_TYPES = {"application/zip", "application/octet-stream", "application/x-zip-compressed"}

# Un archivo específico de cada formato que solo existe en ese formato
# (mismo criterio que usa libmagic internamente para distinguir OOXML).
_OOXML_MARKERS = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt/presentation.xml": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def detect_mime_type(path: Path) -> str:
    import magic

    detected = magic.from_file(str(path), mime=True)

    if detected in _ZIP_LIKE_TYPES:
        ooxml_type = _detect_ooxml(path)
        if ooxml_type:
            return ooxml_type

    if detected in _AMBIGUOUS_TEXT_TYPES:
        return _EXTENSION_FALLBACK.get(path.suffix.lower(), detected)

    return detected


def _detect_ooxml(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return None

    for marker, mime_type in _OOXML_MARKERS.items():
        if marker in names:
            return mime_type
    return None
