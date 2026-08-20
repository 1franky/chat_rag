# syntax=docker/dockerfile:1
#
# Servidor MCP del RAG (FastMCP). Expone rag_search, rag_list_documents y
# rag_get_document_chunks sobre la colección de Qdrant.

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
# scripts/init_qdrant.py corre dentro de este contenedor (ver plan.md, sección 10).
COPY scripts/ ./scripts/

RUN --mount=type=cache,target=/root/.cache/uv \
    cd rag-mcp && uv sync

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /app/rag-mcp

# Precarga el modelo de embeddings en build time para no pagar la descarga
# (~470 MB) en el primer arranque del contenedor. LD_PRELOAD evita el
# "cannot allocate memory in static TLS block" de scikit-learn+torch en
# ARM64 (ver entrypoint.sh para el detalle).
RUN LD_PRELOAD="$(find /app/.venv -iname 'libgomp-*.so*' | head -1)" \
    python -c "from embeddings import preload; preload()"

RUN chmod +x entrypoint.sh
ENTRYPOINT ["sh", "entrypoint.sh"]
CMD ["python", "server.py"]
