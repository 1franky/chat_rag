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
- [ ] `chat/models.py::Conversation.total_cost_usd` — `DecimalField`
      (o `FloatField`, ver qué tan preciso hace falta que sea; SQLite no
      tiene problema con `Decimal` vía Django) default 0, se acumula
      turno a turno.
- [ ] Migración.
- [ ] `chat/agent.py`: el evento `"done"` que ya arma la rama
      `ResultMessage` (donde vive `resolved_model`, agregado en la
      Fase 13) suma `"cost_usd": message.total_cost_usd`.
- [ ] `chat/views.py::stream_message`: en el bloque `elif event_type ==
      "done"` (mismo lugar donde ya se loguea `chat_turn_done` y se
      actualiza `agent_session_id`), sumar `event["cost_usd"]` a
      `conversation.total_cost_usd` antes del `asave` (agregar el campo a
      `update_fields`). `total_cost_usd` puede venir `None` en turnos que
      fallaron antes de completar — tratarlo como 0.
- [ ] UI: badge en el header de `conversation.html`, al lado del badge de
      modelo que ya existe (Fase 13) — `${{ conversation.total_cost_usd
      }}` con 3-4 decimales, texto chico, sin interacción.
- [ ] Opcional/nice-to-have: mostrarlo también en el sidebar (junto al
      título de cada conversación) para comparar de un vistazo cuáles
      salieron más caras — evaluar si no satura visualmente un espacio ya
      angosto (256px de ancho).

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
- [ ] `chat/views.py`: nuevo endpoint (ej. `POST
      /chat/<uuid:conversation_id>/reintentar/`) o flag en
      `stream_message` que, en vez de leer `message` del body, toma el
      texto del último `Message` con `role=USER` de la conversación —
      solo si el `Message` de `role=ASSISTANT` más reciente tiene
      `is_error=True` (si no, 400: no hay nada que reintentar).
- [ ] No duplicar el `Message` de rol `user` en la base (ya está guardado
      del intento anterior) — reusar el mismo flujo de streaming de
      `stream_message` pero saltando el `Message.objects.acreate(...,
      role=USER, ...)` inicial.
- [ ] UI: botón "↻ Reintentar" visible solo bajo el último mensaje del
      asistente cuando ese mensaje quedó marcado con error (mismo
      criterio visual que ya usa `_message.html` para pintar errores,
      revisar cómo distingue `is_error` hoy).
- [ ] `static/js/chat.js`: la llamada al nuevo endpoint reusa el mismo
      manejo de SSE que ya existe para mandar un mensaje normal (no
      duplicar lógica de parseo de eventos).

**Criterio de aceptación**: fuerzo un error (ej. cortando `chat-rag-mcp`
un momento así una tool falla, o algo que dispare `is_error`), aparece el
botón, lo aprieto sin retipear nada, y el turno se reintenta con el mismo
texto.

---

### Fase 16 — Adjuntar documentos desde el chat

**Objetivo**: hoy subir un documento requiere salir de la conversación e
ir a `/documentos/`. Agregar un botón de adjuntar directo en el
composer, sin cambiar de pantalla.

Tareas:
- [ ] `static/js/chat.js`: botón 📎 en el composer + `<input
      type="file" hidden>`, dispara la misma request que ya usa
      `apps/ingesta/views.py::upload` (`POST /documentos/subir/`,
      `multipart/form-data`, campo `file`) — **no hace falta backend
      nuevo**, ese endpoint ya devuelve `{document_id, card_html}` y no
      está atado a `/documentos/` de ninguna forma especial.
  - Confirmar que `upload()` no tiene ninguna restricción de referer/CSRF
    que choque al llamarlo desde `conversation.html` en vez de
    `documents.html` (debería ser el mismo `@login_required` +
    `@require_POST` de siempre, sin nada extra que revisar).
- [ ] Mientras se indexa: chip inline en el composer o como mensaje de
      sistema liviano en el hilo — "📎 archivo.pptx — indexando…" — con
      polling al endpoint que ya existe (`ingesta:status`, mismo patrón
      htmx/JS que usa `documents.html`) hasta que el `status` sea
      `indexed` o `failed`.
- [ ] Si falla la ingesta (`status=failed`), mostrar el `error_message`
      del `Document` en el mismo chip, no fallar en silencio.
- [ ] Sin selector de colección desde acá (a propósito, para no
      complicar el flujo rápido) — el documento entra sin colección
      asignada; si el usuario quiere organizarlo, lo mueve después desde
      `/documentos/` (Fase 10, ya soporta eso).
- [ ] `SYSTEM_PROMPT` (`chat/agent.py`) no necesita cambios — `rag_search`
      ya busca en todo lo indexado por default, así que apenas termina de
      indexarse el documento recién subido ya es encontrable en la misma
      conversación.

**Criterio de aceptación**: subo un archivo nuevo sin salir de la
conversación, veo el indicador de "indexando…" pasar a "listo", y en el
mismo hilo le pregunto algo sobre ese documento y me responde con su
contenido.

---

### Fase 17 — Reranker sobre la búsqueda híbrida

**Objetivo**: capa extra de precisión sobre la fusión RRF de la Fase 12
— un cross-encoder re-ordena los candidatos ya fusionados (mira
query+chunk juntos, más preciso que comparar embeddings por separado)
antes de devolver los `top_k` finales a Claude.

Tareas:
- [ ] `fastembed` (ya es dependencia desde la Fase 12) trae también
      reranking vía `fastembed.rerank.cross_encoder.TextCrossEncoder` —
      revisar el catálogo de modelos vigente antes de fijar uno (mismo
      cuidado que con los IDs de modelo de Claude en la Fase 13: estas
      cosas cambian). Tiene que ser multilingüe/soportar español, ya que
      los documentos indexados son en español.
- [ ] `rag_shared/embeddings.py`: `get_reranker()` (mismo patrón lazy +
      `lru_cache` que `get_model()`/`get_sparse_model()`) +
      `rerank(query: str, texts: list[str]) -> list[float]` (scores, un
      float por texto, mismo orden de entrada).
- [ ] `vector_store.search()`: pedir más candidatos que `top_k` al fusionar
      (ej. `top_k * 4`, tunear con pruebas reales) vía el mismo
      `prefetch`+RRF que ya existe, y en la capa de arriba (`rag_search`
      en `rag-mcp/server.py`, que es quien tiene el texto de la query a
      mano) rerankear esos candidatos y cortar a `top_k` recién ahí — el
      reranker necesita el texto de la query, no solo el vector, así que
      no encaja bien adentro de `vector_store.py` como las otras piezas.
- [ ] Latencia: el reranker corre sobre CPU igual que los embeddings —
      medir cuánto suma al tiempo de `rag_search` con `top_k * 4`
      candidatos reales y ajustar el multiplicador si pega mucho al
      turno completo.
- [ ] `preload()` (`embeddings.py`) precarga también el modelo de
      reranking en build-time, mismo mecanismo que los otros dos.

**Criterio de aceptación**: una query ambigua semánticamente (un término
que aparece en varios chunks pero solo uno responde realmente la
pregunta) — comparar el orden final antes/después de este cambio y
confirmar que el chunk correcto sube a la primera posición cuando antes
no estaba ahí. Documentar el ejemplo concreto usado, igual que se hizo
con "ZJ" en la Fase 12.

---

### Fase 18 — Búsqueda en el historial de conversaciones

**Objetivo**: hoy el sidebar solo lista conversaciones por fecha/título
— no hay forma de encontrar "¿en qué conversación pregunté tal cosa?"
sin abrir una por una.

Tareas:
- [ ] `chat/views.py`: vista nueva `search_conversations` — `Message.
      objects.filter(conversation__user=request.user,
      content__icontains=q)`, agrupado por conversación. SQLite con
      `icontains` alcanza para el volumen de uso personal actual (unas
      pocas decenas de conversaciones); si en algún momento se vuelve
      lento, migrar a FTS5 de SQLite es la mejora natural, no hace falta
      adelantarla ahora.
- [ ] UI: input de búsqueda arriba de la lista de conversaciones en el
      sidebar (`base.html`) — probablemente vía htmx (`hx-get` con
      debounce), mismo patrón liviano que ya usa el filtro de colecciones
      en `/documentos/`.
- [ ] Resultados: lista de conversaciones que matchearon, cada una con un
      snippet corto del mensaje que hizo match (no todo el mensaje) y
      link directo a esa conversación.
- [ ] Sin resaltado del mensaji dentro de `conversation.html` al llegar
      desde un resultado de búsqueda (`scrollIntoView` + highlight
      temporal) — evaluar si vale la pena en esta fase o queda para
      después, no es necesario para que la feature sea útil.

**Criterio de aceptación**: busco una palabra que sé que mencioné en una
conversación vieja (no la más reciente) y aparece en los resultados con
un link que me lleva directo a ella.

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
