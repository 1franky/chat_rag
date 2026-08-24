"""Servidor MCP del RAG (FastMCP), ver plan.md sección 2.4.

Fase 3: las tres tools ya no son stubs — usan rag_shared.vector_store
(Qdrant), rag_shared.embeddings (el mismo modelo que usa la ingesta) y
rag_shared.documents_db (lectura de la tabla Document de Django).
"""

from __future__ import annotations

import asyncio
import os
from typing import Literal

import structlog
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from rag_shared import documents_db, reports, vector_store
from rag_shared.embeddings import embed_query, embed_query_sparse, rerank
from rag_shared.logging import configure_logging
from rag_shared.models import Chunk, CollectionMeta, DocumentMeta

configure_logging(service="chat-rag-mcp")
logger = structlog.get_logger()

mcp = FastMCP("chat-rag")

# Base pública para armar el link de descarga de un reporte (plan-v3.md,
# Fase 20) — mismo patrón que PUBLIC_BASE_URL en chat-web
# (config/settings.py), pero acá no hay Django/request de donde caer a
# request.build_absolute_uri() si falta: sin setearla en .env, la URL
# devuelta queda relativa (sirve para debug local, no para un link
# clickeable real).
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
# Tiene que coincidir con el prefijo registrado en
# apps/core/urls.py::download_report (chat-web es quien sirve el archivo,
# no este servidor — ver la nota de REPORTS_DIR en rag_shared/reports.py).
REPORTS_URL_PATH = "/reportes"

# Cuántos candidatos de más pedirle a la fusión RRF antes de rerankear y
# cortar a `top_k` (plan-v3.md, Fase 17) — el cross-encoder puede promover
# un chunk que la fusión RRF dejó afuera del top_k original, así que hace
# falta margen. 2x, no el 4x de partida que sugería el plan: medido en este
# host (2 CPUs, ARM64, sin GPU) la latencia del reranker escala con la
# cantidad de candidatos — 4x (20 candidatos con top_k=5) tardaba ~19s,
# inviable para un chat interactivo; 2x (10 candidatos) baja a ~5-6s,
# aceptado como trade-off precisión/latencia. Ver el docstring de
# `rag_search` para el detalle completo de la decisión.
_RERANK_CANDIDATE_MULTIPLIER = 2


@mcp.tool
async def rag_search(query: str, top_k: int = 5, collection: str | None = None) -> list[Chunk]:
    """Busca los fragmentos más relevantes para `query` entre los documentos indexados.

    `collection` (opcional, plan-v2.md Fase 10) acota la búsqueda a una sola
    colección — usar el nombre exacto que devuelve `rag_list_collections`.
    Sin especificarlo, busca en todos los documentos indexados.

    Búsqueda híbrida (plan-v2.md, Fase 12): combina similitud vectorial con
    BM25 léxico, mejor para términos exactos (nombres propios, códigos).

    Reranking (plan-v3.md, Fase 17): la fusión RRF de arriba compara
    embeddings calculados por separado (query vs. chunk); un cross-encoder
    reordena después mirando query+chunk juntos, más preciso. Se le pide a
    `vector_store.search` `top_k * _RERANK_CANDIDATE_MULTIPLIER` candidatos
    (mismo prefetch+RRF de siempre, sin cambios en vector_store.py — subir
    el `top_k` que recibe ya alcanza), se rerankean acá (es esta capa la
    que tiene el texto de la query a mano) y se corta a `top_k` recién al
    final.

    Costo de latencia (decisión de arquitectura, confirmada con el usuario
    tras medir en este host — 2 CPUs físicas, ARM64, sin GPU): el modelo de
    reranking (`rag_shared.embeddings.RERANK_MODEL`,
    `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` por default) corre sobre
    CPU y su costo escala con la cantidad y longitud de los candidatos
    (chunks reales de hasta 800 caracteres, `CHUNK_SIZE` de
    `rag_shared/chunker.py`). Con top_k=5 (default) y
    `_RERANK_CANDIDATE_MULTIPLIER=2` → 10 candidatos: ~5-6s extra por
    búsqueda sobre el tiempo de fusión RRF solo (que es de milisegundos).
    Se evaluó primero el único modelo de reranking multilingüe que trae
    fastembed (`jinaai/jina-reranker-v2-base-multilingual`, cross-encoder
    tipo BERT-base): con 20 candidatos (el 4x que sugería originalmente el
    plan) tardaba ~19-70s reales, muy por encima de lo tolerable para un
    turno de chat — de ahí el cambio de modelo y de multiplicador.
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

    candidate_k = top_k * _RERANK_CANDIDATE_MULTIPLIER
    results = await vector_store.search(vector, sparse_vector, top_k=candidate_k, collection_id=collection_id)

    if results:
        # rerank() es CPU-bound (cross-encoder sentence-transformers/torch)
        # y bloqueante — a thread aparte, mismo criterio que
        # embed_query/embed_query_sparse arriba.
        scores = await asyncio.to_thread(rerank, query, [chunk.text for chunk in results])
        for chunk, score in zip(results, scores, strict=True):
            # Pisa el score de fusión RRF (rango arbitrario, solo sirve para
            # ordenar entre sí) con el del reranker — más informativo aguas
            # abajo, y consistente con el orden final que se devuelve.
            chunk.score = score
        results.sort(key=lambda chunk: chunk.score, reverse=True)
        results = results[:top_k]

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


@mcp.tool
async def report_generate_table(
    format: Literal["txt", "csv", "xlsx"], title: str, columns: list[str], rows: list[list[str]]
) -> str:
    """Genera un archivo descargable con datos tabulares ya armados
    (plan-v3.md, Fase 20) y devuelve la URL pública para descargarlo.

    Usar SOLO cuando el usuario pida explícitamente un archivo/reporte/
    exportar datos (ej. "dame esto en un Excel", "expórtamelo") — no para
    mostrar resultados normales en el chat, ahí alcanza con responder en
    texto/markdown como siempre. `rows` tiene que venir ya armado por vos
    (ej. el cruce/diff de resultados de dos consultas de `data-platform`) —
    esta tool solo escribe el archivo, no consulta ni transforma datos.

    `format`: "csv"/"xlsx" para abrir en Excel u otra planilla, "txt" para
    texto plano simple. Todas las celdas se guardan como texto.
    """
    writer = {"txt": reports.write_txt, "csv": reports.write_csv, "xlsx": reports.write_xlsx}[format]
    # CPU/IO-bound (escritura a disco, openpyxl arma el .xlsx en memoria
    # antes de guardarlo) — a thread aparte, mismo criterio que el resto de
    # las funciones bloqueantes de este módulo.
    path = await asyncio.to_thread(writer, title, columns, rows)
    url = f"{PUBLIC_BASE_URL}{REPORTS_URL_PATH}/{path.name}"
    logger.info("report_generated", format=format, filename=path.name, columns=len(columns), rows=len(rows))
    return url


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
