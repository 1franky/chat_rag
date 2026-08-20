#!/bin/sh
# Entrypoint del contenedor chat-rag-mcp.
set -e

# scikit-learn y torch traen cada uno su propia copia embebida de libgomp;
# cargar las dos agota el bloque TLS estático de glibc en ARM64 y revienta
# con "cannot allocate memory in static TLS block" al importar
# sentence-transformers. Precargar la copia de scikit-learn evita que se
# cargue dos veces. Ver también la precarga del modelo en el Dockerfile.
GOMP="$(find /app/.venv -iname 'libgomp-*.so*' | head -1)"
if [ -n "$GOMP" ]; then
    export LD_PRELOAD="$GOMP"
fi

# Se asegura de que la colección rag_documents exista antes de arrancar
# (idempotente — hace lo mismo que scripts/init_qdrant.py, pero automático
# en cada arranque para no depender de correrlo a mano la primera vez).
python -c "import asyncio; from vector_store import ensure_collection; asyncio.run(ensure_collection())"

exec "$@"
