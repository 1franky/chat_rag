"""Modelos pydantic compartidos entre chat-web (ingesta) y chat-rag-mcp
(búsqueda). Ver plan.md, sección 2.4, para las firmas de las tools MCP que
los usan.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class TextBlock(BaseModel):
    """Bloque de texto tal como lo extrae un parser, antes de chunkear.

    Es más grueso que un Chunk final (un parser puede devolver, por
    ejemplo, una página entera): `chunker.chunk_blocks` los recorta al
    tamaño de chunk configurado, propagando `page`/`section`.
    """

    text: str
    page: int | None = None
    section: str | None = None


class Chunk(BaseModel):
    """Un fragmento de texto indexado en Qdrant, con su metadata de origen.

    `score` solo se completa cuando el Chunk viene de un resultado de
    búsqueda (`rag_search`); en `rag_get_document_chunks` queda en None.
    """

    document_id: str
    chunk_index: int
    text: str
    page: int | None = None
    section: str | None = None
    score: float | None = None


class DocumentMeta(BaseModel):
    """Metadata de un documento indexado, para `rag_list_documents`."""

    document_id: str
    filename: str
    mime_type: str
    status: DocumentStatus
    chunk_count: int = 0
    uploaded_at: datetime
    error_message: str | None = None
    collection: str | None = None


class CollectionMeta(BaseModel):
    """Una colección de documentos, para `rag_list_collections` (plan-v2.md,
    Fase 10) — así Claude sabe qué colecciones existen antes de decidir si
    acotar `rag_search` a una."""

    name: str
    document_count: int = 0


class SearchResult(BaseModel):
    """Resultado de `rag_search`: los chunks más relevantes para una query."""

    query: str
    chunks: list[Chunk] = Field(default_factory=list)
