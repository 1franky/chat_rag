# syntax=docker/dockerfile:1
#
# Multi-stage: `base` instala dependencias e incluye el código de la app;
# `web` corre Daphne (ASGI), `worker` corre Celery. Ambos targets comparten
# la misma imagen base para no duplicar la instalación de dependencias.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Instala dependencias primero (cache de capas): shared/ es dependencia local editable de web/.
COPY shared/ ./shared/
COPY web/pyproject.toml ./web/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    cd web && uv sync --no-install-project

COPY web/ ./web/

RUN --mount=type=cache,target=/root/.cache/uv \
    cd web && uv sync

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /app/web

# collectstatic corre acá (build time) y no en el entrypoint: con
# read_only: true en compose.yaml el filesystem del contenedor no admite
# escritura en runtime, así que STATIC_ROOT tiene que quedar ya resuelto
# dentro de la imagen. DJANGO_SECRET_KEY dummy porque el comando la exige
# pero no valida nada con ella.
RUN DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput

RUN chmod +x entrypoint.sh
ENTRYPOINT ["sh", "entrypoint.sh"]

# --- Target: web (servidor ASGI) ---
FROM base AS web

CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--loop", "asyncio"]

# --- Target: worker (Celery) ---
FROM base AS worker

# Tesseract (OCR de imágenes, parsers/image.py y fallback de pdf.py) y
# libmagic (detección real de mime type, rag_shared.mime). Solo en worker:
# chat-web nunca los necesita.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Precarga el modelo de embeddings en build time (evita la descarga de
# ~470 MB en la primera task de ingesta). Va a /opt/model-cache-seed y no a
# MODEL_CACHE_DIR: ahí se monta en runtime el volumen models-cache (vacío
# la primera vez, compartido con chat-rag-mcp), que taparía lo precargado
# — entrypoint.sh lo copia al volumen si hace falta (mismo mecanismo que
# rag-mcp/Dockerfile). LD_PRELOAD evita el "cannot allocate memory in
# static TLS block" de scikit-learn+torch en ARM64.
RUN LD_PRELOAD="$(find /app/.venv -iname 'libgomp-*.so*' | head -1)" \
    GLIBC_TUNABLES="glibc.rtld.optional_static_tls=2097152" \
    MODEL_CACHE_DIR=/opt/model-cache-seed \
    python -c "from rag_shared.embeddings import preload; preload()"

CMD ["celery", "-A", "config", "worker", "-l", "info", "-c", "2"]
