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

### Fase 24 — Sidebar y navegación ✅

**Objetivo**: aplicar la identidad nueva a la navegación, y resolver el
comportamiento en mobile (hoy el sidebar empuja el contenido en vez de
superponerse).

Tareas:
- [x] Sidebar (`base.html`): logo/wordmark con tratamiento (cuadrado
      `bg-primary` de 24px con el ícono `message-square` + texto, en vez
      de texto plano suelto), íconos reales (`plus`/`files`) en "Nueva
      conversación"/"Documentos", separación entre secciones con un
      `border-b` nuevo entre el bloque de acciones y el de
      buscar+historial (ya había un `border-t` antes del usuario, quedan
      3 zonas visualmente claras) y labels de grupo ("Hoy"/"Ayer"/...)
      con tratamiento de eyebrow (uppercase + tracking, en vez de texto
      plano chico).
- [x] Buscador: ícono de lupa dentro del input (posicionado absoluto,
      `pl-8` en el input para no superponerse), estado vacío de
      resultados con el mismo ícono + más aire (`py-6`) en vez de una
      sola línea de texto.
- [x] Mobile: breakpoint `lg` (64rem/1024px, mismo que ya usaba el resto
      del proyecto en otros lados). Por debajo de `lg` el sidebar pasa a
      `fixed` + `-translate-x-full`/`translate-x-0` (desliza, no empuja)
      con un backdrop (`bg-black/50`) que cierra al clickear; en `lg` y
      para arriba sigue exactamente el comportamiento de siempre
      (`w-64`/`w-0` empujando el contenido). Un listener de
      `matchMedia('(min-width: 64rem)').addEventListener('change', ...)`
      en `x-init` mantiene `isMobile` sincronizado si la ventana cruza el
      breakpoint (no solo un check al cargar), y resetea `sidebarOpen` al
      default de cada modo al cruzarlo (abierto en desktop, cerrado en
      mobile) en vez de arrastrar el estado del modo anterior. Cierre con
      `Escape` agregado (`@keydown.window.escape`, solo actúa si
      `isMobile`) — Ctrl/Cmd+B siguen funcionando igual en ambos modos.
      Verificado a nivel CSS que la cascada resuelve como se espera: la
      regla base `.w-64` (sin variante) aparece ANTES del bloque
      `@media (min-width:64rem)` en el `tailwind.css` compilado, así que
      `lg:w-0`/`lg:w-64` (dentro de ese bloque) ganan en escritorio pese
      a la regla base siempre presente — sin esto el ancho fijo que hace
      falta en mobile (para que el drawer no dependa de la animación de
      ancho) podría haber quedado peleando con el `lg:w-0` en escritorio.
- [x] `user_menu.html` y `theme_toggle.html`: botones a `h-11 w-11` (44px,
      Tailwind `11 * 0.25rem`) en vez de `p-1.5`/`p-2` alrededor de un
      glifo chico. El botón "Salir" (texto, no ícono) pasó a `h-11` con
      más padding horizontal por consistencia de altura en la fila,
      aunque no sea un control solo-ícono. El botón de borrar por ítem de
      conversación (`_sidebar_conversations.html`) quedó
      deliberadamente MÁS CHICO que 44px (`p-1.5`, ícono `trash-2` de
      14px) — es una acción secundaria embebida en una fila densa, no un
      control autónomo; forzar 44px ahí hubiera roto la densidad de la
      lista para una ganancia marginal.

**Criterio de aceptación**: probado contra el stack Docker real (build +
up de `chat-web`, Tailwind recompilado) con una sesión real (limpiada al
terminar): `/chat/` sirve el sprite completo con los 2 íconos nuevos
(`message-square`, `settings`) además de los de la Fase 23, el `<aside>`
trae las clases `fixed`/`lg:static` y el toggle `translate-x-0 lg:w-64` /
`-translate-x-full lg:w-0 lg:translate-x-0` esperado. `/chat/buscar/?q=`
verificado con término sin resultados (estado vacío con ícono) y con
término real (5 resultados, label de grupo en mayúsculas). `/documentos/`
y `/settings/` siguen sirviendo 200 sin cambios de comportamiento. No se
pudo probar el drag/click real del backdrop ni el breakpoint con un
navegador de verdad en esta sesión (`claude-in-chrome` no estaba
conectado) — la lógica de Alpine (`matchMedia`, `:class` con string
ternario, `x-show`) reusa patrones ya validados en producción en este
mismo archivo (el toggle `w-64`/`w-0` original, `$watch` de
`theme_toggle.html`), y la cascada CSS que depende del orden
base-antes-que-`@media` se confirmó leyendo el `tailwind.css` compilado
directamente.

---

### Fase 25 — Chat: burbujas, header y composer ✅

**Objetivo**: es la pantalla que más se usa — aplicar la identidad
nueva a mensajes, header de conversación y composer, resolviendo la
jerarquía apretada que hay hoy.

Tareas:
- [x] `_message.html`: avatar circular por rol (`user`/`bot`, íconos
      nuevos vendoreados) en vez de depender solo de alineación+color;
      mensajes de `tool` con ícono `wrench` en vez del 🔧 emoji.
      Agrupamiento de mensajes consecutivos del mismo rol vía CSS
      (`.msg`/`.msg-<rol>` + selector de hermano adyacente en
      `tailwind/input.css`, sin estado en Python/Alpine — ver el
      comentario ahí) en vez de un `mb-4` fijo por mensaje: un cambio de
      rol se lee como turno nuevo (más aire), varios mensajes seguidos
      del mismo rol (ej. varias tool calls seguidas) quedan agrupados
      (menos aire). `static/js/chat.js` (`appendBubble`/`addToolChip`)
      arma el mismo markup a mano para lo que llega en vivo durante un
      turno — mismas clases, mismos íconos (helper `iconSvg()` nuevo),
      para que no se note la diferencia entre un mensaje recién llegado y
      uno recargado desde el historial.
- [x] Header de `conversation.html` reescrito: título solo en su línea,
      metadata (modelo/costo/compartido) baja a una línea liviana sin
      cajas (separada por "·"), "Compartir"/"Copiar link" quedan como
      botón primario visible con ícono, "Exportar"/"Revocar
      link"/"Borrar" se agruparon en un menú "..." (`x-data="{ open:
      false }"` anidado dentro del `shareWidget` existente —
      `@click.outside`/`Escape` cierran, confirmado que Alpine resuelve
      `revoke()`/`shareUrl` del scope padre desde el hijo sin problema,
      patrón estándar de Alpine).
- [x] Composer: adjuntar (`paperclip`) y enviar (`send`) con íconos
      reales, target táctil de adjuntar a 44px (mismo criterio de la
      Fase 24). Indicador de "enviando" en el botón: 3 puntos con la
      misma animación `.skeleton` que ya usaba la burbuja "pensando" del
      asistente desde `plan.md` Fase 5 (`bg-current`, toma el color de
      texto del botón) — la burbuja "pensando" en sí ya existía de antes
      y no hizo falta tocarla, solo el "…" del botón de enviar.
- [x] Chip de adjunto: ícono `paperclip` reemplaza 📎, gana la misma
      clase `.msg msg-attachment` (espaciado consistente con el resto del
      hilo). Botón de reintentar: ícono `rotate-ccw` reemplaza ↻.
- [x] Estado vacío: `empty.html` y el estado vacío dentro de
      `conversation.html` ganan un ícono `bot` en un círculo arriba del
      copy, y cada prompt sugerido gana un ícono `message-square` (en
      vez de ser solo texto plano en una caja).
- [x] 3 íconos nuevos vendoreados (`user`, `bot`, `ellipsis`), sprite en
      21 íconos total.
- [x] Encontrado y corregido en el camino (no estaba en el plan
      original): `chat/shared_conversation.html` (página pública
      standalone, reusa `_message.html` tal cual) no incluía el sprite de
      íconos — los avatares nuevos hubieran quedado como círculos vacíos
      ahí (`<use>` sin `<symbol>` correspondiente, no tira error pero
      tampoco se ve nada). Se agregó el `{% include
      "partials/icon_sprite.html" %}` a esa página ahora (no se puede
      dejar rota hasta la Fase 26) — el resto del tratamiento visual de
      esa página sigue siendo tarea de esa fase.

**Criterio de aceptación**: probado contra el stack Docker real (build +
up de `chat-web`, Tailwind recompilado) con una conversación real de la
cuenta que ya tenía los 3 roles (usuario, varias tool calls seguidas,
asistente) — confirmado por curl con una sesión real (limpiada al
terminar): el HTML sirve las clases `msg`/`msg-<rol>` esperadas, los 3
avatares (`icon-user`/`icon-bot`/`icon-wrench`), el header con el botón
primario + menú "..." con sus 3 íconos, y el composer con
`paperclip`/`send`. Probado también el estado vacío (conversación nueva
sin mensajes, creada y borrada solo para la prueba) y la página pública
compartida (link de prueba creado y revocado después) — confirmado que
sirve el sprite completo tras el fix. Sin browser real disponible en la
sesión (`claude-in-chrome` no conectado): no se pudo ver la animación de
los 3 puntos, el hover/click del menú "..." en vivo, ni el agrupamiento
de mensajes con los ojos — se verificó en cambio que el CSS del selector
de hermano adyacente compila al valor esperado (`grep` directo sobre el
`tailwind.css` compilado) y que `chat.js` (que no se puede ejecutar sin
navegador) queda con paréntesis/llaves/corchetes balanceados y una
revisión manual línea por línea contra el markup de `_message.html` que
tiene que espejar. No se gastó una llamada real a la API para esta fase:
ningún cambio tocó `chat/views.py`/`chat/agent.py`/el protocolo SSE, solo
el markup/CSS/JS de presentación sobre un flujo que ya funcionaba.

---

### Fase 26 — Documentos, configuración y resto de pantallas ✅

**Objetivo**: extender la identidad nueva al resto de la app para que no
quede la sensación de "dos apps distintas" (chat rediseñado vs. el
resto igual que antes).

Tareas:
- [x] `documents.html` / `_document_card.html` / `_chat_attachment_chip.html`:
      ícono por ESTADO (pendiente/procesando/indexado/error — filtro
      nuevo `ingesta_extras.py::status_icon`, mismo diccionario que
      `status_badge_class` ya tenía por color), con `animate-spin` en el
      de "procesando" (verificado con un objeto `Document` sintético,
      no había ningún documento real en ese estado en la cuenta al
      probar). Tabs de colecciones: ✎/✕ reemplazados por íconos
      `pencil`/`x`. Dropzone: ícono `upload` arriba del texto. Botón
      "Borrar" de cada card e ícono "+ Crear" con íconos reales. Estado
      vacío con ícono `files`.
- [x] `accounts/login.html`: mismo mark de marca que el sidebar (cuadrado
      `bg-primary` + ícono `message-square`) antes de loguearse — los
      inputs ya estaban estilizados consistentemente desde antes
      (`TailwindStyledFormMixin` en `apps/accounts/forms.py`, sin cambios
      acá). `accounts/settings.html`: ícono `trash-2` en el botón
      destructivo de "Zona de peligro".
- [x] `404.html`: ya extendía `base.html` (hereda toda la identidad
      gratis, sidebar incluido) — solo se le agregó un ícono
      `circle-alert` arriba del mensaje, mismo tratamiento que los
      demás estados vacíos/de error de la app. `500.html` (standalone a
      propósito, sin Tailwind ni fuente self-hosted — ver el comentario
      del template): se portó a mano el color de marca violeta como
      variable CSS nueva (`--primary`/`--primary-fg`, claro y oscuro) y
      el botón pasó a usarlo en vez del contraste neutro que tenía —
      es el único token que cambió desde que se escribió esa página, el
      resto de la paleta neutra siguió igual. `shared_conversation.html`
      ya se había arreglado en la Fase 25 (el include del sprite que le
      faltaba).
- [x] `partials/toasts.html`: un toast "success" no tenía ningún color
      propio antes (mismo `border-border`/`bg-card` neutro que cualquier
      otra cosa) — ahora usa el mismo esmeralda que ya usa el badge
      "Indexado" de documentos (reuso del token existente, no un color
      de éxito nuevo e inconsistente), con ícono `check`; "error" suma
      ícono `circle-alert`. Botón de cerrar (✕) reemplazado por el
      ícono `x`.
- [x] 6 íconos nuevos vendoreados (`pencil`, `check`, `clock`, `upload`,
      `loader-circle`, `circle-alert`), sprite en 27 íconos total.

**Criterio de aceptación**: probado contra el stack Docker real (build +
up de `chat-web`, Tailwind recompilado, `animate-spin` confirmado en el
CSS compilado) con una sesión real (limpiada al terminar): `/login/`
(sin sesión) sirve el sprite completo y el mark de marca, `/documentos/`
con datos reales de la cuenta confirma los íconos de estado
(`clock`/`check`/`circle-alert` presentes; `loader-circle` sin ningún
uso real porque no había ningún documento "procesando" en ese momento —
se verificó aparte con `render_to_string` y un objeto `Document`
sintético que el ícono Y la clase `animate-spin` salen juntos),
`pencil`/`x`/`plus`/`upload`/`files`/`trash-2` todos presentes,
`/settings/` con el botón destructivo, `/esto-no-existe/` (404) con el
ícono nuevo. `500.html` verificado con `render_to_string` (sin request,
mismo camino que usa Django de verdad para este handler) — confirma que
ambos valores de `--primary` (claro/oscuro) están en el HTML. Toasts
verificados a nivel de markup servido (`item.type !== 'error'`/`===
'error'` con sus íconos respectivos, botón de cerrar con ícono `x`) —
no se pudo ver la animación de entrada/salida ni disparar uno real sin
browser (`claude-in-chrome` no conectado en la sesión).

---

### Fase 27 — Microinteracciones y pulido final responsive ✅

**Objetivo**: última pasada, después de que todas las pantallas ya usan
la identidad nueva — detalles de movimiento/feedback y una verificación
mobile completa (no solo el sidebar de la Fase 24).

Tareas:
- [x] Transición de entrada (`msg-enter`, `tailwind/input.css`, fade +
      slide de 4px, 0.2s) para mensajes nuevos en el chat — puesta a
      mano SOLO en `chat.js` (`appendBubble`/`addToolChip`/
      `appendAttachmentChip`), nunca en `_message.html`: si el historial
      completo hiciera fade-in junto con la carga de la página se vería
      como un flash, no como una entrada. El chip de adjunto necesitó
      cuidado extra: `_chat_attachment_chip.html` lo reusa también htmx
      para refrescar un chip YA insertado cada 2s (polling
      pending/processing) — si la clase viniera en el HTML del server en
      vez de agregarse a mano tras el primer insert, cada refresh
      reiniciaría la animación.
- [x] Feedback de click/press: regla CSS global sobre `<button>` (cubre
      la enorme mayoría de los controles reales sin tocar un solo
      template — enviar, adjuntar, reintentar, compartir, el menú "...",
      borrar/renombrar, toggles, forms). Para los pocos `<a>`/`<label>`
      que se ven y actúan como botón (ítem de conversación del sidebar,
      resultado de búsqueda, "Documentos", "Configuración", "Exportar",
      "Elegir archivos", tabs de colecciones, "Volver al chat" de 404) se
      optó a mano con una clase nueva `.press` — a propósito NO un
      selector global sobre `<a>`, que agarraría también los links
      dentro de una respuesta en markdown (`.markdown-body a`), donde
      "apachurrar" el texto entero de un link con `transform: scale()`
      se ve raro. Ambos (`button`/`.press`) respetan
      `prefers-reduced-motion: reduce` (igual que `msg-enter`).
- [x] Pasada mobile — 3 fixes concretos, todos verificables sin
      necesidad de un dispositivo real:
      1. Auto-zoom de Safari/iOS al enfocar un input: cualquier
         `<input>`/`<textarea>`/`<select>` con font-size computado menor
         a 16px lo dispara — casi todos los inputs de la app usan
         `text-sm` (14px). Regla CSS global (`@media (max-width:
         39.9975rem)`, mismo breakpoint `sm` de Tailwind) sube a 16px
         solo por debajo de ese ancho, sin tocar cada input a mano ni
         agrandarlos en desktop.
      2. Composer tapado por el teclado virtual: se agregó
         `interactive-widget=resizes-content` al `<meta viewport>` de
         `base.html` y las 3 páginas standalone con inputs
         (`login.html`, `shared_conversation.html`, `500.html`) —
         atributo del CSS Viewport spec que le pide al navegador
         redimensionar el viewport de layout cuando aparece el teclado
         en vez de superponerlo; aditivo, un navegador que no lo conoce
         lo ignora sin romper nada.
      3. Encontrado en el camino (no estaba en el plan original):
         burbujas de mensaje sin `min-w-0` — un flex item no encoge por
         debajo del ancho intrínseco de su contenido por default, así
         que un mensaje con una URL/hash larga sin espacios se salía del
         viewport en mobile pese al `max-w-2xl` (que solo pone un techo,
         no fuerza a encoger). Agregado `min-w-0 break-words` a ambas
         burbujas (usuario/asistente) en `_message.html` y espejado en
         `chat.js::appendBubble`.
      4. Cards de documentos: ya quedaban en una columna en mobile sin
         cambios (`grid` sin `grid-cols-*` en la base, solo
         `sm:grid-cols-2 lg:grid-cols-3` — el default de CSS Grid sin
         columnas explícitas ya es una sola columna) — confirmado, no
         hizo falta tocar nada ahí.
- [x] Contraste del violeta revisado con la fórmula real de luminancia
      WCAG (no estimado) contra `--background` en ambos modos —los dos
      pasan AA: 5.70:1 en claro, 6.56:1 en oscuro (mismos números que ya
      había calculado la Fase 23 para el texto sobre el botón sólido: el
      ratio es simétrico, da igual qué lado se llame "texto" y cuál
      "fondo"). No hizo falta ajustar el tono. La comparación contra
      `--foreground` que pedía el enunciado original del plan no
      corresponde a ningún uso real en la app (el violeta nunca se
      renderiza como texto plano sobre `--foreground` ni al revés —
      confirmado que no hay ningún `text-primary` sin el sufijo
      `-foreground` en ningún template) — se documenta la comparación
      real que sí aplica (`--background`) en vez de una que no representa
      nada visible.

**Criterio de aceptación**: probado contra el stack Docker real (build +
up de `chat-web`, Tailwind recompilado) con una sesión real (limpiada al
terminar): confirmado por curl que `interactive-widget=resizes-content`
está en `/login/` y `/chat/<id>/`, que `.press` aparece en las pantallas
esperadas (sidebar, header de conversación, documentos), que
`min-w-0 max-w-2xl break-words` está en las burbujas servidas, y que
`font-size:16px` bajo el media query mobile está en el `tailwind.css`
servido. `animate-spin`/`@keyframes msg-enter`/la regla de `.press`
confirmadas en el CSS compilado con los valores esperados. Sin browser
real disponible en la sesión (`claude-in-chrome` no conectado): no se
pudo ver la animación de entrada de un mensaje, el "apachurrado" al
tocar un botón, ni probar en un dispositivo real que el teclado virtual
ya no tapa el composer — estos 3 quedan verificados por construcción
(mecanismos CSS/meta-tag estándar y bien documentados, no por
inspección visual) en vez de confirmados con los ojos.

Con esta fase se completa **todo `plan-v4.md`** (Fases 23-27) — el
rediseño visual de la interfaz que pidió el usuario está terminado.

---

Fuera de alcance de este plan (a propósito, por la decisión de "sin
reescritura de layout/flujos"): reordenar el layout de 2 columnas,
cambiar cómo funciona cualquier flujo existente (compartir, adjuntar,
reintentar, etc.), o agregar pantallas/funcionalidad nueva — eso sigue
siendo terreno de `plan-v3.md` (Fase 19, Google Drive) o de un
`plan-v5.md` futuro si surge algo nuevo.
