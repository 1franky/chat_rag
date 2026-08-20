#!/bin/sh
# Entrypoint del contenedor chat-rag-mcp.
set -e

# "cannot allocate memory in static TLS block" al importar
# sentence-transformers en ARM64: con Django+Celery+torch+sklearn+etc.
# cargados en el mismo proceso, el conjunto de librerías con TLS estático
# agota el margen que reserva glibc — y encima parece no-determinístico
# (sensible a ASLR: no siempre pasa). Dos mitigaciones, no conflictúan:
# - LD_PRELOAD a la copia de libgomp de scikit-learn: torch trae su propia
#   copia también, cargar las dos duplica el consumo de TLS innecesariamente.
# - GLIBC_TUNABLES=glibc.rtld.optional_static_tls: agranda el margen que
#   glibc reserva para TLS estático de libs cargadas dinámicamente después
#   del arranque (glibc >= 2.35 — la imagen base es Debian trixie, tiene
#   2.41, así que aplica).
GOMP="$(find /app/.venv -iname 'libgomp-*.so*' | head -1)"
if [ -n "$GOMP" ]; then
    export LD_PRELOAD="$GOMP"
fi
export GLIBC_TUNABLES="glibc.rtld.optional_static_tls=2097152"

# El modelo se precarga en build time en /opt/model-cache-seed y no
# directo en MODEL_CACHE_DIR: en runtime ahí se monta el volumen
# models-cache (compartido con chat-worker), que la primera vez está
# vacío y taparía lo precargado — se perdería el ahorro de la descarga.
# Si el volumen todavía está vacío, se semilla con lo que ya bajamos.
SEED_DIR=/opt/model-cache-seed
TARGET_DIR="${MODEL_CACHE_DIR:-/app/models}"
if [ -d "$SEED_DIR" ] && [ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
    mkdir -p "$TARGET_DIR"
    cp -a "$SEED_DIR"/. "$TARGET_DIR"/
fi

# Se asegura de que la colección rag_documents exista antes de arrancar
# (idempotente — hace lo mismo que scripts/init_qdrant.py, pero automático
# en cada arranque para no depender de correrlo a mano la primera vez).
python -c "import asyncio; from rag_shared.vector_store import ensure_collection; asyncio.run(ensure_collection())"

exec "$@"
