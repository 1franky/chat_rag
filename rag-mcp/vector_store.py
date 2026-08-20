"""Cliente async de Qdrant para chat-rag-mcp.

Expone la conexión a la instancia propia del proyecto (`chat-qdrant`, ver
plan.md sección 2.2) y los helpers de bajo nivel que usan tanto el MCP
(`server.py`) como `scripts/init_qdrant.py`. La búsqueda real se conecta en
`rag_search` en la Fase 3 — acá solo queda lista la infraestructura.

NOTA: plan.md (sección 3) lo llama `qdrant_client.py`, pero ese nombre
colisiona con el paquete pip `qdrant-client` (se importa como
`qdrant_client`) — al correr `python server.py` desde este mismo directorio,
Python antepone esta carpeta a `sys.path`, así que `import qdrant_client`
se resolvería contra este propio archivo en vez del paquete instalado. Se
renombró a `vector_store.py` para evitar el shadowing.
"""

from __future__ import annotations

import os
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models
from rag_shared.models import Chunk

QDRANT_URL = os.environ.get("QDRANT_URL", "http://chat-qdrant:6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "rag_documents")

# intfloat/multilingual-e5-small: 384 dimensiones (plan.md, sección 2.2)
EMBEDDING_DIM = 384


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

    await client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIM,
            distance=models.Distance.COSINE,
        ),
    )
    return True


async def search(query_vector: list[float], top_k: int = 5) -> list[Chunk]:
    """Busca los `top_k` chunks más similares al vector de query.

    Helper listo para la Fase 3 (`rag_search` deja de ser un stub). En la
    Fase 2 no lo invoca ninguna tool todavía.
    """
    client = get_client()
    results = await client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
    )
    return [
        Chunk(
            document_id=point.payload["document_id"],
            chunk_index=point.payload["chunk_index"],
            text=point.payload["text"],
            page=point.payload.get("page"),
            section=point.payload.get("section"),
            score=point.score,
        )
        for point in results.points
    ]
