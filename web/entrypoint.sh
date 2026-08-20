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
#
# migrate corre con flock sobre un lock file en /data/sqlite/: chat-web y
# chat-worker arrancan mas o menos al mismo tiempo y ambos corren migrate
# contra el mismo SQLite — sin el lock, la primera vez que hay una
# migración de verdad para aplicar (no un no-op) los dos la corren en
# paralelo y uno de los dos pincha con "table already exists".
set -e

# Solo aplica de verdad en chat-worker (es el único target que precarga el
# modelo — ver Dockerfile); en chat-web /opt/model-cache-seed no existe.
#
# IMPORTANTE: a diferencia del resto de este archivo, este bloque NO es
# inofensivo para chat-web — se probó y confirmó. LD_PRELOAD/GLIBC_TUNABLES
# quedan exportados para TODO lo que este proceso ejecute después (incluido
# el subproceso `claude` del Agent SDK, Fase 4), y forzarle libgomp.so por
# LD_PRELOAD a un binario compilado con Bun (que no lo espera ni lo
# necesita) lo hace abortar el arranque con "panic(main thread): abort()
# called" — un rato largo de bisección para encontrarlo. chat-web nunca
# importa sentence-transformers (el import es perezoso, ver
# rag_shared/embeddings.py) así que no le hace falta este fix para nada.
SEED_DIR=/opt/model-cache-seed
if [ -d "$SEED_DIR" ]; then
    # "cannot allocate memory in static TLS block" al importar
    # sentence-transformers en ARM64 (rag_shared.embeddings, usado por la
    # task de ingesta) — mismo problema y mismo fix que en
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
    TARGET_DIR="${MODEL_CACHE_DIR:-/app/models}"
    if [ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
        mkdir -p "$TARGET_DIR"
        cp -a "$SEED_DIR"/. "$TARGET_DIR"/
    fi
fi

# Agent SDK (chat-web, Fase 4): las credenciales de Claude Code están
# montadas de solo lectura en /creds/claude-readonly(.json) — el propio
# subproceso `claude` necesita escribir en CLAUDE_CONFIG_DIR (guarda ahí el
# transcript de cada sesión, para poder resumir la conversación en el
# siguiente mensaje), así que se copian a un directorio escribible en cada
# arranque (refleja el estado de auth más reciente del host; el transcript
# de sesiones ya escrito ahí no se toca). Solo aplica a chat-web —
# chat-worker no monta /creds/claude-readonly, así que este bloque no hace
# nada ahí.
if [ -d /creds/claude-readonly ] && [ -n "$CLAUDE_CONFIG_DIR" ]; then
    mkdir -p "$CLAUDE_CONFIG_DIR"
    [ -f /creds/claude-readonly/.credentials.json ] && cp /creds/claude-readonly/.credentials.json "$CLAUDE_CONFIG_DIR/.credentials.json"
    [ -f /creds/claude-readonly.json ] && cp /creds/claude-readonly.json "$CLAUDE_CONFIG_DIR/.claude.json"
fi

flock /data/sqlite/.migrate.lock python manage.py migrate --noinput

exec "$@"
