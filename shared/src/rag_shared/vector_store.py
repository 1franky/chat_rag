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

from rag_shared.embeddings import SparseVector
from rag_shared.models import Chunk

QDRANT_URL = os.environ.get("QDRANT_URL", "http://chat-qdrant:6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "rag_documents")

# intfloat/multilingual-e5-small: 384 dimensiones (plan.md, sección 2.2)
EMBEDDING_DIM = 384

# Búsqueda híbrida (plan-v2.md, Fase 12): el vector denso queda "sin nombre"
# (compatibilidad con la colección ya existente, que no tiene vectores
# nombrados) y el sparse (BM25, vía fastembed) se guarda en un named vector
# aparte — Qdrant exige nombre para vectores sparse.
SPARSE_VECTOR_NAME = "bm25"

# Namespace fijo para derivar IDs de punto determinísticos a partir de
# (document_id, chunk_index) — así reprocesar un documento pisa sus propios
# puntos en vez de acumular duplicados.
_POINT_ID_NAMESPACE = uuid.UUID("6f6f6f6f-6f6f-6f6f-6f6f-6f6f6f6f6f6f")


def _point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{document_id}:{chunk_index}"))


def _build_points(
    document_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    sparse_vectors: list[SparseVector],
    collection_id: str | None = None,
) -> list[models.PointStruct]:
    if not (len(chunks) == len(vectors) == len(sparse_vectors)):
        raise ValueError("chunks, vectors y sparse_vectors deben tener la misma longitud")
    return [
        models.PointStruct(
            id=_point_id(document_id, chunk.chunk_index),
            # "" = nombre del vector denso "sin nombre" (DEFAULT_VECTOR_NAME
            # interno de qdrant-client), junto al sparse nombrado.
            vector={
                "": vector,
                SPARSE_VECTOR_NAME: models.SparseVector(indices=sparse_indices, values=sparse_values),
            },
            payload={
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "page": chunk.page,
                "section": chunk.section,
                # None para documentos sin colección (plan-v2.md, Fase 10) —
                # un FieldCondition de collection_id nunca matchea None, así
                # que una búsqueda acotada a una colección los deja afuera
                # correctamente sin necesitar lógica aparte.
                "collection_id": collection_id,
            },
        )
        for chunk, vector, (sparse_indices, sparse_values) in zip(chunks, vectors, sparse_vectors, strict=True)
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

# Modifier.IDF: fastembed calcula del lado del cliente solo la mitad
# "term-frequency + saturación" de la fórmula BM25 (no conoce el corpus
# completo al embeber un chunk aislado); este modifier le pide a Qdrant que
# multiplique cada score por el IDF calculado server-side sobre todo lo
# indexado en la colección — sin esto es term-frequency puro, no BM25 real.
_SPARSE_VECTORS_CONFIG = {SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)}


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
    """Crea la colección `rag_documents` (384 dim, cosine, + sparse BM25) si no existe.

    Devuelve True si la creó, False si ya existía. IMPORTANTE: no migra una
    colección ya existente sin sparse vectors (Qdrant no permite agregar un
    named vector nuevo post-creación) — para eso está el management command
    `reindex_documents` (plan-v2.md, Fase 12).
    """
    client = get_client()
    if await client.collection_exists(COLLECTION_NAME):
        return False
    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=_VECTORS_CONFIG,
        sparse_vectors_config=_SPARSE_VECTORS_CONFIG,
    )
    return True


# Cuántos candidatos trae cada rama (densa/sparse) antes de fusionar — más
# que `top_k` porque el ranking de cada una por separado no coincide
# necesariamente con el orden final post-fusión (RRF).
_PREFETCH_LIMIT = 50


def _hybrid_prefetch(
    query_vector: list[float], sparse_query: SparseVector, query_filter: models.Filter | None
) -> list[models.Prefetch]:
    sparse_indices, sparse_values = sparse_query
    return [
        models.Prefetch(query=query_vector, filter=query_filter, limit=_PREFETCH_LIMIT),
        models.Prefetch(
            query=models.SparseVector(indices=sparse_indices, values=sparse_values),
            using=SPARSE_VECTOR_NAME,
            filter=query_filter,
            limit=_PREFETCH_LIMIT,
        ),
    ]


async def search(
    query_vector: list[float],
    sparse_query: SparseVector,
    top_k: int = 5,
    collection_id: str | None = None,
) -> list[Chunk]:
    """Busca los `top_k` chunks más relevantes, combinando similitud vectorial
    (denso) y léxica (BM25 sparse) vía Reciprocal Rank Fusion (plan-v2.md,
    Fase 12) — `sparse_query` es el vector sparse ya calculado de la query
    (`rag_shared.embeddings.embed_query_sparse`).

    `collection_id` (plan-v2.md, Fase 10) acota la búsqueda a una sola
    colección de documentos; sin especificar, busca en todo lo indexado.
    """
    query_filter = None
    if collection_id is not None:
        query_filter = models.Filter(
            must=[models.FieldCondition(key="collection_id", match=models.MatchValue(value=collection_id))]
        )
    results = await get_client().query_points(
        collection_name=COLLECTION_NAME,
        prefetch=_hybrid_prefetch(query_vector, sparse_query, query_filter),
        query=models.FusionQuery(fusion=models.Fusion.RRF),
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
    """Ver docstring de `ensure_collection` (versión async) — mismo comportamiento."""
    client = get_sync_client()
    if client.collection_exists(COLLECTION_NAME):
        return False
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=_VECTORS_CONFIG,
        sparse_vectors_config=_SPARSE_VECTORS_CONFIG,
    )
    return True


def collection_has_sparse_vectors_sync() -> bool:
    """True si la colección ya existe y tiene el named vector sparse
    (plan-v2.md, Fase 12) — usado por el management command `reindex_documents`
    para decidir si hace falta recrear la colección antes de reindexar."""
    client = get_sync_client()
    if not client.collection_exists(COLLECTION_NAME):
        return False
    info = client.get_collection(COLLECTION_NAME)
    sparse_vectors = info.config.params.sparse_vectors or {}
    return SPARSE_VECTOR_NAME in sparse_vectors


def recreate_collection_sync() -> None:
    """Borra la colección (si existe) y la vuelve a crear vacía, ya con
    sparse vectors configurados. Destructivo: se usa desde el management
    command `reindex_documents`, que después reindexa todos los documentos
    activos — Qdrant no permite agregar un named vector nuevo a una
    colección existente, la única forma de migrar es recrearla."""
    client = get_sync_client()
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=_VECTORS_CONFIG,
        sparse_vectors_config=_SPARSE_VECTORS_CONFIG,
    )


def upsert_chunks_sync(
    document_id: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    sparse_vectors: list[SparseVector],
    collection_id: str | None = None,
) -> None:
    """Guarda (o pisa, si ya existían) los puntos de un documento."""
    points = _build_points(document_id, chunks, vectors, sparse_vectors, collection_id=collection_id)
    get_sync_client().upsert(collection_name=COLLECTION_NAME, points=points)


def delete_document_sync(document_id: str) -> None:
    """Borra todos los chunks de un documento (filtro por payload)."""
    get_sync_client().delete(collection_name=COLLECTION_NAME, points_selector=_delete_document_filter(document_id))


def set_document_collection_sync(document_id: str, collection_id: str | None) -> None:
    """Actualiza el `collection_id` de todos los chunks YA indexados de un
    documento (al moverlo a otra colección desde la UI, plan-v2.md Fase 10)
    — `set_payload` filtrado por `document_id`, sin re-embeber ni volver a
    subir vectores."""
    get_sync_client().set_payload(
        collection_name=COLLECTION_NAME,
        payload={"collection_id": collection_id},
        points=models.Filter(
            must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))]
        ),
    )
