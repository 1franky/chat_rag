"""Servidor MCP del RAG (FastMCP), ver plan.md sección 2.4.

Fase 3: las tres tools ya no son stubs — usan rag_shared.vector_store
(Qdrant), rag_shared.embeddings (el mismo modelo que usa la ingesta) y
rag_shared.documents_db (lectura de la tabla Document de Django).
"""

from __future__ import annotations

import asyncio
import os

import structlog
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from rag_shared import documents_db, vector_store
from rag_shared.embeddings import embed_query
from rag_shared.logging import configure_logging
from rag_shared.models import Chunk, DocumentMeta

configure_logging(service="chat-rag-mcp")
logger = structlog.get_logger()

mcp = FastMCP("chat-rag")


@mcp.tool
async def rag_search(query: str, top_k: int = 5) -> list[Chunk]:
    """Busca los fragmentos más relevantes para `query` entre los documentos indexados."""
    # embed_query es CPU-bound (sentence-transformers) y bloqueante: se
    # corre en un thread aparte para no trabar el event loop del server.
    vector = await asyncio.to_thread(embed_query, query)
    results = await vector_store.search(vector, top_k=top_k)
    logger.info("rag_search", query=query, top_k=top_k, results=len(results))
    return results


@mcp.tool
async def rag_list_documents() -> list[DocumentMeta]:
    """Lista los documentos indexados (o en proceso) y su estado."""
    return await asyncio.to_thread(documents_db.list_documents)


@mcp.tool
async def rag_get_document_chunks(document_id: str) -> list[Chunk]:
    """Devuelve todos los chunks de un documento indexado, en orden."""
    return await vector_store.get_document_chunks(document_id)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    qdrant_ok = await vector_store.ping()
    status = 200 if qdrant_ok else 503
    if not qdrant_ok:
        logger.warning("health_check_degraded", qdrant=qdrant_ok)
    return JSONResponse({"status": "ok" if qdrant_ok else "degraded", "qdrant": qdrant_ok}, status_code=status)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8100"))
    logger.info("startup", port=port)
    mcp.run(transport="http", host="0.0.0.0", port=port)
