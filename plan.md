# Plan de Implementación — chat_rag

> Plataforma personal tipo chat con Claude Agent SDK, MCP existente (`data-platform-mcp`) y RAG propio expuesto como MCP. Todo dockerizado y aislado en la red `ai-platform`.

---

## 1. Contexto y restricciones

### Entorno objetivo
- **OS**: Ubuntu 20.04.6 LTS
- **Arquitectura**: aarch64 (ARM64)
- **RAM**: 12 GB
- **CPU**: solo vCPU (sin GPU)
- **Docker network existente**: `ai-platform` (externa)

### Servicios ya corriendo en `ai-platform`
| Servicio | Hostname interno | Puerto | Uso |
|---|---|---|---|
| `data-platform-mcp` | `data-platform-mcp` | 8000 | MCP existente (SQL read-only) |
| `postgres-lab` | `postgres-lab` | 5432 | Lab del MCP (NO tocar) |
| `mariadb-lab` | `mariadb-lab` | 3306 | Lab del MCP (NO tocar) |
| `mongo-lab` | `mongo-lab` | 27017 | Lab del MCP (NO tocar) |

> **Nota sobre Qdrant**: aunque el compose del MCP levanta un `qdrant`, en este proyecto se levanta uno **propio** (`chat-qdrant`) con su propio volumen y configuración. Motivos: aislar dependencias, poder reiniciar/actualizar sin afectar al MCP, evitar problemas reportados con la instancia actual, y control total sobre snapshots y backups.

**RAM ya comprometida**: ~3 GB (sin contar el Qdrant del MCP, que puede apagarse si no se usa). Presupuesto disponible para nuevos servicios: ~6 GB (dejar 3 GB al sistema).

### Restricciones que condicionan decisiones
- ARM64 descarta imágenes que solo publican amd64
- Sin GPU: modelos de embeddings livianos, sin reranker pesado en v1
- Uso 100% personal: SQLite en lugar de Postgres para Django, sin registro público
- Datos confidenciales: nada expuesto al host más allá del puerto de la UI

---

## 2. Decisiones de arquitectura

### 2.1 Servicios nuevos a añadir
| Servicio | Imagen / stack | RAM aprox |
|---|---|---|
| `chat-web` | Python 3.12 + Django 5 + Daphne (ASGI) | 400 MB |
| `chat-worker` | Python 3.12 + Celery + modelo de embeddings | 1.5 GB |
| `chat-redis` | `redis:7-alpine` | 100 MB |
| `chat-rag-mcp` | Python 3.12 + FastMCP | 300 MB |
| `chat-qdrant` | `qdrant/qdrant:v1.17.1` | 512 MB |

**Total nuevo**: ~2.8 GB. Total sistema: ~5.8 GB (asumiendo apagar el Qdrant del MCP). Deja ~6.2 GB de margen.

### 2.2 Qdrant propio del proyecto
- Servicio dedicado `chat-qdrant` en la red `ai-platform`
- Colección `rag_documents`: 384 dim, distancia cosine
- Volumen nombrado `chat-qdrant-data` para persistencia
- Puerto REST 6333 y gRPC 6334 solo accesibles dentro de la red (no expuestos al host)
- Snapshots automáticos configurables vía script (ver Fase 7)
- **Recomendación**: apagar/eliminar el servicio `qdrant` del compose del MCP si no lo usa nadie más, para liberar RAM y evitar confusión

### 2.3 Stack técnico

**Backend web**
- Django 5.x + Django Channels (para SSE streaming del chat)
- Daphne como servidor ASGI
- SQLite para datos de la app (usuarios, conversaciones, metadata de documentos)
- WhiteNoise para servir estáticos

**Frontend**
- Django templates + Tailwind CSS (CLI standalone, sin Node build)
- HTMX para interactividad sin SPA
- Alpine.js para estado local (toggle tema, dropdowns)
- `marked.js` para render de markdown
- `highlight.js` para syntax highlighting
- Sin build step, todo servido como static files

**Async & background**
- Celery + Redis como broker
- Un worker con concurrencia 2 (ingesta de docs no debe saturar embeddings)

**RAG**
- **Parseo por formato** (evitando `unstructured[all-docs]` por ARM64):
  - PDF: `pypdf` + `pdfplumber` (fallback para tablas)
  - DOCX: `python-docx`
  - PPTX: `python-pptx`
  - XLSX: `openpyxl` + `pandas`
  - CSV: `pandas`
  - MD/TXT: lectura directa
  - Imágenes (PNG/JPG): `pytesseract` (Tesseract con paquete `spa` para español)
  - Google Docs/Sheets/Slides: **Fase 6** vía Google Picker + Drive API. En v1, el usuario descarga como formato Office desde Drive.
- **Chunking**: `langchain-text-splitters` (`RecursiveCharacterTextSplitter`, chunk 800, overlap 120)
- **Embeddings**: `sentence-transformers` con `intfloat/multilingual-e5-small`
  - 384 dim, 470 MB en disco, ~150 MB en RAM inferencia
  - Soporte multilingüe (español nativo)
  - ~50-100ms por chunk en vCPU
- **Vector store**: Qdrant (colección nueva)
- **Reranker**: NO en v1. Se puede añadir `BAAI/bge-reranker-v2-m3` después si retrieval flojea.

**Chat**
- `claude-agent-sdk` (Python)
- Autenticación vía suscripción Pro personal (login en Claude Code una vez, comparte auth con SDK)
- MCPs registrados: `data-platform-mcp` (existente) + `rag-mcp` (nuevo)
- Streaming SSE al frontend

**Auth**
- `django.contrib.auth` con `AbstractUser`
- **Un solo superuser** creado vía `createsuperuser` en primer arranque
- Vista de registro **eliminada** (no existirá URL)
- Middleware `LoginRequiredMiddleware` custom que fuerza login en todas las URLs excepto `/login/` y `/static/`
- Sesiones con cookie `Secure` + `HttpOnly` + `SameSite=Strict`

### 2.4 RAG como MCP propio
El servicio `chat-rag-mcp` expondrá vía MCP:
- `rag_search(query: str, top_k: int = 5) -> list[Chunk]`
- `rag_list_documents() -> list[DocumentMeta]`
- `rag_get_document_chunks(document_id: str) -> list[Chunk]`

Ventajas de esta separación:
- Claude decide **cuándo** buscar (no siempre inyectamos contexto)
- Django solo maneja la **ingesta**, no la recuperación
- Mismo patrón mental que tu MCP existente
- Reemplazar el vector store no toca Django

### 2.5 Seguridad (siguiendo tu estándar del MCP existente)
- `read_only: true` en todos los contenedores excepto donde haya que escribir
- `cap_drop: [ALL]`
- `no-new-privileges: true`
- `tmpfs` para `/tmp`
- Solo Django expone puerto al host (`127.0.0.1:3004`)
- Redis, worker, RAG-MCP solo accesibles dentro de `ai-platform`
- Secrets vía `.env` (nunca en imágenes)

---

## 3. Estructura de directorios

```
~/docker/
├── data-analits-MCP/          # (ya existe, no tocar)
└── chat_rag/                  # NUEVO
    ├── compose.yaml
    ├── .env.example
    ├── .env                   # (gitignored)
    ├── .gitignore
    ├── README.md
    │
    ├── web/                   # Django app + Dockerfile
    │   ├── Dockerfile
    │   ├── pyproject.toml
    │   ├── manage.py
    │   ├── entrypoint.sh
    │   ├── config/            # settings, urls, asgi
    │   │   ├── __init__.py
    │   │   ├── settings.py
    │   │   ├── urls.py
    │   │   ├── asgi.py
    │   │   └── celery.py
    │   ├── apps/
    │   │   ├── accounts/      # auth custom, login view
    │   │   ├── chat/          # conversaciones, streaming, Agent SDK
    │   │   ├── ingesta/       # upload, tasks Celery, parsers
    │   │   └── core/          # base template, tema, middlewares
    │   ├── templates/
    │   │   ├── base.html
    │   │   ├── accounts/
    │   │   ├── chat/
    │   │   └── ingesta/
    │   └── static/
    │       ├── css/           # tailwind.css compilado
    │       ├── js/            # htmx, alpine, marked, highlight
    │       └── img/
    │
    ├── rag-mcp/               # Servicio MCP del RAG
    │   ├── Dockerfile
    │   ├── pyproject.toml
    │   ├── server.py          # FastMCP server
    │   ├── embeddings.py      # wrapper sentence-transformers
    │   ├── qdrant_client.py   # helper Qdrant
    │   └── entrypoint.sh
    │
    ├── shared/                # librería común (parsers, chunking)
    │   ├── pyproject.toml
    │   └── src/rag_shared/
    │       ├── parsers/       # uno por formato
    │       ├── chunker.py
    │       └── models.py      # pydantic: Chunk, Document
    │
    ├── data/                  # volúmenes (gitignored)
    │   ├── sqlite/            # db.sqlite3
    │   ├── media/             # archivos subidos originales
    │   ├── models/            # cache de sentence-transformers
    │   └── qdrant-snapshots/  # snapshots del vector store
    │
    └── scripts/
        ├── init_qdrant.py     # crea colección rag_documents
        └── create_admin.sh    # wrapper de createsuperuser
```

---

## 4. Compose nuevo (esqueleto)

Archivo: `~/docker/chat_rag/compose.yaml`

```yaml
services:
  chat-qdrant:
    image: qdrant/qdrant:v1.17.1
    restart: unless-stopped
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }
    volumes:
      - chat-qdrant-data:/qdrant/storage
      - ./data/qdrant-snapshots:/qdrant/snapshots
    expose: ["6333", "6334"]
    # Sin ports: al host — solo accesible en la red ai-platform
    healthcheck:
      test:
        - CMD
        - bash
        - -c
        - "exec 3<>/dev/tcp/127.0.0.1/6333"
      interval: 15s
      timeout: 5s
      start_period: 15s
      retries: 5
    networks: [ai-platform]

  chat-redis:
    image: redis:7-alpine
    restart: unless-stopped
    deploy:
      resources:
        limits: { cpus: "0.25", memory: 128M }
    volumes:
      - redis-data:/data
    read_only: true
    tmpfs: [/tmp:size=8m]
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    healthcheck:
      test: [CMD, redis-cli, ping]
      interval: 15s
    networks: [ai-platform]

  chat-rag-mcp:
    build:
      context: .
      dockerfile: rag-mcp/Dockerfile
    image: chat-rag-mcp:0.1.0
    restart: unless-stopped
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }
    environment:
      QDRANT_URL: http://chat-qdrant:6333
      QDRANT_COLLECTION: rag_documents
      EMBEDDING_MODEL: intfloat/multilingual-e5-small
      MODEL_CACHE_DIR: /app/models
    volumes:
      - models-cache:/app/models
    expose: ["8100"]
    read_only: true
    tmpfs: [/tmp:size=32m]
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    depends_on:
      chat-qdrant: { condition: service_healthy }
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health')"]
      interval: 30s
    networks: [ai-platform]

  chat-worker:
    build:
      context: .
      dockerfile: web/Dockerfile
      target: worker
    image: chat-web:0.1.0
    restart: unless-stopped
    command: celery -A config worker -l info -c 2
    deploy:
      resources:
        limits: { cpus: "2.0", memory: 2G }
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DATABASE_URL: sqlite:////data/sqlite/db.sqlite3
      REDIS_URL: redis://chat-redis:6379/0
      QDRANT_URL: http://chat-qdrant:6333
      QDRANT_COLLECTION: rag_documents
      EMBEDDING_MODEL: intfloat/multilingual-e5-small
      MODEL_CACHE_DIR: /app/models
      MEDIA_ROOT: /data/media
    volumes:
      - ./data/sqlite:/data/sqlite
      - ./data/media:/data/media
      - models-cache:/app/models
    depends_on:
      chat-redis: { condition: service_healthy }
      chat-qdrant: { condition: service_healthy }
    read_only: true
    tmpfs: [/tmp:size=64m]
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    networks: [ai-platform]

  chat-web:
    build:
      context: .
      dockerfile: web/Dockerfile
      target: web
    image: chat-web:0.1.0
    restart: unless-stopped
    command: daphne -b 0.0.0.0 -p 8000 config.asgi:application
    deploy:
      resources:
        limits: { cpus: "1.5", memory: 512M }
    environment:
      DJANGO_SETTINGS_MODULE: config.settings
      DATABASE_URL: sqlite:////data/sqlite/db.sqlite3
      REDIS_URL: redis://chat-redis:6379/0
      DATA_PLATFORM_MCP_URL: http://data-platform-mcp:8000/mcp
      RAG_MCP_URL: http://chat-rag-mcp:8100/mcp
      MEDIA_ROOT: /data/media
      ALLOWED_HOSTS: localhost,127.0.0.1
      CSRF_TRUSTED_ORIGINS: http://localhost:3004
      # ANTHROPIC_API_KEY: se lee del volumen ~/.claude si usas suscripción Pro
    volumes:
      - ./data/sqlite:/data/sqlite
      - ./data/media:/data/media
      - ${HOME}/.claude:/root/.claude:ro  # credencial de Claude Code
    ports:
      - "127.0.0.1:3004:8000"
    depends_on:
      chat-redis: { condition: service_healthy }
      chat-rag-mcp: { condition: service_healthy }
      chat-qdrant: { condition: service_healthy }
    read_only: true
    tmpfs: [/tmp:size=64m]
    security_opt: [no-new-privileges:true]
    cap_drop: [ALL]
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]
      interval: 30s
    networks: [ai-platform]

networks:
  ai-platform:
    name: ai-platform
    external: true

volumes:
  redis-data:
  models-cache:
  chat-qdrant-data:
```

**Notas del compose**:
- El montaje `${HOME}/.claude:/root/.claude:ro` permite al Agent SDK usar tu login de Claude Code sin API key. Si prefieres API key, comentar esa línea y añadir `ANTHROPIC_API_KEY` en `.env`.
- `data/sqlite` y `data/media` son bind mounts (no volúmenes) para poder respaldar fácil.
- `models-cache` es volumen nombrado compartido entre `chat-worker` y `chat-rag-mcp` para no duplicar el modelo en disco.

---

## 5. Fases de implementación

Cada fase entrega un estado funcional verificable. Ejecutar cada una en su propia sesión de Claude Code.

### Fase 0 — Preparación (30 min)

**Objetivo**: repo inicial, estructura, herramientas.

Tareas:
- [ ] Crear `~/docker/chat_rag/` con estructura de directorios de sección 3
- [ ] `.gitignore` (`.env`, `data/`, `__pycache__`, `*.pyc`, `models-cache/`)
- [ ] `.env.example` con todas las vars
- [ ] `README.md` inicial con quickstart
- [ ] `pyproject.toml` en `web/`, `rag-mcp/`, `shared/` (con `uv` como package manager)
- [ ] `Dockerfile` multi-stage en `web/` (targets: `base`, `web`, `worker`) y `rag-mcp/`
- [ ] Verificar que la red `ai-platform` existe (`docker network ls`)

**Criterio de aceptación**: `docker compose config` valida sin errores.

---

### Fase 1 — Skeleton Django + Auth (día 1)

**Objetivo**: Django corriendo, login funcional, tema oscuro/claro.

Tareas:
- [ ] `django-admin startproject config web/`
- [ ] Apps: `accounts`, `chat`, `ingesta`, `core`
- [ ] `settings.py`:
  - SQLite en `/data/sqlite/db.sqlite3`
  - `AUTH_USER_MODEL = 'accounts.User'`
  - Session cookies seguras
  - `STATIC_ROOT`, `MEDIA_ROOT`
  - Channels + Daphne
- [ ] Modelo `User` en `accounts/models.py` (heredar `AbstractUser`, añadir `theme_preference`)
- [ ] Vista login custom (sin registro)
- [ ] Middleware `LoginRequiredMiddleware` en `core/middlewares.py`
- [ ] `base.html`:
  - Tailwind compilado (CLI standalone ARM64)
  - Toggle tema con Alpine (`{ theme: localStorage.theme || 'system' }`)
  - Sidebar colapsable, botón perfil, botón logout
  - Slot principal `{% block content %}`
- [ ] `entrypoint.sh`: migrate + collectstatic + arranca Daphne
- [ ] Script `create_admin.sh`: wrapper interactivo de `createsuperuser`
- [ ] Vista `/healthz` que retorna 200
- [ ] Vista `/` que redirige a `/chat/` (o `/login/` si no auth)

**Criterio de aceptación**:
- `docker compose up chat-web chat-redis` levanta OK
- Crear admin: `docker compose exec chat-web python manage.py createsuperuser`
- Login en `http://localhost:3004/login/` funciona
- Toggle claro/oscuro persiste al refrescar

---

### Fase 2 — Qdrant propio + Servicio RAG MCP básico (día 2)

**Objetivo**: Qdrant nuevo corriendo, MCP del RAG corriendo, colección creada, tools registrados.

Tareas:
- [ ] Levantar `chat-qdrant` y verificar sano (`docker compose up chat-qdrant`)
- [ ] Confirmar que el volumen `chat-qdrant-data` persiste tras `docker compose down/up`
- [ ] `shared/`: paquete Python con `models.py` (Chunk, Document, DocumentMeta pydantic)
- [ ] `rag-mcp/server.py`: FastMCP con tres tools stub (`rag_search`, `rag_list_documents`, `rag_get_document_chunks`) que devuelven listas vacías
- [ ] `rag-mcp/embeddings.py`: singleton de `SentenceTransformer` con cache en `/app/models`
- [ ] `rag-mcp/qdrant_client.py`: cliente async apuntando a `chat-qdrant:6333`, helper para `search`
- [ ] Endpoint `/health` en el MCP que verifique conexión con Qdrant
- [ ] `scripts/init_qdrant.py`: script one-off que crea colección `rag_documents` (384 dim, cosine) si no existe
- [ ] Dockerfile con precarga del modelo en build (evitar descarga en primer arranque)

**Criterio de aceptación**:
- `docker compose up chat-qdrant chat-rag-mcp` ambos sanos
- `docker compose exec chat-rag-mcp python /app/scripts/init_qdrant.py` crea la colección
- `curl http://<container-ip>:8100/health` responde 200 e indica conexión con Qdrant OK
- Reiniciar `chat-qdrant` no pierde datos
- Desde Django (Fase 4) las tools serán invocables

---

### Fase 3 — Pipeline de ingesta (día 3-4)

**Objetivo**: subir archivo → parsear → chunkear → embed → guardar en Qdrant + metadata en SQLite.

Tareas:
- [ ] Modelos Django en `ingesta/models.py`:
  - `Document`: id, filename, mime_type, size, uploaded_at, status (`pending|processing|indexed|failed`), chunk_count, error_message
- [ ] Parsers en `shared/src/rag_shared/parsers/`:
  - `pdf.py` (pypdf → fallback pdfplumber si texto vacío)
  - `docx.py`, `pptx.py`, `xlsx.py`, `csv.py`, `md.py`, `txt.py`, `image.py` (pytesseract)
  - Interfaz común: `parse(path: Path) -> Iterable[TextBlock]`
  - Factory `get_parser(mime_type)` en `parsers/__init__.py`
- [ ] `shared/chunker.py`: `RecursiveCharacterTextSplitter` (800/120), respeta párrafos
- [ ] Tesseract instalado en imagen `chat-worker` (paquete `tesseract-ocr` + `tesseract-ocr-spa`)
- [ ] Task Celery `ingesta.tasks.process_document(document_id)`:
  1. Cargar Document, marcar `processing`
  2. Detectar mime type real (no confiar en extensión)
  3. Parsear → chunks
  4. Embed (batch de 32 chunks)
  5. Upsert en Qdrant con payload `{document_id, chunk_index, text, page?, section?}`
  6. Marcar `indexed`, actualizar `chunk_count`
  7. Try/except: marcar `failed` con mensaje
- [ ] Vista `ingesta/views.py::upload`:
  - Recibe archivo(s), guarda en `MEDIA_ROOT/<uuid>/<filename>`
  - Crea Document en DB
  - Encola task
  - Retorna JSON con `document_id`
- [ ] Vista `ingesta/views.py::list_documents`: HTML con lista + estado en vivo (HTMX polling cada 2s a `/ingesta/status/<id>/`)
- [ ] UI drag-drop en `templates/ingesta/documents.html`:
  - Zona drop full-height con Alpine
  - Preview de nombre/tamaño/tipo
  - Barra de progreso por archivo
  - Grid de documentos existentes con badge de estado
  - Botón borrar (soft-delete + delete de Qdrant por filtro)
- [ ] Implementar `rag_search`, `rag_list_documents`, `rag_get_document_chunks` en el MCP (ya no stubs)

**Criterio de aceptación**:
- Subir un PDF: aparece en lista con estado `processing` → `indexed`
- `docker compose exec chat-rag-mcp python -c "from qdrant_client import ...; print(count)"` muestra chunks
- Subir DOCX, XLSX, imagen (con texto), MD: todos indexan
- Borrar un documento elimina chunks de Qdrant

---

### Fase 4 — Chat con Agent SDK (día 5)

**Objetivo**: chat funcional que consume los dos MCPs, con streaming.

Tareas:
- [ ] Modelos `chat/models.py`:
  - `Conversation`: id, user, title (auto-generado del primer mensaje), created_at, updated_at
  - `Message`: conversation, role (`user|assistant|tool`), content, tool_name?, tool_args?, tool_result?, created_at
- [ ] `chat/agent.py`: wrapper del Agent SDK
  - `ClaudeAgentOptions` con `mcp_servers` apuntando a `data-platform-mcp` y `rag-mcp`
  - Función `stream_reply(conversation_id, user_message) -> AsyncIterator[Event]`
  - Cada event yielded es dict serializable: `{type: 'token'|'tool_use'|'tool_result'|'done', ...}`
- [ ] Vista async `chat/views.py::stream_message`:
  - Recibe POST con `conversation_id` y `message`
  - Guarda mensaje del usuario
  - Retorna `StreamingHttpResponse` con SSE
  - Cada chunk del agent → línea `data: {json}\n\n`
  - Al final, guarda mensaje assistant completo
- [ ] Vista `chat/views.py::conversation_detail`: HTML con historial + input
- [ ] Vista `chat/views.py::new_conversation`: crea y redirige
- [ ] Sidebar: lista de conversaciones agrupadas por fecha (hoy, ayer, últimos 7 días, más antiguo)
- [ ] Template chat:
  - Burbujas usuario (derecha, primary) / assistant (izquierda, muted)
  - Chips visuales cuando invoca tool: `🔍 rag_search("...")` colapsable con resultado
  - Markdown render en cliente con `marked.js` (post-stream)
  - Syntax highlighting con `highlight.js`
  - Botón copiar en cada bloque de código
  - Auto-scroll suave
  - Input con Alpine: Shift+Enter nueva línea, Enter enviar, Cmd+K nueva conversación
- [ ] JavaScript de streaming: `EventSource` conecta a `/chat/stream/`, va apendeando tokens

**Criterio de aceptación**:
- Enviar mensaje → respuesta stream token a token
- Preguntar algo sobre datos → Claude invoca `mcp__data-platform__list_connections` visible en UI
- Preguntar sobre docs subidos → Claude invoca `rag_search` y usa el contexto
- Recargar página conserva historial
- Cambiar de conversación desde sidebar funciona

---

### Fase 5 — Pulido UI (día 6)

**Objetivo**: producto que se sienta bien de usar.

Tareas:
- [ ] Estética base tipo shadcn: variables CSS (`--background`, `--foreground`, `--muted`, `--border`, `--primary`, `--accent`), radios `--radius-md: 0.5rem`, sombras suaves
- [ ] Tipografía: Inter (self-hosted en `static/fonts/`, no Google Fonts)
- [ ] Transiciones de vista con View Transitions API donde aplique
- [ ] Skeleton loaders en carga de conversaciones y lista de docs
- [ ] Toast notifications (Alpine + Tailwind) para éxito/error de acciones
- [ ] Keyboard shortcuts:
  - `Cmd/Ctrl + K`: nueva conversación
  - `Cmd/Ctrl + Enter`: enviar
  - `Cmd/Ctrl + /`: focus en input
  - `Cmd/Ctrl + B`: toggle sidebar
- [ ] Estado vacío bonito en `/chat/` (sin conversaciones): tarjeta con prompts sugeridos que empiezan una conversación al click
- [ ] Estado vacío en `/documentos/`: CTA con drag-drop grande
- [ ] Configuración de usuario (`/settings/`): cambiar contraseña, tema por defecto, borrar todos los datos
- [ ] Export de conversación a Markdown (`.md` con timestamps)
- [ ] Página 404 y 500 personalizadas

**Criterio de aceptación**: dos horas usándolo sin que algo se sienta tosco.

---

### Fase 6 — Google Drive (opcional, día 7)

**Objetivo**: importar Google Docs/Sheets/Slides sin descargar manualmente.

Tareas:
- [ ] Proyecto en Google Cloud Console + credenciales OAuth (Desktop app)
- [ ] Habilitar Drive API + Picker API
- [ ] `django-allauth` o flujo OAuth manual para vincular cuenta Google (solo tu cuenta)
- [ ] Botón "Importar de Drive" en `/documentos/`
- [ ] Google Picker JS embebido, callback envía `file_id` + `mime_type` al backend
- [ ] Backend descarga vía Drive API con `export`:
  - Google Doc → `.docx`
  - Google Sheet → `.xlsx`
  - Google Slide → `.pptx`
- [ ] Guarda en `MEDIA_ROOT` y encola task normal de ingesta

**Criterio de aceptación**: seleccionar un Google Doc desde el picker lo indexa en el RAG.

---

### Fase 7 — Backup y observabilidad (medio día)

- [ ] Script `scripts/backup.sh`:
  - Snapshot de la colección Qdrant vía API `POST /collections/rag_documents/snapshots` → queda en `data/qdrant-snapshots/`
  - Tar de `data/sqlite/` (con `sqlite3 .backup` para consistencia)
  - Tar de `data/media/`
  - Empaqueta todo en `backups/YYYY-MM-DD-HHMM.tar.gz`
- [ ] Script `scripts/restore.sh`: contraparte que restaura desde un tarball
- [ ] Cron (o systemd timer) para backup diario, retención 7 días
- [ ] Rotación de logs con `logrotate` o similar
- [ ] Logs estructurados JSON (structlog) en Django y RAG-MCP
- [ ] Endpoint `/metrics` básico (contador de conversaciones, docs indexados, errores últimas 24h) para vista interna

---

## 6. Variables de entorno (`.env.example`)

```dotenv
# Django
DJANGO_SECRET_KEY=cambiame-usa-python-secrets
DJANGO_DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:3004

# Base de datos y storage
DATABASE_URL=sqlite:////data/sqlite/db.sqlite3
MEDIA_ROOT=/data/media

# Redis
REDIS_URL=redis://chat-redis:6379/0

# MCPs
DATA_PLATFORM_MCP_URL=http://data-platform-mcp:8000/mcp
RAG_MCP_URL=http://chat-rag-mcp:8100/mcp

# Qdrant (instancia propia del proyecto)
QDRANT_URL=http://chat-qdrant:6333
QDRANT_COLLECTION=rag_documents

# Embeddings
EMBEDDING_MODEL=intfloat/multilingual-e5-small
MODEL_CACHE_DIR=/app/models

# Claude — solo UNA de estas dos opciones:
# Opción A: usar suscripción (monta ~/.claude en el contenedor, no set API key)
# Opción B: API key (comenta el mount en compose y define aquí)
# ANTHROPIC_API_KEY=sk-ant-...

# UI expose
CHAT_WEB_BIND_ADDRESS=127.0.0.1
CHAT_WEB_PORT=3004
```

---

## 7. Testing mínimo por fase

| Fase | Tipo | Qué probar |
|---|---|---|
| 1 | Manual | Login, logout, toggle tema, admin creado |
| 2 | Integración | Init Qdrant, healthcheck MCP, tools stub responden |
| 3 | Unit + integración | Cada parser con archivo fixture, task Celery end-to-end, delete cascade |
| 4 | Manual + integración | Stream funciona, tools se invocan, historial persiste |
| 5 | Manual | UX check, shortcuts, responsive |

Estructura de tests: `web/apps/*/tests/` y `rag-mcp/tests/` con pytest + pytest-django + pytest-asyncio.

---

## 8. Riesgos identificados y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Sentence-transformers lento en ARM64 vCPU | Ingesta lenta | Batch grande, task async, indicador de progreso claro. Alternativa: onnxruntime |
| Tesseract mala calidad en imágenes borrosas | Chunks basura | Preprocesado con Pillow (contraste), permitir marcar doc como "solo OCR fallido" |
| Suscripción Pro se queda sin cuota mid-conversación | Chat cae | Detectar 429, mensaje claro al usuario, fallback a mostrar respuesta parcial |
| PDF con solo imágenes se salta pypdf | Doc queda vacío | Detectar texto vacío tras pypdf → correr Tesseract sobre las páginas rasterizadas |
| Qdrant colección corrupta | RAG cae | Snapshots diarios vía API + script de reindex desde `Document` en SQLite |
| Puerto Qdrant del MCP y del chat chocan si ambos exponen al host | Uno de los dos no arranca | Ninguno expone al host (`ports` vacío), solo `expose`; el hostname distingue |
| Cambio de política de Anthropic sobre uso Agent SDK con suscripción | App deja de funcionar | Fácil switch a API key: solo cambiar variable de entorno |
| ARM64: algún wheel no existe | Build falla | Fijar versiones probadas en ARM64 en `pyproject.toml`, compilar desde source si necesario |

---

## 9. Checklist previo al primer `docker compose up`

- [ ] Red `ai-platform` existe (`docker network create ai-platform` si no)
- [ ] Compose del MCP corriendo (`data-platform-mcp` sano). El Qdrant del MCP puede apagarse si no se usa: `docker compose stop qdrant` en el directorio del MCP
- [ ] `.env` creado a partir de `.env.example` con valores reales
- [ ] `SECRET_KEY` generado con `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- [ ] Directorios `data/sqlite`, `data/media`, `data/models`, `data/qdrant-snapshots` creados con permisos correctos
- [ ] Si usas suscripción Pro: haber corrido `claude` una vez en el host para tener `~/.claude/` populado

---

## 10. Comandos de operación

```bash
# Levantar
cd ~/docker/chat_rag
docker compose up -d

# Ver logs
docker compose logs -f chat-web
docker compose logs -f chat-worker

# Crear admin (solo primera vez)
docker compose exec chat-web python manage.py createsuperuser

# Inicializar colección Qdrant (solo primera vez)
docker compose exec chat-rag-mcp python /app/scripts/init_qdrant.py

# Aplicar migraciones tras cambios
docker compose exec chat-web python manage.py migrate

# Shell Django
docker compose exec chat-web python manage.py shell

# Reindexar todos los documentos (mantenimiento)
docker compose exec chat-web python manage.py reindex_all

# Qdrant: crear snapshot manual de la colección
docker compose exec chat-qdrant curl -X POST http://localhost:6333/collections/rag_documents/snapshots

# Qdrant: listar colecciones
docker compose exec chat-qdrant curl http://localhost:6333/collections

# Backup completo (SQLite + media + snapshot Qdrant)
./scripts/backup.sh

# Bajar
docker compose down

# Bajar borrando volúmenes (¡destructivo!)
docker compose down -v
```

---

## 11. Fuera de alcance (v1)

Cosas que NO se implementarán en la primera versión pero podrían venir después:

- Múltiples usuarios / permisos por documento
- Colecciones/carpetas para agrupar documentos
- Reranker
- Búsqueda híbrida (BM25 + vectorial)
- Compartir conversación por link
- Voz (STT/TTS)
- Function calling directo (sin MCP) para tools ad-hoc
- Fine-tuning o memoria de largo plazo del asistente
- Métricas de calidad de retrieval (recall@k, MRR)
- Multi-modelo (elegir Claude Sonnet vs Opus por conversación)

---

## 12. Definición de "listo"

La v1 está lista cuando:

1. Puedo abrir `http://localhost:3004`, hacer login, y ver el chat.
2. Puedo subir un PDF, esperar unos segundos, y verlo indexado.
3. Puedo preguntar en el chat "resúmeme el documento X" y Claude usa el RAG.
4. Puedo preguntar "cuántas conexiones tiene el MCP" y Claude usa `data-platform-mcp`.
5. La UI se ve bien en claro y oscuro.
6. Reinicio del host: `docker compose up -d` levanta todo sin pasos manuales.
7. Nada más que el puerto 3004 en localhost está expuesto al host.
