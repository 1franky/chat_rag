# chat_rag

Plataforma personal tipo chat con [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview), el MCP existente (`data-platform-mcp`) y un RAG propio expuesto también como MCP. Todo dockerizado y aislado en la red `ai-platform`.

> 📋 El diseño completo (arquitectura, decisiones, fases de implementación, riesgos) vive en [`plan.md`](./plan.md).

## Estado del proyecto

🚧 En construcción — todavía no hay código, solo el plan de implementación (Fase 0 en curso).

## Stack

- **Backend**: Django 5 + Channels/Daphne (SSE streaming), SQLite
- **Chat**: `claude-agent-sdk` (Python), streaming de tokens, tools vía MCP
- **RAG**: parseo por formato (PDF, DOCX, PPTX, XLSX, CSV, MD, imágenes con OCR), `sentence-transformers` (`intfloat/multilingual-e5-small`), Qdrant como vector store
- **Async**: Celery + Redis
- **Frontend**: Django templates + Tailwind CSS + HTMX + Alpine.js, sin build de Node
- **Infra**: Docker Compose, red externa `ai-platform`, contenedores `read_only` y sin capacidades extra

## Requisitos

- Ubuntu 20.04+ en arquitectura ARM64 (aarch64)
- Docker + Docker Compose v2
- Red Docker `ai-platform` ya creada (`docker network create ai-platform` si no existe)
- MCP `data-platform-mcp` corriendo en esa misma red
- Login previo de Claude Code en el host (`~/.claude/` populado) si se usa la suscripción Pro en lugar de API key

## Quickstart (cuando el proyecto esté implementado)

```bash
# Clonar y entrar
git clone git@github.com:1franky/chat_rag.git
cd chat_rag

# Configurar variables de entorno
cp .env.example .env
# editar .env: SECRET_KEY, etc.

# Levantar todo
docker compose up -d

# Crear el usuario admin (solo primera vez)
docker compose exec chat-web python manage.py createsuperuser

# Inicializar la colección de Qdrant (solo primera vez)
docker compose exec chat-rag-mcp python /app/scripts/init_qdrant.py
```

Luego abrir `http://localhost:3004` y hacer login.

Más comandos de operación (logs, backups, reindexado, etc.) en la [sección 10 de `plan.md`](./plan.md#10-comandos-de-operación).

## Estructura

```
chat_rag/
├── compose.yaml
├── web/          # Django app (chat, ingesta, accounts, core)
├── rag-mcp/      # Servidor MCP del RAG (FastMCP)
├── shared/       # Librería común: parsers, chunking, modelos
├── data/         # Volúmenes locales (gitignored)
└── scripts/      # Backup, restore, inicialización de Qdrant
```

Detalle completo en la [sección 3 de `plan.md`](./plan.md#3-estructura-de-directorios).

## Seguridad

- Uso 100% personal, sin registro público, un único superusuario
- Contenedores `read_only`, `cap_drop: [ALL]`, `no-new-privileges`
- Solo el puerto de la UI (`127.0.0.1:3004`) se expone al host
- Secrets vía `.env`, nunca en las imágenes

## Fuera de alcance (v1)

Multi-usuario, reranker, búsqueda híbrida, compartir conversaciones, voz, fine-tuning. Ver [sección 11 de `plan.md`](./plan.md#11-fuera-de-alcance-v1) para el detalle completo.

## Licencia

Proyecto personal, sin licencia pública definida.
