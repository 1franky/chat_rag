// Drag & drop + subida con barra de progreso por archivo (plan.md, Fase 3).
// Usa XMLHttpRequest (no fetch) porque es la única API con eventos de
// progreso de subida (`upload.onprogress`).
function documentsPage() {
  return {
    dragging: false,
    uploading: [],

    handleFiles(fileList) {
      Array.from(fileList).forEach((file) => this.uploadFile(file));
    },

    uploadFile(file) {
      const item = {
        key: `${file.name}-${Date.now()}-${Math.random()}`,
        name: file.name,
        progress: 0,
        error: null,
      };
      this.uploading.push(item);

      const formData = new FormData();
      formData.append('file', file);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/documentos/subir/');
      xhr.setRequestHeader('X-CSRFToken', getCsrfToken());

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          item.progress = Math.round((event.loaded / event.total) * 100);
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          item.progress = 100;
          try {
            const data = JSON.parse(xhr.responseText);
            this.appendDocumentCard(data.card_html);
          } catch (e) {
            item.error = 'Respuesta inesperada del servidor';
          }
          setTimeout(() => {
            this.uploading = this.uploading.filter((u) => u.key !== item.key);
          }, 1200);
        } else {
          item.error = this.parseError(xhr) || `Error (HTTP ${xhr.status})`;
        }
      });

      xhr.addEventListener('error', () => {
        item.error = 'No se pudo conectar con el servidor';
      });

      xhr.send(formData);
    },

    parseError(xhr) {
      try {
        return JSON.parse(xhr.responseText).error;
      } catch (e) {
        return null;
      }
    },

    appendDocumentCard(html) {
      const grid = document.getElementById('documents-grid');
      const empty = grid.querySelector('[data-empty-state]');
      if (empty) empty.remove();
      grid.insertAdjacentHTML('afterbegin', html);
      if (window.htmx) {
        htmx.process(grid);
      }
    },
  };
}
