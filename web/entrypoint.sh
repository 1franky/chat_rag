#!/bin/sh
# Entrypoint del contenedor chat-web: aplica migraciones y arranca el
# comando pasado (Daphne por defecto, ver compose.yaml). chat-worker usa
# este mismo Dockerfile pero con `command: celery ...`, que también pasa
# por acá — migrate es idempotente así que no hay problema en correrlo
# también ahí.
#
# collectstatic NO va acá: corre en build time (ver Dockerfile), porque
# con read_only: true el filesystem del contenedor no admite escritura en
# runtime salvo en los bind mounts explícitos (/data/sqlite, /data/media).
set -e

# Solo aplica de verdad en chat-worker (es el único target que precarga el
# modelo — ver Dockerfile); en chat-web /opt/model-cache-seed no existe y
# el bloque de más abajo no hace nada. El export de LD_PRELOAD/
# GLIBC_TUNABLES es inofensivo igual para chat-web.
#
# "cannot allocate memory in static TLS block" al importar
# sentence-transformers en ARM64 (rag_shared.embeddings, usado por la task
# de ingesta en chat-worker) — mismo problema y mismo fix que en
# rag-mcp/entrypoint.sh, ver el comentario ahí para el detalle.
GOMP="$(find /app/.venv -iname 'libgomp-*.so*' | head -1)"
if [ -n "$GOMP" ]; then
    export LD_PRELOAD="$GOMP"
fi
export GLIBC_TUNABLES="glibc.rtld.optional_static_tls=2097152"

# El modelo se precarga en build time en /opt/model-cache-seed y no
# directo en MODEL_CACHE_DIR: en runtime ahí se monta el volumen
# models-cache (compartido con chat-rag-mcp), que la primera vez está
# vacío y taparía lo precargado. Si todavía está vacío, se semilla.
SEED_DIR=/opt/model-cache-seed
TARGET_DIR="${MODEL_CACHE_DIR:-/app/models}"
if [ -d "$SEED_DIR" ] && [ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
    mkdir -p "$TARGET_DIR"
    cp -a "$SEED_DIR"/. "$TARGET_DIR"/
fi

python manage.py migrate --noinput

exec "$@"
