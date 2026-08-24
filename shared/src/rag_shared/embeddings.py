"""Wrapper singleton de los modelos de embeddings: denso (sentence-transformers),
sparse (fastembed, BM25 — plan-v2.md Fase 12, búsqueda híbrida) y de reranking
(sentence-transformers CrossEncoder — plan-v3.md Fase 17).

Los tres modelos se cargan una sola vez por proceso y se cachean en
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
    from sentence_transformers import CrossEncoder, SentenceTransformer

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
# Qdrant/bm25: no es un modelo de ML propiamente (no tiene pesos entrenados),
# fastembed lo expone con la misma interfaz que el resto de sus modelos
# sparse para poder combinarlo con el denso sin lógica aparte.
SPARSE_EMBEDDING_MODEL = os.environ.get("SPARSE_EMBEDDING_MODEL", "Qdrant/bm25")
# Cross-encoder multilingüe (mMARCO, cubre español) — se evaluó primero el
# único modelo de reranking que trae fastembed marcado como multilingüe
# (`jinaai/jina-reranker-v2-base-multilingual`, 1.1GB) pero en este host
# (2 CPUs físicas, ARM64) tardaba ~19-70s por búsqueda real (candidatos de
# hasta 800 caracteres, el CHUNK_SIZE de rag_shared/chunker.py) — inviable
# para un chat interactivo. Este modelo (~470MB, mismo framework
# sentence-transformers que ya usa el embedding denso) da el mismo tipo de
# mejora de precisión a una fracción del costo: ~5-6s para 10 candidatos.
RERANK_MODEL = os.environ.get("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
# CRÍTICO en este host (2 CPUs físicas, chat-rag-mcp limitado a 1.0 CPU vía
# cgroup en compose.yaml): sin fijar esto, torch arranca su pool de threads
# según `os.cpu_count()` (ve las 2 CPUs del host, no la cuota del cgroup) —
# esos threads de más quedan constantemente throttled por el cgroup, mismo
# problema que se vio primero con el reranker de fastembed/onnxruntime
# (~4s con threads=1 vs ~70s sin fijar, medido en este host). Default 1 =
# mismo número que el límite de CPU del contenedor; si se sube ese límite
# en compose.yaml, subir este valor en la misma proporción.
RERANK_THREADS = int(os.environ.get("RERANK_THREADS", "1"))
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


@lru_cache(maxsize=1)
def get_reranker() -> "CrossEncoder":
    import torch
    from sentence_transformers import CrossEncoder

    # torch.set_num_threads (no un kwarg del constructor de CrossEncoder):
    # es process-wide, pero este proceso no hace otra cosa en paralelo que
    # se beneficie de más de un thread — ver el comentario de RERANK_THREADS.
    torch.set_num_threads(RERANK_THREADS)
    return CrossEncoder(RERANK_MODEL, cache_folder=MODEL_CACHE_DIR, device="cpu")


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


def rerank(query: str, texts: list[str]) -> list[float]:
    """Score de relevancia query-texto por cross-encoder (plan-v3.md, Fase
    17) — un float por texto, mismo orden que `texts`. A diferencia de los
    embeddings densos/sparse (comparan vectores calculados por separado),
    el cross-encoder mira query+texto juntos en cada pasada: más preciso,
    pero no se puede precalcular por texto de antemano — por eso se usa
    solo sobre los candidatos ya fusionados (RRF), no sobre todo el corpus.
    """
    if not texts:
        return []
    pairs = [(query, text) for text in texts]
    return [float(score) for score in get_reranker().predict(pairs)]


def preload() -> None:
    """Descarga y cachea los modelos (denso, sparse y reranker). Se llama en build-time del Dockerfile."""
    get_model()
    get_sparse_model()
    get_reranker()


if __name__ == "__main__":
    preload()
