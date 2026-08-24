# chat_rag — Plan v3

Continuación de `plan-v2.md` (Fases 8–13, completa). Estas son fases
nuevas, todavía sin implementar — cada una en su propia rama
`Feature/Fase-NN` cuando se decida arrancarla, mismo flujo que v1/v2 (ver
`plan.md` para las convenciones de branching/testing).

Numeración continua desde la Fase 13. Prioridad pensada de mayor a menor
valor por esfuerzo: primero mejoras chicas sobre lo que ya se usa a
diario (costo visible, reintentar, adjuntar), después una mejora de
calidad de retrieval que se apoya directo en la Fase 12 (reranker), y al
final las dos más grandes/con dependencias externas (búsqueda en
historial, Google Drive — esta última bloqueada por credenciales OAuth
que tiene que crear el usuario, como ya estaba anotado en `plan.md`
Fase 6).

Las Fases 20-22 son la pata de **reportería** (generar y descargar
archivos — tablas, documentos, diagramas — a partir de lo que el chat ya
sabe hacer hoy: leer documentos vía `rag_search` y consultar bases vía
las tools de `data-platform`). Es sensiblemente más grande que el resto
del plan junto, así que están separadas en 3 sub-fases por complejidad
creciente — nada obliga a hacerlas en orden ni a completarlas todas antes
de seguir con otra cosa; si en algún momento se sienten como su propio
bloque, migrarlas a un `plan-v4.md` es tan simple como cortar y pegar,
no hay dependencia dura hacia atrás con las Fases 14-19.

**Decisión de arquitectura, común a las 3**: el agente hoy corre con
`permission_mode="bypassPermissions"` y sin restringir `tools`
(`chat/agent.py`), pero el propio comentario del código dice que la
intención es que las tools disponibles queden "acotadas a los dos MCPs
propios" — nada de darle al modelo un Bash/Write genérico para que
escriba archivos a mano dentro de un contenedor `read_only: true`. Para
reportería, la generación tiene que ser vía **tools MCP nuevas y
determinísticas**: Claude manda datos ya estructurados (filas de una
tabla, texto de un documento, nodos/aristas de un diagrama) y el server
arma el archivo con una librería real, no le confiamos al modelo que
genere bytes binarios de un .xlsx. Van como tools nuevas en
`chat-rag-mcp` (reusa el mismo contenedor — `openpyxl`/`python-docx`/
`python-pptx` ya son dependencias de `rag_shared`, hoy solo para
*parsear* esos formatos al ingerir documentos, las mismas libs sirven
para *escribir*), en vez de un servicio nuevo — si con el tiempo esto
crece mucho o pesa demasiado el build de esa imagen, separarlo en un
`chat-reports-mcp` propio (mismo patrón que `chat-rag-mcp`) es la
migración natural, no hace falta adelantarla ahora.

**Dónde quedan los archivos generados**: `chat-rag-mcp` monta
`data/sqlite` de **solo lectura** a propósito (ver el comentario en
`compose.yaml` — chat-web/chat-worker son los únicos que escriben ahí),
así que un modelo Django nuevo tipo `GeneratedFile` para trackearlos NO
es la opción más simple: implicaría que chat-rag-mcp escriba en la
sqlite compartida, rompiendo esa regla. Más simple para un v1 (uso
100% personal, un solo usuario): el archivo se guarda directo en un
volumen (`data/media/reports/<uuid>.<ext>`, mismo volumen `data/media`
que ya usan los documentos subidos, con un mount RW nuevo en
`chat-rag-mcp` que hoy no lo tiene) y una vista de Django liviana lo
sirve por nombre — sin tabla de tracking, sin dueño que validar (ya está
todo detrás de `@login_required` vía `apps/core/middlewares.py`, igual
que el resto del sitio). Se pierde poder "listar reportes generados" o
limpiarlos automáticamente — aceptable para un v1, se puede agregar un
modelo de tracking después si hace falta. El link de descarga lo arma la
tool con `PUBLIC_BASE_URL` (ya existe desde la Fase 11 para compartir
conversaciones — hay que agregarlo también al `environment:` de
`chat-rag-mcp` en `compose.yaml`, hoy solo lo lee `chat-web`), y Claude
lo devuelve como un link markdown normal en su respuesta — el chat ya
renderiza markdown, así que un `[reporte.xlsx](url)` sale clickeable sin
tocar el JS del composer ni inventar un sistema de "adjuntos" nuevo.

**Nota sobre `data-platform-mcp` y su propia tool `generate_report`**:
investigando esto se encontró que el MCP externo (`data-platform-mcp`,
código en `~/docker/data-analits-MCP` en este mismo host — no es parte
de este repo) ya expone una tool `generate_report` bastante madura
(pregunta en lenguaje natural sobre **una sola** conexión → genera y
ejecuta el SQL sola → exporta a xlsx/pdf/csv/json/html, con budget de
tamaño y truncado). Decisión explícita: **no se usa esa tool para nada
de esto** — la reportería completa (generación de los archivos) vive
acá, en `chat_rag`/`chat-rag-mcp`; `data-platform-mcp` queda acotado a
solo **consultar** datos (`execute_read_query`,
`generate_and_execute_query`, etc.), igual que hoy. Motivo: control
total de formatos (docx/pptx/drawio no existen del lado de
`data-platform-mcp`, y no tiene sentido tener dos sistemas de reportería
en dos proyectos distintos) y porque el caso de cruzar datos de más de
una conexión (el ejemplo original del usuario) no encaja en el diseño
de esa tool de todos modos (una sola conexión, una sola pregunta, un
solo SQL). Ojo al escribir el `SYSTEM_PROMPT` (`chat/agent.py`) en la
Fase 20: hay que ser explícito en que para generar archivos/reportes
descargables se usan las tools `report_*` de `rag`, no `generate_report`
de `data-platform` — si no, nada impide que Claude la use igual (ambas
aparecen como tools disponibles) y el resultado sea el problema
original: un payload `content_base64` volcado como JSON crudo en el
chat (`templates/chat/_message.html` hoy no tiene ningún manejo especial
para eso).

**Nota sobre links compartidos (Fase 11)**: un link de reporte que
aparece en el texto de una respuesta SÍ se ve en una conversación
compartida por `/compartido/<token>/` (a diferencia de los mensajes de
tool, que esa vista ya excluye) — pero al no estar logueado, clickearlo
desde ahí redirige a login. Es un caso raro (compartís explícitamente Y
el reporte le interesa a quien lo abre sin cuenta) — se deja así para
v1, no vale la pena la complejidad de un segundo modo de acceso público
para esto todavía.

Quedan del backlog original de `plan.md` (sección 11, "Fuera de alcance
v1") sin tocar todavía: múltiples usuarios (descartado a propósito, uso
100% personal) y voz/STT-TTS (no incluida acá, candidata para una v4 si
hace falta).

---

### Fase 14 — Costo y uso por conversación

**Objetivo**: ver cuánto está costando cada conversación, sobre todo
ahora que existe la opción de usar Opus (Fase 13) — hoy ese dato lo
devuelve el Agent SDK en cada turno (`ResultMessage.total_cost_usd`) pero
se descarta.

Tareas:
- [x] `chat/models.py::Conversation.total_cost_usd` — `DecimalField`
      (o `FloatField`, ver qué tan preciso hace falta que sea; SQLite no
      tiene problema con `Decimal` vía Django) default 0, se acumula
      turno a turno.
- [x] Migración.
- [x] `chat/agent.py`: el evento `"done"` que ya arma la rama
      `ResultMessage` (donde vive `resolved_model`, agregado en la
      Fase 13) suma `"cost_usd": message.total_cost_usd`.
- [x] `chat/views.py::stream_message`: en el bloque `elif event_type ==
      "done"` (mismo lugar donde ya se loguea `chat_turn_done` y se
      actualiza `agent_session_id`), sumar `event["cost_usd"]` a
      `conversation.total_cost_usd` antes del `asave` (agregar el campo a
      `update_fields`). `total_cost_usd` puede venir `None` en turnos que
      fallaron antes de completar — tratarlo como 0.
- [x] UI: badge en el header de `conversation.html`, al lado del badge de
      modelo que ya existe (Fase 13) — `${{ conversation.total_cost_usd
      }}` con 3-4 decimales, texto chico, sin interacción.
- [ ] Opcional/nice-to-have: mostrarlo también en el sidebar (junto al
      título de cada conversación) para comparar de un vistazo cuáles
      salieron más caras — evaluar si no satura visualmente un espacio ya
      angosto (256px de ancho). NO implementado en esta fase — se dejó
      afuera para no saturar el espacio angosto del sidebar (256px), que
      ya tiene título + ícono de borrar por item.

**Criterio de aceptación**: mando varios mensajes en una conversación con
Opus, el badge de costo sube después de cada turno, y el total coincide
(a los centavos) con la suma manual de `total_cost_usd` que se ve en los
logs estructurados (`chat_turn_done`, o uno nuevo si hace falta separar
el campo de costo de ese log).

---

### Fase 15 — Reintentar turno fallido

**Objetivo**: hoy si un turno falla (`Message.is_error=True`, ej. rate
limit, timeout, error de alguna tool) la única forma de seguir es
escribir el mensaje de nuevo a mano. Agregar un botón para reintentarlo
sin retipear.

**Restricción de arquitectura a tener en cuenta**: `chat/agent.py` usa
`query()` con `resume` (no `ClaudeSDKClient`) — cada turno nuevo hace que
el SDK reconstruya el contexto leyendo el transcript que el CLI ya
guardó en `CLAUDE_CONFIG_DIR` (ver el docstring del módulo). Eso significa
que **no se puede "editar" ni "rebobinar" un turno ya ocurrido** — el
transcript previo es inmutable desde acá. Lo único viable es volver a
mandar el mismo texto del último mensaje de usuario como un turno *nuevo*
(se agrega después del que falló, no lo reemplaza). Por eso el alcance de
esta fase es específicamente "reintentar el último turno si falló", no
un "editar cualquier mensaje pasado y regenerar desde ahí" — eso último
implicaría manejar ramas de conversación, fuera de alcance acá.

Tareas:
- [x] `chat/views.py`: nuevo endpoint `POST
      /chat/<uuid:conversation_id>/reintentar/` (`retry_message`) que, en
      vez de leer `message` del body, toma el texto del último `Message`
      con `role=USER` de la conversación — solo si el último mensaje que no
      es de una tool es ese mismo mensaje de usuario sin respuesta (el
      turno se cortó antes de producir texto) o un `Message` de
      `role=ASSISTANT` con `is_error=True` (si no, 400: no hay nada que
      reintentar). Se amplió el criterio del enunciado original ("el
      `Message` de `role=ASSISTANT` más reciente tiene `is_error=True`")
      porque si el turno falla ANTES de que el modelo emita texto, no llega
      a crearse ningún `Message` de rol assistant (ver el `if
      assistant_text:` de `_stream_agent_turn`) — con el criterio literal
      ese caso hubiera quedado sin forma de reintentar.
- [x] No duplicar el `Message` de rol `user` en la base (ya está guardado
      del intento anterior) — se extrajo el generador de eventos SSE de
      `stream_message` a `_stream_agent_turn(conversation, user_text)`,
      compartido por ambos endpoints; `retry_message` no llama a
      `Message.objects.acreate(..., role=USER, ...)`.
- [x] UI: botón "↻ Reintentar" — no se puso dentro de `_message.html`
      (bajo el mensaje del asistente en el DOM) para no tener que reordenar
      el hilo cada vez que `send()`/`retry()` agregan un bubble nuevo; en
      cambio queda fijo debajo del hilo, junto al box de `errorMessage`,
      visible con el mismo criterio (`can_retry`, calculado server-side en
      `conversation_detail` y recalculado en JS al terminar cada turno).
- [x] `static/js/chat.js`: `send()` y `retry()` comparten un helper
      `runTurn(url, body)` con todo el parseo de SSE — no se duplicó esa
      lógica.

**Criterio de aceptación**: verificado sin gastar en la API para el caso
base (mensaje de usuario insertado a mano en la DB, sin respuesta —
simula un turno cortado antes de cualquier texto) y con turnos reales de
Claude para confirmar el flujo end-to-end completo, incluyendo el segundo
caso (`Message` de asistente con `is_error=True`): en ambos, el botón
aparece (`can_retry`/`chatPage(..., true)` en el HTML), al reintentar NO
se duplica el `Message` de rol user, se agrega un `Message` de asistente
nuevo con la respuesta, y `can_retry` vuelve a `false` tras un reintento
exitoso. También confirmado el 400 ("No hay ningún turno fallido para
reintentar") en una conversación sin nada que reintentar.

---

### Fase 16 — Adjuntar documentos desde el chat

**Objetivo**: hoy subir un documento requiere salir de la conversación e
ir a `/documentos/`. Agregar un botón de adjuntar directo en el
composer, sin cambiar de pantalla.

Tareas:
- [x] `static/js/chat.js`: botón 📎 en el composer + `<input
      type="file" hidden>`, dispara la misma request que ya usa
      `apps/ingesta/views.py::upload` (`POST /documentos/subir/`,
      `multipart/form-data`, campo `file`) — **no hizo falta backend
      nuevo para subir**, ese endpoint ya devuelve `{document_id,
      card_html}` y no está atado a `/documentos/` de ninguna forma
      especial. Confirmado: `upload()` solo tiene `@login_required` +
      `@require_POST`, sin restricción de referer que choque al llamarlo
      desde `conversation.html`.
- [x] Mientras se indexa: chip inline en el hilo (no en el composer, para
      que quede en el historial de mensajes) — con polling **reusando
      htmx** (mismo mecanismo que `documents.html`: `hx-get` a
      `ingesta:status` cada 2s, `htmx.process()` tras insertar el chip a
      mano vía JS, mismo patrón que ya usaba `ingesta.js`) hasta que el
      `status` sea `indexed` o `failed`. Único cambio de backend: `upload`
      y `status` (`apps/ingesta/views.py`) ahora aceptan `chip=1` (GET o
      POST) para devolver un fragmento nuevo y más liviano
      (`_chat_attachment_chip.html`) en vez de la card completa de
      `/documentos/` — default sin el parámetro sigue devolviendo la card
      de siempre, `documents.html` no cambió.
- [x] Si falla la ingesta (`status=failed`), se muestra el `error_message`
      del `Document` en el mismo chip (borde rojo + texto del error).
- [x] Sin selector de colección desde acá — el chip liviano no lo incluye
      (a diferencia de la card completa); si el usuario quiere
      organizarlo, lo mueve después desde `/documentos/` (Fase 10).
- [x] `SYSTEM_PROMPT` (`chat/agent.py`) no necesitó cambios — confirmado
      con el criterio de aceptación real.

**Criterio de aceptación**: verificado end-to-end contra el stack Docker
real (subida vía `curl -F`, sin UI real de navegador, pero mismo camino de
requests que usaría el JS): subí un `.txt` con un dato inventado dentro de
una conversación nueva, el chip pasó de "Pendiente" a "Indexado" en el
polling, y en el mismo hilo le pregunté por ese dato — Claude respondió
citando el valor exacto del documento recién subido. También verificado
el caso de fallo (archivo con mime type no soportado): el chip queda con
borde rojo, badge "Error" y el `error_message` real
("Tipo de archivo no soportado: application/octet-stream") visible, sin
fallar en silencio. `/documentos/` confirmado sin cambios de
comportamiento (mismas cards completas de siempre). Documentos y
conversaciones de prueba borrados (incluyendo vectores en Qdrant) al
terminar.

---

### Fase 17 — Reranker sobre la búsqueda híbrida

**Objetivo**: capa extra de precisión sobre la fusión RRF de la Fase 12
— un cross-encoder re-ordena los candidatos ya fusionados (mira
query+chunk juntos, más preciso que comparar embeddings por separado)
antes de devolver los `top_k` finales a Claude.

Tareas:
- [x] Modelo de reranking: se evaluó primero `fastembed` (ya era
      dependencia desde la Fase 12), que trae reranking vía
      `fastembed.rerank.cross_encoder.TextCrossEncoder`. Su único modelo
      marcado como multilingüe, `jinaai/jina-reranker-v2-base-
      multilingual` (1.1GB), funcionaba bien en precisión pero **medido en
      este host (2 CPUs físicas, ARM64, sin GPU) tardaba ~19-70s por
      búsqueda real** (chunks de hasta 800 caracteres, `CHUNK_SIZE` de
      `rag_shared/chunker.py`) — inviable para un chat interactivo, incluso
      después de fijar el número de threads (ver más abajo). Se cambió a
      `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` vía
      **sentence-transformers** (~470MB, mismo framework que ya usa el
      embedding denso, entrenado en mMARCO — cubre español) y quedó en
      ~5-6s para 10 candidatos. Decisión confirmada con el usuario
      (pregunta explícita tras medir, con las 4 opciones evaluadas) antes
      de implementarla.
- [x] `rag_shared/embeddings.py`: `get_reranker()` (mismo patrón lazy +
      `lru_cache` que `get_model()`/`get_sparse_model()`) +
      `rerank(query: str, texts: list[str]) -> list[float]` (scores, un
      float por texto, mismo orden de entrada). `RERANK_THREADS` (default
      1) fija `torch.set_num_threads` — **crítico** en este host: sin
      fijarlo, torch arranca su pool según `os.cpu_count()` (ve las 2 CPUs
      físicas del host, no la cuota de 1.0 CPU del cgroup del contenedor)
      y esos threads de más quedan constantemente throttled — el mismo
      request pasa de ~4s a ~70s solo por ese overhead de contención
      (medido primero con el reranker de fastembed/onnxruntime, mismo
      principio aplica a torch).
- [x] `vector_store.search()` sin cambios (no hizo falta): pedir más
      candidatos que `top_k` al fusionar se logra pasándole a
      `vector_store.search()` un `top_k` más alto desde `rag_search` — la
      función no necesita saber que el resultado se va a rerankear
      después.
- [x] `rag-mcp/server.py::rag_search`: pide `top_k *
      _RERANK_CANDIDATE_MULTIPLIER` candidatos, rerankea (tiene el texto
      de la query a mano) y corta a `top_k` recién al final. Multiplicador
      final: **2** (10 candidatos con el `top_k=5` default), no el 4 (20
      candidatos) que sugería el plan original — con 4x medía ~19s incluso
      con el modelo chico, muy por encima de lo tolerable.
- [x] Latencia: medida exhaustivamente contra el stack real (ver arriba) —
      determinó tanto el cambio de modelo como el multiplicador final.
- [x] `preload()` (`embeddings.py`) precarga también el modelo de
      reranking en build-time. `rag-mcp/entrypoint.sh` tuvo que ajustarse
      también: el semillado del volumen `models-cache` desde el seed de
      build-time solo corría si el volumen estaba completamente vacío —
      en un deploy que ya tenía el denso/sparse de fases anteriores, el
      reranker nuevo se hubiera quedado sin semillar (se habría bajado
      igual en el primer uso real). Cambiado a `cp -an` (merge, no
      clobber) sin la condición de "vacío".
- [x] `compose.yaml`: límite de memoria de `chat-rag-mcp` subido de 1.5G a
      2.5G (medido: los tres modelos cargados en un turno real de chat
      ocupan ~1.2-1.3GB en este host, 2.5G deja margen sin sobre-reservar
      en un host compartido con otros proyectos).

**Decisión de arquitectura, confirmada con el usuario**: el plan original
asumía que el reranker sumaría poco tiempo ("ajustar el multiplicador si
pega mucho"). La realidad medida en este host (2 CPUs, ARM64, sin GPU,
compartido con varios otros proyectos) fue mucho peor de lo esperado —
ver el detalle en las tareas de arriba. Se le presentaron 4 opciones al
usuario (modelo chico + pocos candidatos / aún menos candidatos / seguir
con el modelo grande de fastembed / descartar el reranker) con la
latencia real medida de cada una; eligió la primera.

**Criterio de aceptación**: documentos de prueba subidos con un caso
concreto de ambigüedad léxica (mismo criterio que "ZJ" en la Fase 12) —
tres documentos cortos, dos "decoy" que repiten mucho el término literal
de la query ("código de descuento") sin responderla realmente, uno que sí
la responde pero con un sinónimo ("cupón") y menor densidad léxica.
Query: *"¿Cómo aplico un código de descuento antes de pagar?"*. Antes del
reranking (fusión RRF), el chunk correcto y uno de los decoy quedaban
**empatados en el primer puesto** (mismo score RRF, 0.8333, orden entre
ellos indefinido de una corrida a otra). Después del reranking, el chunk
correcto queda claro y consistentemente en el puesto #1 (score 1.33 vs.
-4.79 del decoy). Confirmado también end-to-end con un turno de chat real
(no solo a nivel de `vector_store`/`rerank()`): Claude respondió citando
primero el procedimiento correcto (aplicar el cupón en el checkout) y
mencionó la lista de códigos del decoy como información secundaria. Datos
de prueba borrados de la cuenta real al terminar.

---

### Fase 18 — Búsqueda en el historial de conversaciones

**Objetivo**: hoy el sidebar solo lista conversaciones por fecha/título
— no hay forma de encontrar "¿en qué conversación pregunté tal cosa?"
sin abrir una por una.

Tareas:
- [x] `chat/views.py`: vista nueva `search_conversations` — `Message.
      objects.filter(conversation__user=request.user,
      content__icontains=q)`, agrupado por conversación (un resultado por
      conversación: el mensaje que matcheó más reciente). Excluye mensajes
      de rol `tool` (mismo criterio de privacidad que
      `export_conversation`/`shared_conversation`). SQLite con
      `icontains` alcanza para el volumen de uso personal actual — FTS5
      queda como mejora natural si algún día hace falta.
- [x] UI: input de búsqueda arriba de la lista de conversaciones en el
      sidebar (`base.html`) — htmx (`hx-get` con debounce de 300ms +
      evento `search` nativo del input al vaciarlo con la "x", instantáneo
      sin esperar el debounce). `q` vacío devuelve el mismo partial de la
      lista normal (`partials/_sidebar_conversations.html`, extraído del
      bloque que antes estaba inline en `base.html`) — "borrar la
      búsqueda" revierte al estado de siempre sin lógica aparte en el
      cliente.
- [x] Resultados (`partials/_sidebar_search_results.html`): lista de
      conversaciones que matchearon, cada una con un snippet corto
      (`SEARCH_SNIPPET_RADIUS=60` caracteres de contexto a cada lado del
      match) del mensaje que hizo match y link directo a esa conversación.
- [x] Sin resaltado del mensaje dentro de `conversation.html` al llegar
      desde un resultado de búsqueda — se dejó afuera de esta fase, tal
      como preveía el plan.
- [x] Gotcha encontrado en el camino (no estaba en el plan original): los
      items de `_sidebar_conversations.html` tienen `x-data` (el botón de
      borrar, Fase 8) — un swap de htmx reemplaza HTML "a mano"
      (`innerHTML`), sin pasar por el ciclo de vida de Alpine, así que el
      contenido repuesto tras volver de una búsqueda quedaba con esos
      botones sin inicializar (mismo síntoma que el gotcha de orden de
      carga de scripts ya documentado, causa distinta). Fix en
      `sidebar.js`: listener global de `htmx:afterSwap` que llama
      `Alpine.initTree()` sobre el nodo que acaba de entrar al DOM.

**Criterio de aceptación**: verificado contra el stack Docker real — dos
conversaciones de prueba, una "vieja" (`updated_at` forzado a 20 días
atrás) con un término distintivo, otra "reciente" sin relación. Buscar el
término trae solo la conversación vieja, con un link que lleva directo a
ella. Confirmado también: 0 resultados no rompe nada (mensaje claro sin
resultados), 2+ resultados ordenan por `updated_at` descendente (más
reciente primero), pluralización correcta ("1 resultado" vs "N
resultados"), un mensaje de rol `tool` con el término buscado NO aparece
en los resultados (privacidad), y volver a page completa (no fragmento)
resalta correctamente la conversación activa vía el nuevo
`active_conversation_id`. Datos de prueba borrados de la cuenta real al
terminar.

---

### Fase 19 — Importar desde Google Drive

**Objetivo**: retomar la Fase 6 (opcional) de `plan.md` — importar
Google Docs/Sheets/Slides sin tener que descargarlos manualmente primero.
Sigue bloqueada por lo mismo que en v1: requiere que el usuario cree
primero un proyecto en Google Cloud Console + credenciales OAuth
(Desktop app) y habilite Drive API + Picker API — un paso que no se puede
resolver desde acá, por eso queda última en la lista.

Tareas (sin cambios respecto al plan original, ver `plan.md` sección
"Fase 6" para el detalle completo):
- [ ] Credenciales OAuth de Google (bloqueante, lo hace el usuario).
- [ ] Flujo OAuth para vincular la única cuenta de Google del usuario
      (uso 100% personal, no hace falta multi-cuenta).
- [ ] Botón "Importar de Drive" en `/documentos/` + Google Picker JS.
- [ ] Backend descarga vía Drive API con `export` (Doc→docx,
      Sheet→xlsx, Slide→pptx), guarda en `MEDIA_ROOT` y encola el task
      de ingesta normal (`process_document`) — mismo camino que un
      archivo subido a mano, sin lógica de indexado especial.

**Criterio de aceptación**: seleccionar un Google Doc desde el picker lo
indexa en el RAG, igual que subir el archivo a mano hoy.

---

### Fase 20 — Reportería: infraestructura + formatos tabulares (.txt, .csv, .xlsx)

**Objetivo**: sienta la base de todo lo demás (guardado + descarga de
archivos generados) y cubre el caso de uso concreto pedido — pedirle al
chat que cruce datos de dos consultas vía `data-platform` (ej. "traeme
los clientes con puntualidad A de la base 1 y de la central, y decime
cuáles no están en ambas o tienen datos distintos") y devuelva el
resultado como archivo. Claude ya sabe hacer el cruce/diff en texto —
acá solo se le da una forma de bajarlo como archivo real en vez de
pegarlo en el chat.

Tareas:
- [ ] `data/media/reports/` — nuevo subdirectorio del volumen `media`
      existente. `compose.yaml::chat-rag-mcp`: agregar mount
      `./data/media/reports:/data/media/reports` (RW, a diferencia del
      mount `:ro` que ya tiene para `data/sqlite`) y la env var
      `PUBLIC_BASE_URL` (hoy solo la lee `chat-web`).
- [ ] `rag_shared/reports.py` (nuevo módulo, mismo criterio que
      `rag_shared/embeddings.py`/`vector_store.py` — compartido, aunque
      de momento solo lo use `chat-rag-mcp`): funciones `write_txt`,
      `write_csv`, `write_xlsx` — reciben datos ya estructurados
      (`list[dict]` o `list[list]` + headers) y devuelven la ruta del
      archivo escrito bajo un nombre `<uuid4>.<ext>`. `write_xlsx` usa
      `openpyxl.Workbook()` (ya es dependencia de `rag_shared`, hoy solo
      se usa para leer).
- [ ] `rag-mcp/server.py`: tool nueva `report_generate_table(format:
      Literal["txt","csv","xlsx"], title: str, columns: list[str], rows:
      list[list[str]]) -> str` (devuelve la URL completa de descarga,
      armada con `PUBLIC_BASE_URL`). Agregar al `SYSTEM_PROMPT` de
      `chat/agent.py` cuándo usarla (ej. "cuando el usuario pida
      explícitamente un archivo/reporte/exportar datos en vez de verlos
      en el chat") **y aclarar explícitamente que `generate_report` de
      `data-platform` NO se usa para esto** (ver la nota de arquitectura
      más arriba) — sin esa aclaración nada impide que Claude la elija
      igual, ya que las dos aparecen como tools disponibles.
- [ ] Vista Django nueva para servir la descarga — evaluar si conviene
      una app `apps/reports/` propia (más limpio si las Fases 21/22
      suman más lógica acá) o un par de funciones sueltas en
      `apps/core/views.py` (más simple si esto no crece mucho). Sirve
      `data/media/reports/<archivo>` con `FileResponse(...,
      as_attachment=True)`; protegida por el `@login_required` normal
      del sitio (sin modelo de dueño — es de un solo usuario).
- [ ] Sin tracking en DB para este v1 (ver la nota de arquitectura más
      arriba) — los archivos viejos se acumulan en el volumen sin
      límite; anotar como conocido, evaluar limpieza (cron simple tipo
      "borrar lo de más de N días", similar en espíritu al de
      `scripts/backup.sh` de la Fase 9) si en la práctica molesta.

**Criterio de aceptación**: le pido al chat el reporte de clientes
descrito arriba (dos consultas vía `data-platform` + el cruce), me
responde con un link, lo clickeo y se descarga un .xlsx real con las
filas correctas — comparado a mano contra lo que devuelven las dos
queries por separado.

---

### Fase 21 — Reportería: documentos de oficina (.docx, .pptx, .pdf)

**Objetivo**: el otro caso de uso pedido — "generame un resumen /
reporte del documento X" como archivo entregable, no solo texto en el
chat. Cubre Word, PowerPoint y PDF.

Tareas:
- [ ] `rag_shared/reports.py`: `write_docx` (`python-docx`, ya
      dependencia — título + secuencia de secciones con
      título/párrafos/bullets, sin diseño elaborado en v1) y `write_pptx`
      (`python-pptx`, ya dependencia — una diapositiva por sección,
      layout título+contenido).
- [ ] `write_pdf`: acá sí hace falta una dependencia nueva —
      `reportlab` o `fpdf2` (evaluar al implementar; `fpdf2` es más
      simple para reportes de texto/tablas, `reportlab` da más control
      de layout si hace falta algo más elaborado más adelante).
- [ ] `rag-mcp/server.py`: tool `report_generate_document(format:
      Literal["docx","pptx","pdf"], title: str, sections:
      list[{heading: str, body: str}]) -> str` — mismo shape de retorno
      (URL) que `report_generate_table`. El input son secciones ya
      redactadas por Claude (leyó el documento fuente vía `rag_search`/
      `rag_get_document_chunks` y armó el resumen/contenido él mismo),
      la tool solo maqueta y exporta.
- [ ] `SYSTEM_PROMPT`: instrucción de cuándo elegir cada formato si el
      usuario no lo especifica (ej. pptx para algo tipo presentación,
      docx para un informe/resumen largo, pdf cuando pide explícitamente
      "PDF" o algo para imprimir/archivar).

**Criterio de aceptación**: le pido "hazme un resumen ejecutivo del
documento X en Word" (o PowerPoint, o PDF), y el archivo descargado
tiene contenido real y coherente con ese documento, no un placeholder.

---

### Fase 22 — Reportería: diagramas e imágenes (.drawio, gráficos)

**Objetivo**: la parte más incierta de las tres — "generá un diagrama de
acuerdo al documento X". Separada en dos entregables bien distintos
porque la dificultad técnica es muy distinta entre ellos.

**Parte A — `.drawio` (XML editable, sin rasterizar)**: es solo un
esquema XML (`mxGraphModel`) — no hace falta ninguna librería de
diagramación, alcanza con construir el árbol a mano
(`xml.etree.ElementTree`, stdlib) a partir de nodos/posiciones/aristas
que arma Claude. El usuario lo abre después en diagrams.net/draw.io para
editarlo — no se renderiza una imagen del lado del servidor acá.

**Parte B — imagen rasterizada (PNG)**: acá NO conviene un enfoque tipo
Mermaid/drawio-en-vivo (necesitan un navegador headless — Puppeteer/
Chrome — pesado para este contenedor ARM64 chico). La opción liviana es
**Graphviz** (paquete apt `graphviz`, expone el binario `dot`): Claude
describe el diagrama como nodos/aristas con atributos simples, se arma
un `.dot` y `dot -Tpng` lo rasteriza sin depender de un browser. Para
gráficos de datos (no diagramas de flujo/relación sino charts de una
tabla), `matplotlib` es más directo — evaluar si esta fase cubre ambos
casos o si el chart de datos merece su propia sub-tarea más adelante.

Tareas:
- [ ] `rag_shared/reports.py`: `write_drawio` (XML a mano, sin
      dependencia nueva).
- [ ] `rag-mcp/Dockerfile`: instalar `graphviz` (apt) — medir cuánto
      suma al tamaño/tiempo de build de esta imagen, que ya carga
      sentence-transformers + fastembed + torch, antes de decidir si
      vale la pena o conviene un servicio aparte para esto.
- [ ] `rag_shared/reports.py`: `write_diagram_png` (arma el `.dot` desde
      nodos/aristas, corre `dot -Tpng` vía `subprocess`).
- [ ] (Opcional/evaluar si entra en esta fase) `write_chart_png` con
      `matplotlib` para gráficos de barras/líneas/torta a partir de
      datos tabulares — caso de uso distinto al de "diagrama de un
      documento" (más cercano a la Fase 20, cruce de datos numéricos).
- [ ] `rag-mcp/server.py`: tool `report_generate_diagram(format:
      Literal["drawio","png"], nodes: list[{id, label}], edges:
      list[{from, to, label}]) -> str`.
- [ ] Con el link de descarga de un `.png`, evaluar si además conviene
      que Claude lo referencie como imagen inline (`![diagrama](url)`,
      markdown estándar) en vez de solo como link — depende de si el
      renderer de markdown del chat (`static/js/chat.js`) ya soporta
      `<img>` o hay que habilitarlo a propósito.

**Criterio de aceptación**: le pido "generá un diagrama de flujo de
según el documento X" — el `.drawio` abre limpio en draw.io con los
nodos/relaciones reales del documento, y/o el `.png` (Graphviz) se ve
como un diagrama de flujo legible, no un placeholder ni nodos sueltos
sin relación con el contenido real.

---
