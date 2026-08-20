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

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]

# --- Target: worker (Celery) ---
FROM base AS worker

# Tesseract (OCR de imágenes) se instala acá en la Fase 3, junto con los
# parsers de shared/.
CMD ["celery", "-A", "config", "worker", "-l", "info", "-c", "2"]
