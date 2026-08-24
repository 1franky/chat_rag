# chat_rag — Plan v4 (rediseño visual)

Continuación de `plan-v3.md` (Fases 14–22, completas salvo la 19 —
Google Drive — bloqueada por credenciales OAuth). Estas son fases
nuevas, todavía sin implementar — mismo flujo de siempre: cada una en su
propia rama `Feature/Fase-NN`, se prueba contra el stack Docker real, se
commitea/pushea/PR, el usuario mergea (ver `plan.md` para las
convenciones completas).

Numeración continua desde la Fase 22.

**Motivación**: a pedido explícito del usuario tras revisar la app en
uso — la interfaz funciona bien pero "no gustó del todo". Encuestado
sobre qué específicamente, marcó tres cosas: se ve genérica/cruda, la
densidad y jerarquía visual compiten entre sí, y el comportamiento en
mobile no está pulido. Sobre el alcance, eligió **"rediseño visual más
fuerte"** — nueva paleta/identidad de marca, no solo un pulido
incremental de lo que ya hay, pero tampoco una reescritura de layout o
flujos (eso queda descartado a propósito: mucho más esfuerzo y riesgo de
romper cosas que ya andan bien).

**Diagnóstico de partida** (inspección de `web/templates/`,
`web/tailwind/input.css` y `web/static/js/`, sin haber tocado nada
todavía):

- El sistema de diseño ya está tokenizado en variables CSS al estilo
  shadcn (`--background`, `--foreground`, `--primary`, `--accent`,
  `--border`, `--ring`, etc. en `tailwind/input.css`, un solo lugar para
  claro y oscuro) — buena base para retocar la identidad sin tener que
  tocar cada template, pero **hoy no hay ningún color de marca real**:
  `--primary` es literalmente slate oscuro/claro (mismo tono que
  `--foreground`), y el resto de la paleta es gris neutro + rojo solo
  para destructive. De ahí sale gran parte de la sensación "genérica".
- Los íconos son emojis planos incrustados directo en los templates
  (☰ ➕ 📎 🔗 🔧 ↻), sin ningún set de íconos real ni tamaño/trazo
  consistente entre ellos.
- El header de una conversación (`conversation.html`) acumula 3 badges
  chicos (modelo, costo, link compartido) + 4 acciones como texto suelto
  ("Compartir" / "Exportar" / "Borrar" + el que corresponda de
  copiar/revocar) en una sola fila apretada — compiten entre sí, no hay
  jerarquía de qué es información vs. qué es acción.
- El sidebar (`base.html`) es un ancho fijo (`w-64`/`w-0` con
  `transition-all`) que empuja el contenido — no hay ningún breakpoint
  para mobile; en una pantalla angosta el toggle sigue empujando en vez
  de superponerse como overlay.
- Message bubbles (`_message.html`) son simples (usuario/asistente/tool)
  sin avatar ni agrupamiento visual — todo el peso de diferenciar "quién
  habla" recae en la alineación izquierda/derecha y el color de fondo.
- Ya existen buenas bases para construir encima sin reinventar nada:
  fuente self-hosted (`InterVariable`, variable weight), dark mode ya
  andando vía clase `.dark`, `@view-transition` nativo entre navegaciones,
  clase `.skeleton` para loaders. El rediseño reusa todo esto, no lo
  reemplaza.

**Decisión de alcance**: "rediseño más fuerte" se traduce acá en definir
una identidad de marca real (color de acento + tipografía/espaciado más
cuidados) y aplicarla de forma consistente a todas las pantallas, más un
verdadero paso mobile — pero **sin** reestructurar el layout de 2
columnas (sidebar + panel principal) ni los flujos existentes, que el
usuario no pidió tocar. Fases separadas por superficie (fundamentos →
navegación → chat → resto de pantallas → pulido final) para poder
revisar y mergear cada una por separado, igual que el resto del plan.

**Opcional antes de arrancar la Fase 23**: si el usuario quiere ver la
dirección visual (paleta + tipografía + un par de componentes clave)
antes de que se toque código real, se puede armar un mockup rápido con
Claude Design (canvas editable) para aprobar la identidad primero — no
es obligatorio, se puede saltar directo a la Fase 23 y ajustar sobre el
código real si se prefiere iterar así.

---

### Fase 23 — Identidad visual: paleta de marca + set de íconos ✅

**Objetivo**: sentar las bases del rediseño en un solo lugar
(`tailwind/input.css`) antes de tocar ninguna pantalla — color de acento
real, y reemplazo de los emojis por un set de íconos SVG de verdad.

Tareas:
- [x] Elegir un color de acento (con el usuario) y agregarlo a los
      tokens de `tailwind/input.css`. Se armó un preview real (Artifact
      HTML) con 4 candidatos (azul/índigo/violeta/cian) aplicados sobre
      los tokens neutros exactos del proyecto, con mini-mockup de
      sidebar+header+chat por candidato y alternador de tema — el
      usuario eligió **violeta** (`#7c3aed` claro / `#a78bfa` oscuro).
      Se reusó directamente para `--primary`/`--primary-foreground` (no
      hizo falta un token `--accent-brand` separado) y también para
      `--ring` (mismo valor que `--primary`, patrón shadcn habitual —
      el foco de inputs/botones queda "de marca" en vez del gris
      genérico de antes). Ámbar/esmeralda/rojo quedaron afuera de las
      opciones a propósito (ya son semántica de estado en
      `documents.html`). Contraste AA verificado con cálculo real
      (luminancia relativa WCAG, no estimado): 5.7:1 en claro, 6.6:1 en
      oscuro para texto sólido sobre el acento.
- [x] Revisar escala de `--radius` y sombras — ya cubría los 3 casos
      reales del proyecto (sm: badges/chips, md: inputs/botones/
      mensajes, lg: cards/popovers), no hizo falta agregar ni cambiar
      nada, solo se dejó un comentario documentando la revisión.
- [x] Vendoreado un set de 16 íconos SVG reales de **Lucide** (ISC
      License, `web/static/icons/lucide/*.svg` + `LICENSE`) — mismo
      criterio que Inter/Alpine/htmx/marked/highlight.js: archivos
      locales, sin CDN. Set final: `menu`, `plus`, `files`, `search`,
      `paperclip`, `share-2`, `copy`, `unlink-2`, `download`,
      `trash-2`, `rotate-ccw`, `wrench`, `sun`, `moon`, `send`, `x`.
- [x] Mecanismo de inserción: script nuevo `scripts/build_icon_sprite.py`
      (sin dependencias fuera de stdlib) combina los SVG sueltos en UN
      sprite `<symbol>` (`templates/partials/icon_sprite.html`,
      generado, no se edita a mano), incluido una sola vez en
      `base.html`. Cada uso real es el tag
      `{% templatetag openblock %} icon "nombre" {% templatetag closeblock %}`
      (`apps/core/templatetags/core_extras.py`), que renderiza
      `<svg class="icon"><use href="#icon-nombre"></use></svg>` — la
      clase `.icon` (`tailwind/input.css`) repone `fill`/`stroke`/
      `stroke-width` vía CSS (el sprite los recorta al armar los
      `<symbol>`), así `stroke: currentColor` deja que cualquier
      utility de color (`text-destructive`, `hover:text-foreground`,
      etc.) tiña el ícono igual que a un texto. Parámetro `label` en el
      tag para el caso de un ícono suelto sin control que ya lo nombre
      (no usado todavía — el caso real, el botón ☰, ya tenía su propio
      `aria-label`, así que el ícono ahí queda `aria-hidden`).
- [x] Prueba de humo: ☰ del header reemplazado por `{% icon "menu" %}`.
      Agregar un ícono nuevo en una fase futura es bajar el `.svg` de
      Lucide a `static/icons/lucide/` y re-correr el script.

**Criterio de aceptación**: verificado contra el stack Docker real
(`docker compose build chat-web && docker compose up -d chat-web`,
Tailwind compilado con el CLI standalone v4.3.3 linux-arm64 antes del
build — mismo binario que ya se usaba en fases anteriores, no committeado
al repo). `static/css/tailwind.css` servido confirma `--primary:#7c3aed`
(claro) y `#a78bfa` (oscuro) y la clase `.icon` con el CSS esperado.
`/chat/` (sesión real vía `SessionStore`, limpiada al terminar) devuelve
el sprite completo (16 `<symbol>`) y el botón ☰ renderiza
`<use href="#icon-menu">` con `aria-hidden="true"` en el SVG y el
`aria-label` en el `<button>` — sin ninguna otra pantalla tocada todavía
(quedan con emoji hasta las fases 24-27, tal como preveía el plan).

---

### Fase 24 — Sidebar y navegación

**Objetivo**: aplicar la identidad nueva a la navegación, y resolver el
comportamiento en mobile (hoy el sidebar empuja el contenido en vez de
superponerse).

Tareas:
- [ ] Sidebar (`base.html`): logo/wordmark con algo de tratamiento (no
      solo texto plano "chat_rag"), botón "Nueva conversación" e ícono de
      Documentos con los íconos reales de la Fase 23, mejor separación
      entre secciones (nueva conversación / buscar / lista / usuario).
- [ ] Buscador (`_sidebar_conversations.html`/input de búsqueda): ícono
      de lupa dentro del input, estado vacío de resultados con algo más
      que texto plano.
- [ ] Mobile (breakpoint a definir, probablemente `lg`): el sidebar pasa
      de empujar contenido a un overlay con backdrop (Alpine ya maneja
      `sidebarOpen`, se extiende con una media query / clase condicional
      + cierre al click afuera y con Escape, mismo patrón que ya usa
      `x-cloak` en otros lados).
- [ ] `user_menu.html` y `theme_toggle.html`: revisar que los targets
      táctiles tengan tamaño suficiente en mobile (mínimo ~44px).

**Criterio de aceptación**: probado contra el stack Docker real en
viewport de escritorio y en un viewport angosto simulado (devtools,
~375px) — el sidebar en mobile se abre como overlay sin empujar el
chat, cierra con click afuera/Escape, y todos los íconos/textos son
legibles y clickeables en ambos tamaños.

---

### Fase 25 — Chat: burbujas, header y composer

**Objetivo**: es la pantalla que más se usa — aplicar la identidad
nueva a mensajes, header de conversación y composer, resolviendo la
jerarquía apretada que hay hoy.

Tareas:
- [ ] `_message.html`: distinción visual más clara entre roles (avatar o
      ícono chico por rol en vez de depender solo de alineación +
      color), más aire entre mensajes consecutivos del mismo rol vs. de
      roles distintos, mensajes de `tool` con ícono/color propio en vez
      del 🔧 emoji.
- [ ] Header de `conversation.html`: agrupar acciones secundarias
      (Exportar / Borrar / Revocar) en un menú "..." con íconos, dejar
      "Compartir"/"Copiar link" como acción primaria visible; badges de
      modelo/costo/link con tratamiento visual más liviano (evitar 3
      pills apretadas compitiendo con el título).
- [ ] Composer: botón de adjuntar y botón de enviar con íconos reales,
      estado "pensando"/`sending` con un indicador más claro que "…"
      (ej. 3 puntos animados, reusando `.skeleton` o una animación nueva
      chica).
- [ ] Chip de adjunto (`_chat_attachment_chip.html`) y botón de
      reintentar (↻) actualizados al nuevo set de íconos.
- [ ] Estado vacío (prompts sugeridos, tanto en `empty.html` como dentro
      de `conversation.html`) con el tratamiento visual nuevo.

**Criterio de aceptación**: conversación real de prueba (mensajes de
usuario/asistente/tool, un adjunto, un turno fallido con reintento)
revisada visualmente en claro y oscuro — jerarquía clara de qué es
mensaje vs. acción vs. metadata, sin regresión funcional (todo lo que
andaba sigue andando: enviar, adjuntar, compartir, exportar, borrar,
reintentar).

---

### Fase 26 — Documentos, configuración y resto de pantallas

**Objetivo**: extender la identidad nueva al resto de la app para que no
quede la sensación de "dos apps distintas" (chat rediseñado vs. el
resto igual que antes).

Tareas:
- [ ] `documents.html` / `_document_card.html`: cards con el nuevo
      sistema de espaciado/color, íconos por tipo de archivo o estado
      (pendiente/indexado/error) en vez de solo texto/color de badge.
- [ ] `accounts/settings.html`, `accounts/login.html`: mismo tratamiento
      de inputs/botones que el resto.
- [ ] `404.html`/`500.html`/`shared_conversation.html`: revisar que no
      queden visualmente desalineados del resto (son standalone, no
      extienden `base.html`, hay que portar los tokens/fuente a mano).
- [ ] `partials/toasts.html`: revisar que el estilo de los toasts
      combine con la paleta nueva.

**Criterio de aceptación**: recorrido visual de todas las pantallas de
la app (login, home vacío, conversación, documentos, configuración,
página compartida, 404) en claro y oscuro — mismo lenguaje visual en
todas, sin ninguna pantalla "vieja" mezclada con las rediseñadas.

---

### Fase 27 — Microinteracciones y pulido final responsive

**Objetivo**: última pasada, después de que todas las pantallas ya usan
la identidad nueva — detalles de movimiento/feedback y una verificación
mobile completa (no solo el sidebar de la Fase 24).

Tareas:
- [ ] Transición de entrada sutil para mensajes nuevos en el chat
      (`@view-transition` ya existe para navegación entre páginas; acá
      es dentro de la misma página, vía CSS/Alpine).
- [ ] Feedback de click/press en botones principales (no solo `:hover`,
      que no existe en touch).
- [ ] Pasada mobile completa en cada pantalla tocada en las Fases 24-26
      (no solo el sidebar): composer no tapado por el teclado virtual,
      cards de documentos en una columna, formularios de settings/login
      usables sin zoom.
- [ ] Revisión de contraste del color de marca nuevo contra
      `--background`/`--foreground` en ambos modos (WCAG AA como
      mínimo) — puede requerir ajustar el tono elegido en la Fase 23 si
      no pasa en alguno de los dos modos.

**Criterio de aceptación**: recorrido completo de la app en viewport de
escritorio y mobile simulado, con el tema alternado entre claro/oscuro
en cada pantalla — nada se ve "a medio hacer", sin regresiones
funcionales en ningún flujo existente.

---

Fuera de alcance de este plan (a propósito, por la decisión de "sin
reescritura de layout/flujos"): reordenar el layout de 2 columnas,
cambiar cómo funciona cualquier flujo existente (compartir, adjuntar,
reintentar, etc.), o agregar pantallas/funcionalidad nueva — eso sigue
siendo terreno de `plan-v3.md` (Fase 19, Google Drive) o de un
`plan-v5.md` futuro si surge algo nuevo.
