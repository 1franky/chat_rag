// Conversación compartida de solo lectura (plan-v2.md, Fase 11): renderiza
// el markdown de los mensajes del asistente al cargar. Misma lógica
// idempotente que renderMarkdown() en static/js/chat.js (guardar el
// markdown crudo en data-raw ANTES de mutar innerHTML — si esto corriera
// dos veces sobre el mismo elemento, una segunda pasada leyendo
// el HTML ya renderizado aplanaría todo el formato), duplicada a propósito
// en vez de compartida: esta página pública no carga Alpine.js ni depende
// de nada del composer/streaming de la conversación privada, para mantener
// su JS al mínimo indispensable.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.markdown-body:not([data-rendered])').forEach((el) => {
    try {
      if (!el.dataset.raw) {
        el.dataset.raw = el.textContent;
      }
      el.innerHTML = marked.parse(el.dataset.raw);
      el.dataset.rendered = 'true';
      el.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
    } catch (renderError) {
      console.error('No se pudo renderizar markdown:', renderError);
    }
  });
});
