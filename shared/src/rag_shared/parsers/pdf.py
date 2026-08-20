"""Parser de PDF: pypdf primero (rápido); si no extrae texto de ninguna
página, cae a pdfplumber (mejor con tablas); si una página sigue sin texto
(PDF escaneado), esa página se pasa por OCR (plan.md, sección 8: riesgo
"PDF con solo imágenes se salta pypdf").
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pypdf

from rag_shared.models import TextBlock


def parse(path: Path) -> Iterator[TextBlock]:
    reader = pypdf.PdfReader(str(path))
    blocks = []
    any_text = False
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            any_text = True
        blocks.append(TextBlock(text=text, page=page_number))

    if any_text:
        yield from (block for block in blocks if block.text)
        return

    yield from _parse_with_pdfplumber(path)


def _parse_with_pdfplumber(path: Path) -> Iterator[TextBlock]:
    import pdfplumber
    import pytesseract

    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                # Sin texto embebido: probablemente escaneada. OCR sobre el
                # render de la página (pdfplumber ya trae pypdfium2, no hace
                # falta poppler del sistema).
                image = page.to_image(resolution=200).original
                text = pytesseract.image_to_string(image, lang="spa+eng").strip()
            if text:
                yield TextBlock(text=text, page=page_number)
