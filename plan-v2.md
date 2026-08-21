# chat_rag — Plan v2

Continuación de `plan.md` (v1, Fases 0–7, completa salvo la Fase 6 opcional
de Google Drive). Estas son fases nuevas, todavía sin implementar — cada
una en su propia rama `Feature/Fase-NN` cuando se decida arrancarla, mismo
flujo que v1 (ver `plan.md` para las convenciones de branching/testing).

Numeración continua desde la Fase 7 de v1.

---

### Fase 8 — Colecciones/carpetas de documentos

**Objetivo**: agrupar documentos en colecciones para organizar la librería
y poder acotar la búsqueda RAG a un subconjunto ("buscá solo en la
colección Contratos 2026").

Tareas:
- [ ] Modelo `ingesta/models.py::Collection`: `id` (UUID), `name`,
      `created_at`, `updated_at`. Sin owner (uso 100% personal, igual que
      `Document`).
- [ ] `Document.collection` — FK opcional (`null=True, blank=True,
      on_delete=models.SET_NULL`). Un documento pertenece a una colección
      como mucho, o ninguna — modelo de carpeta simple, no etiquetas
      múltiples.
- [ ] Migración.
- [ ] Vistas CRUD de colecciones (crear, renombrar, borrar). Borrar una
      colección NO borra sus documentos, solo los deja sin colección.
- [ ] `/documentos/`: filtro/agrupación por colección (tabs o sidebar:
      "Todos" + cada colección).
- [ ] Al subir un documento: selector de colección (default "sin
      colección"). Poder mover un documento a otra colección después.
- [ ] Payload de cada chunk en Qdrant (`vector_store._build_points`) gana
      `collection_id`.
- [ ] `vector_store.search()` acepta un filtro opcional por colección
      (`models.Filter` con `FieldCondition` sobre `collection_id`).
- [ ] `rag_search` (rag-mcp/server.py) gana un parámetro opcional
      `collection: str | None`.
- [ ] Tool nueva `rag_list_collections` — para que Claude sepa qué
      colecciones existen y decida cuándo acotar la búsqueda.
- [ ] `chat/agent.py::SYSTEM_PROMPT`: mencionar que existen colecciones y
      cuándo usarlas.

**Criterio de aceptación**: creo una colección, subo documentos ahí, le
pido a Claude que busque "solo en esa colección" y lo hace (y si no lo
pido, sigue buscando en todo por default).

---

### Fase 9 — Compartir conversación por link

**Objetivo**: generar un link de solo lectura de una conversación para
compartirla sin dar acceso a la cuenta.

Tareas:
- [ ] Modelo `chat/models.py::SharedLink`: `conversation` FK,
      `token` (`secrets.token_urlsafe(32)`, no adivinable), `created_at`,
      `revoked_at` (nullable). Separado de `Conversation` (no un campo
      único ahí) para poder revocar y tener más de un link histórico sin
      invalidar automáticamente el anterior.
- [ ] Migración.
- [ ] `apps/core/middlewares.py::EXEMPT_PATH_PREFIXES`: agregar el prefijo
      de la vista pública (ej. `/compartido/`).
- [ ] Vista pública `chat/views.py::shared_conversation` en
      `/compartido/<token>/` — sin `@login_required`, 404 si el token no
      existe o `revoked_at` no es nulo. Solo lectura: reusa
      `chat/_message.html` pero en un template standalone (no
      `base.html`) sin sidebar, composer, botón de exportar ni nada que
      exponga el resto de la cuenta — mismo criterio que
      `templates/500.html` (Fase 5: standalone a propósito).
- [ ] Botón "Compartir" en `conversation.html` (al lado de "Exportar"):
      crea el `SharedLink` si no existe uno activo, copia la URL al
      portapapeles, toast de confirmación.
- [ ] Botón "Revocar" (visible si ya hay un link activo).
- [ ] Home de conversación show icono si tiene un link activo actualmente.

**Criterio de aceptación**: comparto un link, lo abro en una ventana de
incógnito (sin sesión) y veo la conversación de solo lectura. Lo revoco y
el link pasa a dar 404.

---

### Fase 10 — Búsqueda híbrida (BM25 + vectorial)

**Objetivo**: mejorar precisión de retrieval combinando búsqueda léxica
(BM25) con la vectorial actual — sobre todo para términos exactos/nombres
propios que un embedding semántico puede diluir.

Tareas:
- [ ] Nueva dependencia `fastembed` (`shared/pyproject.toml`) — se integra
      nativamente con `qdrant-client` para sparse vectors, no hace falta
      mantener un índice BM25 aparte.
- [ ] `rag_shared/embeddings.py`: función nueva `embed_passages_sparse` /
      `embed_query_sparse` (modelo BM25 de fastembed), mismo patrón lazy
      de import que ya usa `get_model()`.
- [ ] `vector_store.py`:
  - `_VECTORS_CONFIG` gana `sparse_vectors_config` (Qdrant soporta sparse
    vectors nativos desde v1.7+).
  - `_build_points`: cada punto gana el sparse vector calculado del texto
    del chunk, junto al denso que ya tiene.
  - `search()`: pasa de `query_points(query=vector)` simple a
    `query_points` con `prefetch` (uno denso, uno sparse) y
    `fusion=models.Fusion.RRF` (Reciprocal Rank Fusion) para combinar
    ambos rankings en uno.
- [ ] **Migración de datos**: reindexar todo lo ya subido (la colección
      existente no tiene sparse vectors) — task de management command o
      script que recorra `Document.objects.active()` y vuelva a correr
      `process_document` para cada uno.
- [ ] `ingesta/tasks.py::_process`: al embeber en batches, calcular
      también el sparse vector de cada batch.

**Criterio de aceptación**: buscar un término exacto (ej. un código de
producto, un nombre propio) que antes no aparecía entre los primeros
resultados por similitud puramente semántica ahora sí aparece arriba.

---

### Fase 11 — Multi-modelo (elegir Sonnet vs Opus por conversación)

**Objetivo**: poder elegir qué modelo de Claude usa cada conversación,
con el trade-off de costo/velocidad/capacidad explícito.

Tareas:
- [ ] `chat/models.py::Conversation.model` — `CharField` con `choices`
      (`claude-sonnet-5` default, `claude-opus-5`; revisar el listado de
      IDs vigente antes de hardcodear valores, cambian con el tiempo).
- [ ] Migración (con default = Sonnet para conversaciones existentes).
- [ ] `chat/agent.py::_build_options`: parámetro `model: str`, pasado a
      `ClaudeAgentOptions(model=...)`.
- [ ] `chat/views.py::new_conversation`: recibe el modelo elegido (form
      field, default Sonnet si no se manda nada).
- [ ] UI: selector en el flujo de "Nueva conversación" (no dentro de una
      conversación ya empezada — cambiar de modelo a mitad con contexto
      ya resumido es confuso). Nota visible de costo/velocidad
      (Opus: más capaz, más lento y caro · Sonnet: el equilibrio default).
- [ ] Mostrar el modelo usado en el header de `conversation.html` (texto
      chico, no interactivo, ya que no se puede cambiar después de creada).

**Criterio de aceptación**: creo una conversación eligiendo Opus, el
header lo muestra, y las respuestas efectivamente vienen de ese modelo
(verificable indirectamente por latencia/calidad, o revisando el log
estructurado del turno si se decide loguear el modelo usado).

---

### Fase 12 — Retención de backups por tamaño, no solo por días

**Objetivo**: la Fase 7 (v1) dejó `scripts/backup.sh` con retención por
antigüedad (`BACKUP_RETENTION_DAYS`, default 7 días) — con backup diario a
las 3 AM (cron ya instalado), si el tamaño del backup crece (más
documentos, colección de Qdrant más grande), 7 días de historial podría
llenar el disco antes de que la retención por días llegue a limpiar nada.
Cambiar a una política consciente del tamaño: conservar los últimos 2
backups, pero si entre los dos superan un umbral (default 5 GB), quedarse
solo con el más reciente.

Tareas:
- [ ] `scripts/backup.sh`: reemplazar el bloque de retención actual
      (`find "$BACKUPS_DIR" -mtime "+$RETENTION_DAYS" -delete`) por:
  1. Listar los backups existentes en `$BACKUPS_DIR` ordenados por fecha
     (más reciente primero).
  2. Si hay más de 2, borrar todos los que sobren de los 2 más recientes.
  3. Sobre los que queden (como mucho 2), sumar su tamaño total; si supera
     `BACKUP_MAX_SIZE_MB` (nueva env var, default 5120 = 5 GB), borrar
     todos menos el más reciente.
- [ ] `.env.example`: agregar `BACKUP_MAX_SIZE_MB` (documentado, comentado
      con default), dejar `BACKUP_RETENTION_DAYS` documentado como
      "cuántos backups conservar como máximo" en vez de días — ver si
      conviene renombrarla a `BACKUP_MAX_COUNT` para que el nombre refleje
      la semántica nueva (son 2 conceptos combinados: cantidad Y tamaño).
- [ ] Loguear en `backup.sh` cuál de los dos criterios disparó el borrado
      (cantidad vs tamaño), para que quede claro en `backups/cron.log`.
- [ ] Probar contra el stack real: generar backups de prueba de tamaño
      variable y confirmar que la política se aplica bien en los tres
      casos (0, 1, 2+ backups previos; por debajo y por encima del umbral
      de tamaño).

**Criterio de aceptación**: con backup diario corriendo, `backups/` nunca
tiene más de 2 archivos, y si esos 2 pesan más de 5 GB combinados, se queda
con uno solo.

---
