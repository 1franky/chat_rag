"""Chunking: `RecursiveCharacterTextSplitter` (800/120), respeta párrafos
(plan.md, sección 2.3).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_shared.models import TextBlock

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


def _get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_blocks(blocks: Iterable[TextBlock]) -> Iterator[TextBlock]:
    """Recorta cada TextBlock (por ejemplo, una página entera) en chunks del
    tamaño configurado, propagando `page`/`section` del bloque de origen.
    """
    splitter = _get_splitter()
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if piece:
                yield TextBlock(text=piece, page=block.page, section=block.section)
