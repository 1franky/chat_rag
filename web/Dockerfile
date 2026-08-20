# syntax=docker/dockerfile:1
#
# Multi-stage: `base` instala dependencias comunes; `web` corre Daphne (ASGI),
# `worker` corre Celery. Ambos targets comparten la misma imagen base para no
# duplicar la instalación de dependencias Python.
#
# NOTA (Fase 0): el código de la app (manage.py, config/, entrypoint.sh) se
# añade en la Fase 1. Hasta entonces esta imagen no compila un contenedor
# funcional — solo deja listo el andamiaje de dependencias.

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

# --- Target: web (servidor ASGI) ---
FROM base AS web

ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

# --- Target: worker (Celery) ---
FROM base AS worker

CMD ["celery", "-A", "config", "worker", "-l", "info", "-c", "2"]
