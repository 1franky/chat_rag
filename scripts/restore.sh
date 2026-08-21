#!/bin/bash
# Restaura un backup de chat_rag creado por scripts/backup.sh (plan.md,
# Fase 7). DESTRUCTIVO: pisa la base SQLite, los documentos en MEDIA_ROOT y
# la colección de Qdrant actuales — pide confirmación explícita antes de
# tocar nada.
#
# Uso: scripts/restore.sh backups/2026-08-21-0300.tar.gz
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

TARBALL="${1:-}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-rag_documents}"
SHARED_TMP="$REPO_DIR/data/sqlite/.restore-tmp-qdrant.snapshot"

log() { echo "[restore $(date '+%Y-%m-%dT%H:%M:%S%z')] $*"; }

if [ -z "$TARBALL" ] || [ ! -f "$TARBALL" ]; then
    echo "Uso: $0 <ruta-al-tarball-de-backup.tar.gz>"
    exit 1
fi

echo "Esto va a REEMPLAZAR de forma irreversible:"
echo "  - la base de datos SQLite actual (data/sqlite/db.sqlite3)"
echo "  - todos los documentos en data/media/"
echo "  - la colección '$QDRANT_COLLECTION' completa en Qdrant"
echo "con el contenido de: $TARBALL"
echo
read -r -p "Escribí RESTAURAR (todo mayúsculas) para confirmar: " CONFIRM
if [ "$CONFIRM" != "RESTAURAR" ]; then
    echo "Cancelado — no se tocó nada."
    exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"; rm -f "$SHARED_TMP"' EXIT

log "extrayendo $TARBALL..."
tar xzf "$TARBALL" -C "$WORK_DIR"

for f in db.sqlite3 media.tar.gz "qdrant-$QDRANT_COLLECTION.snapshot"; do
    if [ ! -f "$WORK_DIR/$f" ]; then
        log "ERROR: el tarball no tiene '$f' — ¿es un backup válido de scripts/backup.sh?"
        exit 1
    fi
done

log "parando chat-web y chat-worker (evita escrituras durante la restauración)..."
docker compose stop chat-web chat-worker

log "restaurando SQLite..."
cp "$WORK_DIR/db.sqlite3" "$REPO_DIR/data/sqlite/db.sqlite3"

log "restaurando data/media (se borra lo que había antes)..."
rm -rf "${REPO_DIR:?}/data/media"
mkdir -p "$REPO_DIR/data/media"
tar xzf "$WORK_DIR/media.tar.gz" -C "$REPO_DIR/data"

# --- Qdrant: subir y recuperar el snapshot ----------------------------------
# La subida se hace vía la API HTTP de Qdrant desde DENTRO de chat-worker
# (con httpx), no con un contenedor `docker run` efímero — mismo motivo que
# en backup.sh (chat-qdrant no expone su puerto al host, y así se evita
# depender de una imagen externa aparte). chat-worker tiene que estar
# arriba para esto — se levanta antes que chat-web a propósito (chat-worker
# no le sirve nada al usuario directamente, así que no hay problema en que
# quede un ratito arriba solo mientras chat-web sigue abajo).
log "levantando chat-worker (necesario para restaurar Qdrant)..."
docker compose up -d chat-worker
cp "$WORK_DIR/qdrant-$QDRANT_COLLECTION.snapshot" "$SHARED_TMP"

log "restaurando snapshot de Qdrant en '$QDRANT_COLLECTION' (puede tardar)..."
docker compose exec -T chat-worker python -c "
import httpx
base = 'http://chat-qdrant:6333/collections/$QDRANT_COLLECTION/snapshots/upload'
with open('/data/sqlite/.restore-tmp-qdrant.snapshot', 'rb') as f:
    r = httpx.post(base, params={'priority': 'snapshot'}, files={'snapshot': ('snapshot', f, 'application/octet-stream')}, timeout=120)
r.raise_for_status()
print(r.json())
"

log "levantando chat-web de nuevo..."
docker compose up -d chat-web

log "listo. Verificá con: curl localhost:3004/healthz"
