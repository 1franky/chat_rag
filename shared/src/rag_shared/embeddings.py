"""Wrapper singleton de los modelos de embeddings: denso (sentence-transformers)
y sparse (fastembed, BM25 — plan-v2.md Fase 12, búsqueda híbrida).

Ambos modelos se cargan una sola vez por proceso y se cachean en
MODEL_CACHE_DIR (volumen `models-cache`, compartido con chat-worker para no
duplicarlo). `preload()` se usa en build-time del Dockerfile para no pagar
la descarga en el primer arranque del contenedor.

El import de `sentence_transformers` (carga torch) y de `fastembed` es
perezoso a propósito: si fuera top-level, cualquier cosa que importe este
módulo transitivamente —incluido chat-web, que nunca embebe nada, solo
porque apps.ingesta.views importa apps.ingesta.tasks— pagaría el costo (y el
riesgo del bug de TLS en ARM64, ver Dockerfile/entrypoint.sh) de cargar
torch en el arranque.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastembed import SparseTextEmbedding
    from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
# Qdrant/bm25: no es un modelo de ML propiamente (no tiene pesos entrenados),
# fastembed lo expone con la misma interfaz que el resto de sus modelos
# sparse para poder combinarlo con el denso sin lógica aparte.
SPARSE_EMBEDDING_MODEL = os.environ.get("SPARSE_EMBEDDING_MODEL", "Qdrant/bm25")
MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/app/models")

# multilingual-e5-small espera el prefijo "query: " / "passage: " en cada
# texto (así fue entrenado) — sin esto el retrieval degrada notablemente.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "

# Vector sparse: pares (índices de término, peso) — mismo formato "crudo"
# para query y passages, `vector_store.py` decide cómo empaquetarlo.
SparseVector = tuple[list[int], list[float]]


@lru_cache(maxsize=1)
def get_model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL, cache_folder=MODEL_CACHE_DIR)


@lru_cache(maxsize=1)
def get_sparse_model() -> "SparseTextEmbedding":
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model_name=SPARSE_EMBEDDING_MODEL, cache_dir=MODEL_CACHE_DIR)


def embed_query(text: str) -> list[float]:
    return get_model().encode(QUERY_PREFIX + text, normalize_embeddings=True).tolist()


def embed_passages(texts: list[str]) -> list[list[float]]:
    prefixed = [PASSAGE_PREFIX + t for t in texts]
    return get_model().encode(prefixed, normalize_embeddings=True).tolist()


def embed_query_sparse(text: str) -> SparseVector:
    # `query_embed` (no `embed`): para BM25 el vector de la query no lleva
    # la normalización por longitud de documento que sí aplica `embed` a
    # los passages — son dos mitades distintas de la fórmula BM25.
    (embedding,) = list(get_sparse_model().query_embed(text))
    return embedding.indices.tolist(), embedding.values.tolist()


def embed_passages_sparse(texts: list[str]) -> list[SparseVector]:
    return [(embedding.indices.tolist(), embedding.values.tolist()) for embedding in get_sparse_model().embed(texts)]


def preload() -> None:
    """Descarga y cachea los modelos (denso y sparse). Se llama en build-time del Dockerfile."""
    get_model()
    get_sparse_model()


if __name__ == "__main__":
    preload()
