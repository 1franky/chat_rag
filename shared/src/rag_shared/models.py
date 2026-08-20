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


class SearchResult(BaseModel):
    """Resultado de `rag_search`: los chunks más relevantes para una query."""

    query: str
    chunks: list[Chunk] = Field(default_factory=list)
