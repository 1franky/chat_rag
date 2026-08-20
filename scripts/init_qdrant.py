#!/usr/bin/env python
"""Script one-off: crea la colección `rag_documents` en Qdrant si no existe.

Uso (dentro del contenedor chat-rag-mcp, que es donde vive vector_store.py):
    docker compose exec chat-rag-mcp python /app/scripts/init_qdrant.py
"""

import asyncio
import sys

sys.path.insert(0, "/app/rag-mcp")

from vector_store import COLLECTION_NAME, QDRANT_URL, ensure_collection  # noqa: E402


async def main() -> None:
    created = await ensure_collection()
    if created:
        print(f"Colección '{COLLECTION_NAME}' creada en {QDRANT_URL}.")
    else:
        print(f"Colección '{COLLECTION_NAME}' ya existía en {QDRANT_URL}, nada que hacer.")


if __name__ == "__main__":
    asyncio.run(main())
