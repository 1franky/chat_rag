# syntax=docker/dockerfile:1
#
# Servidor MCP del RAG (FastMCP). Expone rag_search, rag_list_documents y
# rag_get_document_chunks sobre la colección de Qdrant.
#
# NOTA (Fase 0): server.py, embeddings.py, qdrant_client.py y entrypoint.sh
# se implementan en la Fase 2. Hasta entonces esta imagen no compila un
# contenedor funcional — solo deja listo el andamiaje de dependencias.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Instala dependencias primero (cache de capas): shared/ es dependencia local editable.
COPY shared/ ./shared/
COPY rag-mcp/pyproject.toml ./rag-mcp/pyproject.toml

RUN --mount=type=cache,target=/root/.cache/uv \
    cd rag-mcp && uv sync --no-install-project

COPY rag-mcp/ ./rag-mcp/

RUN --mount=type=cache,target=/root/.cache/uv \
    cd rag-mcp && uv sync

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /app/rag-mcp

# Precarga del modelo de embeddings en build time para evitar descarga en el
# primer arranque (Fase 2, junto con embeddings.py):
# RUN python -c "from embeddings import preload; preload()"

ENTRYPOINT ["sh", "entrypoint.sh"]
