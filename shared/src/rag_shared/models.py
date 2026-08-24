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


class ReportSection(BaseModel):
    """Una sección de un documento de reportería (plan-v3.md, Fase 21) —
    título + cuerpo ya redactado por Claude. `report_generate_document`
    (rag-mcp/server.py) solo maqueta y exporta esto a docx/pptx/pdf, no
    redacta contenido — Claude tuvo que leer el documento fuente (vía
    rag_search/rag_get_document_chunks) y armar el resumen él mismo antes.

    `body` admite líneas sueltas como párrafos normales, y líneas que
    empiezan con "- " o "* " se renderizan como bullets (docx/pptx) —
    mismo criterio simple en los tres formatos, sin pedirle a Claude una
    estructura más rica en el input.
    """

    heading: str
    body: str


class DiagramNode(BaseModel):
    """Un nodo de un diagrama (plan-v3.md, Fase 22) — `id` es la referencia
    que usan los `DiagramEdge` para conectar nodos entre sí, `label` es el
    texto visible."""

    id: str
    label: str


class DiagramEdge(BaseModel):
    """Una arista de un diagrama, entre dos `DiagramNode.id` — `label`
    opcional (ej. el texto sobre la flecha en un diagrama de flujo).

    `source`/`target`, no `from`/`to` como los nombraba el plan original:
    `from` es palabra reservada de Python, no se puede usar como nombre de
    campo de un modelo sin lidiar con un alias — más simple nombrarlos
    distinto de entrada."""

    source: str
    target: str
    label: str = ""


class SearchResult(BaseModel):
    """Resultado de `rag_search`: los chunks más relevantes para una query."""

    query: str
    chunks: list[Chunk] = Field(default_factory=list)
