from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from rag_shared.models import TextBlock


def parse(path: Path) -> Iterator[TextBlock]:
    with Image.open(path) as image:
        # Preprocesado simple (plan.md, sección 8: mitigación para imágenes
        # borrosas) — escala de grises + autocontraste, antes del OCR.
        processed = ImageOps.autocontrast(image.convert("L"))
        text = pytesseract.image_to_string(processed, lang="spa+eng").strip()
    if text:
        yield TextBlock(text=text)
