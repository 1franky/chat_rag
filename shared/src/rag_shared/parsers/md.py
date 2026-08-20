from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from rag_shared.models import TextBlock


def parse(path: Path) -> Iterator[TextBlock]:
    """MD/TXT: lectura directa (plan.md, sección 2.3). Se indexa el
    markdown crudo (con `#`, listas, etc.) — igual de legible para el
    modelo de embeddings y evita depender de un parser de markdown."""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if text:
        yield TextBlock(text=text)
