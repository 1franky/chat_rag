"""Cliente de Qdrant, compartido entre chat-rag-mcp (búsqueda) y el task de
ingesta de chat-worker (upsert/delete al indexar documentos).

Hay dos familias de funciones:
- Async (`search`, `get_document_chunks`, `ensure_collection`, `ping`):
  para chat-rag-mcp, que corre FastMCP sobre un único event loop
  persistente — el `AsyncQdrantClient` cacheado vive tranquilo ahí.
- Sync (`upsert_chunks_sync`, `delete_document_sync`,
  `ensure_collection_sync`): para el task de ingesta en chat-worker.
  Celery corre las tasks en procesos sync; si el cliente async cacheado
  se creara dentro de un `asyncio.run()` por task, quedaría atado a ESE
  event loop y el siguiente `asyncio.run()` (otra task) reventaría al
  reusarlo. Más simple: un `QdrantClient` sync normal para ese lado.

NOTA: plan.md (sección 3) lo llama `qdrant_client.py`, pero ese nombre
colisiona con el paquete pip `qdrant-client` (se importa como
`qdrant_client`): si algún día se ejecuta un script suelto desde este mismo
directorio, Python antepone la carpeta a `sys.path` y `import qdrant_client`
se resolvería contra este propio archivo en vez del paquete instalado. Se
llama `vector_store.py` para evitar el shadowing.
"""

from __future__ import annotations

import os
import uuid
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, QdrantClient, models

from rag_shared.models import Chunk

QDRANT_URL = os.environ.get("QDRANT_URL", "http://chat-qdrant:6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "rag_documents")

# intfloat/multilingual-e5-small: 384 dimensiones (plan.md, sección 2.2)
EMBEDDING_DIM = 384

# Namespace fijo para derivar IDs de punto determinísticos a partir de
# (document_id, chunk_index) — así reprocesar un documento pisa sus propios
# puntos en vez de acumular duplicados.
_POINT_ID_NAMESPACE = uuid.UUID("6f6f6f6f-6f6f-6f6f-6f6f-6f6f6f6f6f6f")


def _point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{document_id}:{chunk_index}"))


def _build_points(document_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> list[models.PointStruct]:
    if len(chunks) != len(vectors):
        raise ValueError("chunks y vectors deben tener la misma longitud")
    return [
        models.PointStruct(
            id=_point_id(document_id, chunk.chunk_index),
            vector=vector,
            payload={
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "page": chunk.page,
                "section": chunk.section,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def _delete_document_filter(document_id: str) -> models.FilterSelector:
    return models.FilterSelector(
        filter=models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
        )
    )


def _chunk_from_point(point, score: float | None = None) -> Chunk:
    payload = point.payload or {}
    return Chunk(
        document_id=payload["document_id"],
        chunk_index=payload["chunk_index"],
        text=payload["text"],
        page=payload.get("page"),
        section=payload.get("section"),
        score=score,
    )


_VECTORS_CONFIG = models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE)


# --- Async (chat-rag-mcp) ----------------------------------------------


@lru_cache(maxsize=1)
def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=QDRANT_URL)


async def ping() -> bool:
    """Verifica conectividad con Qdrant. Usado por /health."""
    try:
        await get_client().get_collections()
        return True
    except Exception:
        return False


async def ensure_collection() -> bool:
    """Crea la colección `rag_documents` (384 dim, cosine) si no existe.

    Devuelve True si la creó, False si ya existía.
    """
    client = get_client()
    if await client.collection_exists(COLLECTION_NAME):
        return False
    await client.create_collection(collection_name=COLLECTION_NAME, vectors_config=_VECTORS_CONFIG)
    return True


async def search(query_vector: list[float], top_k: int = 5) -> list[Chunk]:
    """Busca los `top_k` chunks más similares al vector de query."""
    results = await get_client().query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
    )
    return [_chunk_from_point(point, score=point.score) for point in results.points]


async def get_document_chunks(document_id: str) -> list[Chunk]:
    """Todos los chunks de un documento, ordenados por chunk_index."""
    client = get_client()
    points: list[models.Record] = []
    offset = None
    while True:
        batch, offset = await client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
            ),
            limit=256,
            offset=offset,
            with_vectors=False,
        )
        points.extend(batch)
        if offset is None:
            break

    chunks = [_chunk_from_point(point) for point in points]
    chunks.sort(key=lambda c: c.chunk_index)
    return chunks


# --- Sync (chat-worker / task de ingesta) -------------------------------


@lru_cache(maxsize=1)
def get_sync_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection_sync() -> bool:
    client = get_sync_client()
    if client.collection_exists(COLLECTION_NAME):
        return False
    client.create_collection(collection_name=COLLECTION_NAME, vectors_config=_VECTORS_CONFIG)
    return True


def upsert_chunks_sync(document_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    """Guarda (o pisa, si ya existían) los puntos de un documento."""
    points = _build_points(document_id, chunks, vectors)
    get_sync_client().upsert(collection_name=COLLECTION_NAME, points=points)


def delete_document_sync(document_id: str) -> None:
    """Borra todos los chunks de un documento (filtro por payload)."""
    get_sync_client().delete(collection_name=COLLECTION_NAME, points_selector=_delete_document_filter(document_id))
