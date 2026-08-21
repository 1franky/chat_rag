// Store global de toasts (Alpine), para feedback de éxito/error de acciones
// server-side (mensajes de Django) o disparadas desde JS (plan.md, Fase 5).
document.addEventListener('alpine:init', () => {
  Alpine.store('toast', {
    items: [],
    nextId: 1,

    push(text, type = 'success', timeout = 4000) {
      const id = this.nextId++;
      this.items.push({ id, text, type });
      if (timeout) {
        setTimeout(() => this.remove(id), timeout);
      }
    },

    remove(id) {
      this.items = this.items.filter((item) => item.id !== id);
    },
  });
});
