// Borrar una conversación desde el ícono del sidebar sin tener que abrirla
// primero (plan-v2.md, Fase 8). Usa fetch en vez de un submit normal: si la
// conversación borrada es OTRA distinta de la que se tiene abierta, no hace
// falta recargar toda la página — alcanza con sacar el <a> del sidebar.
function sidebarConversationItem(conversationId, deleteUrl) {
  return {
    async deleteConversation() {
      if (!confirm('¿Borrar esta conversación?')) return;

      let response;
      try {
        response = await fetch(deleteUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
        });
      } catch {
        Alpine.store('toast').push('No se pudo borrar la conversación.', 'error');
        return;
      }
      if (!response.ok) {
        Alpine.store('toast').push('No se pudo borrar la conversación.', 'error');
        return;
      }

      // La conversación borrada era la que estaba abierta: no tiene sentido
      // seguir mostrándola, hay que navegar a otro lado.
      const openConversation = document.querySelector('[data-conversation-id]');
      if (openConversation && openConversation.dataset.conversationId === conversationId) {
        window.location.href = document.body.dataset.chatHomeUrl;
        return;
      }

      // $root (no $el): $el es el nodo donde Alpine evaluó la expresión —
      // acá, el <button> mismo, no el <div x-data> que envuelve todo el
      // item — así que $el.remove() solo sacaba el botón y dejaba un item
      // fantasma (el <a> con el título) en el sidebar.
      this.$root.remove();
      Alpine.store('toast').push('Conversación borrada.', 'success');
    },
  };
}
