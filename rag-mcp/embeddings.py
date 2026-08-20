"""Wrapper singleton de sentence-transformers.

El modelo (~470 MB) se carga una sola vez por proceso y se cachea en
MODEL_CACHE_DIR (volumen `models-cache`, compartido con chat-worker para no
duplicarlo). `preload()` se usa en build-time del Dockerfile para no pagar
la descarga en el primer arranque del contenedor.
"""

from __future__ import annotations

import os
from functools import lru_cache

from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", "/app/models")

# multilingual-e5-small espera el prefijo "query: " / "passage: " en cada
# texto (así fue entrenado) — sin esto el retrieval degrada notablemente.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL, cache_folder=MODEL_CACHE_DIR)


def embed_query(text: str) -> list[float]:
    return get_model().encode(QUERY_PREFIX + text, normalize_embeddings=True).tolist()


def embed_passages(texts: list[str]) -> list[list[float]]:
    prefixed = [PASSAGE_PREFIX + t for t in texts]
    return get_model().encode(prefixed, normalize_embeddings=True).tolist()


def preload() -> None:
    """Descarga y cachea el modelo. Se llama en build-time del Dockerfile."""
    get_model()


if __name__ == "__main__":
    preload()
