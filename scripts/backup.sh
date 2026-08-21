#!/bin/bash
# Backup completo de chat_rag (plan.md, Fase 7): snapshot de la colección de
# Qdrant + backup consistente de SQLite + tar de MEDIA_ROOT, todo empaquetado
# en un solo tarball con timestamp. Pensado para correr a mano o por cron
# (ver scripts/install_cron.sh) — no asume ninguna variable de entorno del
# shell interactivo, todo lo que necesita lo lee de .env/compose.yaml.
#
# Uso: scripts/backup.sh [directorio_de_backups]
#   (default: <repo>/backups)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

BACKUPS_DIR="${1:-$REPO_DIR/backups}"
# Retención consciente del tamaño (plan-v2.md, Fase 9) — reemplaza la
# retención por antigüedad de la Fase 7 (BACKUP_RETENTION_DAYS): con backup
# diario por cron, si el tamaño de cada backup crece (más documentos,
# colección de Qdrant más grande), retener por días podía llenar el disco
# antes de que la retención llegara a borrar nada.
MAX_COUNT="${BACKUP_MAX_COUNT:-2}"
MAX_SIZE_MB="${BACKUP_MAX_SIZE_MB:-5120}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M)"
WORK_DIR="$(mktemp -d)"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-rag_documents}"
# Bind mount de solo chat-worker que también es visible desde el host (ver
# compose.yaml) — el punto de paso para mover archivos entre los dos sin
# pedirle permisos/capabilities extra a ningún contenedor solo para esto.
SHARED_TMP="$REPO_DIR/data/sqlite/.backup-tmp-qdrant.snapshot"

log() { echo "[backup $(date '+%Y-%m-%dT%H:%M:%S%z')] $*"; }

cleanup() {
    rm -rf "$WORK_DIR"
    rm -f "$REPO_DIR/data/sqlite/.backup-tmp.sqlite3" "$SHARED_TMP"
}
trap cleanup EXIT

log "arrancando backup -> $BACKUPS_DIR/$TIMESTAMP.tar.gz"
mkdir -p "$BACKUPS_DIR"

# --- 1. Snapshot de Qdrant -------------------------------------------------
# Todo el ciclo de vida del snapshot (crear, descargar, borrar) se maneja
# vía la API HTTP de Qdrant desde DENTRO de chat-worker (con httpx, ya en
# sus dependencias) en vez de con un contenedor `docker run` efímero:
# chat-qdrant no expone su puerto al host a propósito (compose.yaml), y
# chat-worker ya está en la red correcta y ya tiene acceso de escritura a
# data/sqlite (el bind mount que se usa acá para sacar el archivo al host) —
# no hace falta pedirle permisos de lectura sobre data/qdrant-snapshots
# (que además quedan root:root, dueño de la imagen oficial de qdrant) a
# nada ni a nadie más.
log "snapshot de Qdrant (colección $QDRANT_COLLECTION)..."
SNAPSHOT_NAME="$(docker compose exec -T chat-worker python -c "
import httpx
base = 'http://chat-qdrant:6333/collections/$QDRANT_COLLECTION/snapshots'
r = httpx.post(base, timeout=60)
r.raise_for_status()
name = r.json()['result']['name']

with httpx.stream('GET', f'{base}/{name}', timeout=120) as resp:
    resp.raise_for_status()
    with open('/data/sqlite/.backup-tmp-qdrant.snapshot', 'wb') as f:
        for chunk in resp.iter_bytes():
            f.write(chunk)

httpx.delete(f'{base}/{name}', timeout=30)
print(name)
")"
if [ -z "$SNAPSHOT_NAME" ] || [ ! -f "$SHARED_TMP" ]; then
    log "ERROR: no se pudo crear/descargar el snapshot de Qdrant"
    exit 1
fi
cp "$SHARED_TMP" "$WORK_DIR/qdrant-$QDRANT_COLLECTION.snapshot"
log "  -> $SNAPSHOT_NAME ($(du -h "$WORK_DIR/qdrant-$QDRANT_COLLECTION.snapshot" | cut -f1))"

# --- 2. Backup consistente de SQLite ---------------------------------------
# `sqlite3.Connection.backup()` (stdlib) es el equivalente programático del
# comando `.backup` del CLI sqlite3 — usa la online backup API de SQLite,
# segura con writes concurrentes de chat-web/chat-worker.
log "backup consistente de SQLite..."
docker compose exec -T chat-worker python -c "
import sqlite3
src = sqlite3.connect('/data/sqlite/db.sqlite3')
dst = sqlite3.connect('/data/sqlite/.backup-tmp.sqlite3')
with dst:
    src.backup(dst)
dst.close()
src.close()
"
cp "$REPO_DIR/data/sqlite/.backup-tmp.sqlite3" "$WORK_DIR/db.sqlite3"
log "  -> db.sqlite3 ($(du -h "$WORK_DIR/db.sqlite3" | cut -f1))"

# --- 3. Tar de MEDIA_ROOT (documentos subidos) -------------------------
log "empaquetando data/media..."
tar czf "$WORK_DIR/media.tar.gz" -C "$REPO_DIR/data" media
log "  -> media.tar.gz ($(du -h "$WORK_DIR/media.tar.gz" | cut -f1))"

# --- 4. Tarball final -------------------------------------------------------
FINAL="$BACKUPS_DIR/$TIMESTAMP.tar.gz"
tar czf "$FINAL" -C "$WORK_DIR" .
log "backup completo: $FINAL ($(du -h "$FINAL" | cut -f1))"

# --- 5. Retención (cantidad + tamaño) ---------------------------------------
# Dos criterios en cascada, cada uno logueado por separado para que quede
# claro en backups/cron.log cuál disparó el borrado:
#   1. Cantidad: como mucho $MAX_COUNT backups (default 2) — se borra todo
#      lo que sobre de los más recientes.
#   2. Tamaño: de los que queden (como mucho $MAX_COUNT), si combinados
#      superan $MAX_SIZE_MB, se borran todos menos el más reciente.
log "aplicando retención (máx $MAX_COUNT backups, ${MAX_SIZE_MB}MB combinados)..."

# `ls -t`: orden por mtime, más reciente primero. `2>/dev/null || true`
# porque bajo `set -e` un glob sin matches (no debería pasar acá, ya que
# el backup recién creado siempre está, pero por las dudas) haría fallar a
# `ls` con "No such file or directory" y abortaría el script entero.
mapfile -t all_backups < <(cd "$BACKUPS_DIR" && ls -t -- *.tar.gz 2>/dev/null || true)

if [ "${#all_backups[@]}" -gt "$MAX_COUNT" ]; then
    for old in "${all_backups[@]:$MAX_COUNT}"; do
        log "  borrado (excede $MAX_COUNT backups): $old"
        rm -f "$BACKUPS_DIR/$old"
    done
fi

mapfile -t kept_backups < <(cd "$BACKUPS_DIR" && ls -t -- *.tar.gz 2>/dev/null || true)

if [ "${#kept_backups[@]}" -gt 1 ]; then
    total_kb=0
    for f in "${kept_backups[@]}"; do
        total_kb=$((total_kb + $(du -k "$BACKUPS_DIR/$f" | cut -f1)))
    done
    total_mb=$((total_kb / 1024))
    if [ "$total_mb" -gt "$MAX_SIZE_MB" ]; then
        log "  ${#kept_backups[@]} backups combinados pesan ${total_mb}MB (> ${MAX_SIZE_MB}MB): conservando solo el más reciente"
        for old in "${kept_backups[@]:1}"; do
            log "  borrado (excede tamaño combinado): $old"
            rm -f "$BACKUPS_DIR/$old"
        done
    fi
fi

log "listo."
