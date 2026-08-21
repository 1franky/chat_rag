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
from rag_shared.embeddings import embed_query, embed_query_sparse
from rag_shared.logging import configure_logging
from rag_shared.models import Chunk, CollectionMeta, DocumentMeta

configure_logging(service="chat-rag-mcp")
logger = structlog.get_logger()

mcp = FastMCP("chat-rag")


@mcp.tool
async def rag_search(query: str, top_k: int = 5, collection: str | None = None) -> list[Chunk]:
    """Busca los fragmentos más relevantes para `query` entre los documentos indexados.

    `collection` (opcional, plan-v2.md Fase 10) acota la búsqueda a una sola
    colección — usar el nombre exacto que devuelve `rag_list_collections`.
    Sin especificarlo, busca en todos los documentos indexados.

    Búsqueda híbrida (plan-v2.md, Fase 12): combina similitud vectorial con
    BM25 léxico, mejor para términos exactos (nombres propios, códigos).
    """
    # embed_query/embed_query_sparse son CPU-bound (sentence-transformers /
    # fastembed) y bloqueantes: se corren en threads aparte para no trabar
    # el event loop del server. No dependen entre sí, van en paralelo.
    vector, sparse_vector = await asyncio.gather(
        asyncio.to_thread(embed_query, query),
        asyncio.to_thread(embed_query_sparse, query),
    )

    collection_id = None
    if collection is not None:
        collection_id = await asyncio.to_thread(documents_db.resolve_collection_id, collection)
        if collection_id is None:
            logger.warning("rag_search_unknown_collection", collection=collection)
            return []

    results = await vector_store.search(vector, sparse_vector, top_k=top_k, collection_id=collection_id)
    logger.info("rag_search", query=query, top_k=top_k, collection=collection, results=len(results))
    return results


@mcp.tool
async def rag_list_documents() -> list[DocumentMeta]:
    """Lista los documentos indexados (o en proceso) y su estado."""
    return await asyncio.to_thread(documents_db.list_documents)


@mcp.tool
async def rag_list_collections() -> list[CollectionMeta]:
    """Lista las colecciones (carpetas de documentos) que existen, con
    cuántos documentos tiene cada una — para decidir si conviene acotar
    `rag_search` a alguna en vez de buscar en todo lo indexado."""
    return await asyncio.to_thread(documents_db.list_collections)


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
