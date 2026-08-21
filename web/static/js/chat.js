// Chat: streaming SSE-sobre-fetch (no se puede usar EventSource nativo
// porque necesitamos mandar un POST con body — EventSource solo hace GET),
// render de markdown post-stream con marked.js + highlight.js.

function chatPage(conversationId) {
  return {
    draft: '',
    sending: false,
    errorMessage: '',

    init() {
      this.renderExistingMarkdown();
      this.scrollToBottom();
      this.$nextTick(() => this.$refs.input?.focus());

      window.addEventListener('keydown', (event) => {
        const mod = event.metaKey || event.ctrlKey;
        const key = event.key.toLowerCase();
        if (mod && key === 'k') {
          event.preventDefault();
          document.querySelector('aside form[action$="/nueva/"]')?.requestSubmit();
        } else if (mod && key === '/') {
          event.preventDefault();
          this.$refs.input?.focus();
        } else if (mod && key === 'enter' && document.activeElement === this.$refs.input) {
          // Enter solo (sin Shift) ya envía — este es un atajo alternativo
          // explícito (plan.md, Fase 5) para quien prefiere Cmd/Ctrl+Enter.
          event.preventDefault();
          this.send();
        }
      });

      // Prompt sugerido desde el estado vacío (chat/empty.html): la vista
      // `new_conversation` redirige acá con `?draft=...` en vez de crear el
      // mensaje server-side, para reusar el mismo flujo de streaming que un
      // mensaje tipeado a mano.
      const params = new URLSearchParams(window.location.search);
      const draftFromEmptyState = params.get('draft');
      if (draftFromEmptyState) {
        history.replaceState(null, '', window.location.pathname);
        this.draft = draftFromEmptyState;
        this.$nextTick(() => this.send());
      }
    },

    renderExistingMarkdown() {
      // :not([data-rendered]) — ver el comentario en renderMarkdown() sobre
      // por qué esto tiene que ser idempotente.
      this.$refs.messageList.querySelectorAll('.markdown-body:not([data-rendered])').forEach((el) => {
        try {
          this.renderMarkdown(el);
        } catch (renderError) {
          console.error('No se pudo renderizar markdown:', renderError);
        }
      });
    },

    renderMarkdown(el) {
      // Guardar el markdown crudo ANTES de tocar innerHTML (si todavía no
      // está guardado) es necesario para que esto sea idempotente: si por
      // lo que sea se llama dos veces sobre el mismo elemento, una segunda
      // pasada que lea `el.textContent` ya NO vería el markdown crudo, sino
      // el texto plano del HTML ya renderizado (sin los `**`/`` ` ``/etc.,
      // ya convertidos a <strong>/<code>/<ol> reales) — y volver a mandar
      // ESO a marked.parse() aplana todo el formato a un solo <p>. Con el
      // raw ya guardado en dataset.raw, una repetición es un no-op inocuo
      // (mismo resultado), en vez de destructiva.
      if (!el.dataset.raw) {
        el.dataset.raw = el.textContent;
      }
      el.innerHTML = marked.parse(el.dataset.raw);
      el.dataset.rendered = 'true';
      el.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
        this.addCopyButton(block);
      });
    },

    addCopyButton(codeBlock) {
      const pre = codeBlock.parentElement;
      if (!pre || pre.querySelector('.copy-btn')) return;
      pre.classList.add('relative');
      // El tema de highlight.js le pone padding: 1em a <code>, pero el
      // botón se posiciona relativo a <pre> (sin padding propio) — sin
      // este espacio extra arriba, el botón queda encima de la primera
      // línea de código y la tapa. Inline style para no pelear con la
      // especificidad de highlight-github-dark.min.css.
      codeBlock.style.paddingTop = '2.75rem';
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Copiar';
      // Siempre visible (no group-hover): Tailwind envuelve `group-hover:`
      // en `@media (hover: hover)`, así que en touch (sin mouse) esa media
      // query nunca matchea y el botón quedaba `hidden` para siempre — no
      // hay forma de "hacer hover" con el dedo.
      // select-none: el botón es el último hijo de <pre> en el DOM (aunque
      // visualmente queda arriba por position:absolute) — sin esto, una
      // selección manual de todo el bloque de código arrastra "Copiar" al
      // final del texto copiado.
      button.className =
        'copy-btn absolute right-2 top-2 rounded-md bg-slate-700 px-2 py-1 text-xs text-white select-none hover:bg-slate-600';
      button.addEventListener('click', () => {
        // textContent en vez de innerText: no depende de layout/render
        // (innerText es sensible a CSS y puede comportarse distinto entre
        // navegadores), así que es más confiable para capturar TODO el
        // código, incluida la primera línea.
        navigator.clipboard.writeText(codeBlock.textContent).then(() => {
          button.textContent = '¡Listo!';
          setTimeout(() => (button.textContent = 'Copiar'), 1500);
        });
      });
      pre.appendChild(button);
    },

    autoResize() {
      const el = this.$refs.input;
      el.style.height = 'auto';
      el.style.height = `${el.scrollHeight}px`;
    },

    scrollToBottom() {
      this.$nextTick(() => {
        this.$refs.messageList.scrollTop = this.$refs.messageList.scrollHeight;
      });
    },

    appendBubble(role) {
      const wrapper = document.createElement('div');
      wrapper.className = `mb-4 flex ${role === 'user' ? 'justify-end' : 'justify-start'}`;
      const bubble = document.createElement('div');
      bubble.className =
        role === 'user'
          ? 'max-w-2xl whitespace-pre-wrap rounded-lg bg-primary px-4 py-2 text-primary-foreground'
          : 'markdown-body max-w-2xl whitespace-pre-wrap rounded-lg bg-muted px-4 py-2';
      if (role === 'assistant') {
        // Skeleton loader ("pensando…") mientras se espera el primer token
        // del stream (plan.md, Fase 5) — `send()` lo saca en cuanto llega
        // el primer chunk de texto.
        bubble.innerHTML =
          '<span class="inline-flex gap-1" data-thinking>' +
          '<span class="skeleton h-2 w-2 rounded-full bg-muted-foreground"></span>' +
          '<span class="skeleton h-2 w-2 rounded-full bg-muted-foreground" style="animation-delay: 0.2s"></span>' +
          '<span class="skeleton h-2 w-2 rounded-full bg-muted-foreground" style="animation-delay: 0.4s"></span>' +
          '</span>';
      }
      wrapper.appendChild(bubble);
      this.$refs.messageList.appendChild(wrapper);
      return bubble;
    },

    addToolChip(data) {
      const wrapper = document.createElement('div');
      wrapper.className = 'mb-4 flex justify-start';
      wrapper.dataset.toolUseId = data.id;
      const details = document.createElement('details');
      details.className = 'max-w-2xl rounded-md border border-border px-3 py-2 text-sm';
      const summary = document.createElement('summary');
      summary.className = 'cursor-pointer select-none text-muted-foreground';
      summary.textContent = `🔧 ${data.name}`;
      const args = document.createElement('pre');
      args.className = 'mt-2 overflow-x-auto text-xs';
      args.textContent = JSON.stringify(data.input, null, 2);
      details.appendChild(summary);
      details.appendChild(args);
      wrapper.appendChild(details);
      this.$refs.messageList.appendChild(wrapper);
      this.scrollToBottom();
    },

    updateToolChip(data) {
      const wrapper = this.$refs.messageList.querySelector(`[data-tool-use-id="${CSS.escape(data.tool_use_id)}"]`);
      if (!wrapper) return;
      const summary = wrapper.querySelector('summary');
      if (data.is_error) {
        summary.innerHTML += ' <span class="text-destructive">· error</span>';
      }
    },

    async send() {
      const text = this.draft.trim();
      if (!text || this.sending) return;

      this.sending = true;
      this.errorMessage = '';
      this.appendBubble('user').textContent = text;
      this.draft = '';
      this.$nextTick(() => this.autoResize());
      this.scrollToBottom();

      const assistantBubble = this.appendBubble('assistant');
      let assistantText = '';

      try {
        const response = await fetch(`/chat/${conversationId}/stream/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
          body: JSON.stringify({ message: text }),
        });

        if (!response.ok || !response.body) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || `Error del servidor (HTTP ${response.status})`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split('\n\n');
          buffer = chunks.pop();
          for (const chunk of chunks) {
            if (!chunk.startsWith('data: ')) continue;
            const data = JSON.parse(chunk.slice(6));
            if (data.type === 'token') {
              assistantText += data.text;
              assistantBubble.textContent = assistantText;
              this.scrollToBottom();
            } else if (data.type === 'tool_use') {
              this.addToolChip(data);
            } else if (data.type === 'tool_result') {
              this.updateToolChip(data);
            } else if (data.type === 'error') {
              this.errorMessage = data.error || 'Algo salió mal.';
            }
          }
        }
      } catch (error) {
        this.errorMessage = error.message || 'No se pudo conectar con el servidor.';
      }

      if (assistantText) {
        assistantBubble.dataset.raw = assistantText;
        // El render de markdown/highlight puede fallar sin tumbar el chat:
        // si tira acá, igual queremos liberar `sending` y dejar el mensaje
        // legible (aunque sea en texto plano) en vez de trabar el input.
        try {
          this.renderMarkdown(assistantBubble);
        } catch (renderError) {
          console.error('No se pudo renderizar markdown:', renderError);
        }
      } else {
        assistantBubble.parentElement.remove();
      }
      this.scrollToBottom();
      this.sending = false;
      this.$nextTick(() => this.$refs.input?.focus());

      // El título se autogenera en el server con el primer mensaje
      // (Conversation.set_title_from_message, trunca a 60 caracteres) — se
      // refleja acá al toque para no esperar a la próxima navegación.
      this.updateSidebarTitle(text);
    },

    updateSidebarTitle(firstMessage) {
      const link = document.querySelector(`aside a[href$="/${conversationId}/"]`);
      if (!link || link.textContent.trim() !== 'Sin título') return;
      const collapsed = firstMessage.split(/\s+/).join(' ');
      const title = collapsed.length > 60 ? `${collapsed.slice(0, 60)}…` : collapsed;
      link.textContent = title;
      link.title = title;
      document.title = `${title} · chat_rag`;
    },
  };
}
