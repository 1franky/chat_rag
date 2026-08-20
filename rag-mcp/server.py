"""Servidor MCP del RAG (FastMCP), ver plan.md sección 2.4.

Fase 2: las tres tools son stubs que devuelven listas vacías — solo dejan
registrada la interfaz que va a consumir el Agent SDK desde chat-web. La
implementación real (Qdrant + embeddings) llega en la Fase 3.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP
from rag_shared.models import Chunk, DocumentMeta
from starlette.requests import Request
from starlette.responses import JSONResponse

import vector_store

mcp = FastMCP("chat-rag")


@mcp.tool
def rag_search(query: str, top_k: int = 5) -> list[Chunk]:
    """Busca los fragmentos más relevantes para `query` entre los documentos indexados.

    Stub en la Fase 2: siempre devuelve una lista vacía.
    """
    return []


@mcp.tool
def rag_list_documents() -> list[DocumentMeta]:
    """Lista los documentos indexados y su estado.

    Stub en la Fase 2: siempre devuelve una lista vacía.
    """
    return []


@mcp.tool
def rag_get_document_chunks(document_id: str) -> list[Chunk]:
    """Devuelve todos los chunks de un documento indexado, en orden.

    Stub en la Fase 2: siempre devuelve una lista vacía.
    """
    return []


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    qdrant_ok = await vector_store.ping()
    status = 200 if qdrant_ok else 503
    return JSONResponse({"status": "ok" if qdrant_ok else "degraded", "qdrant": qdrant_ok}, status_code=status)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8100"))
    mcp.run(transport="http", host="0.0.0.0", port=port)
