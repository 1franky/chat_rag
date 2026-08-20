#!/usr/bin/env python
"""Script one-off: crea la colección `rag_documents` en Qdrant si no existe.

Uso (dentro de cualquier contenedor con rag_shared instalado —
chat-rag-mcp o chat-worker):
    docker compose exec chat-rag-mcp python /app/scripts/init_qdrant.py
"""

import asyncio

from rag_shared.vector_store import COLLECTION_NAME, QDRANT_URL, ensure_collection


async def main() -> None:
    created = await ensure_collection()
    if created:
        print(f"Colección '{COLLECTION_NAME}' creada en {QDRANT_URL}.")
    else:
        print(f"Colección '{COLLECTION_NAME}' ya existía en {QDRANT_URL}, nada que hacer.")


if __name__ == "__main__":
    asyncio.run(main())
