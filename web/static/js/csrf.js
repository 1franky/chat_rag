// Token CSRF para requests JS (fetch/XHR/htmx). Ver el comentario en
// templates/base.html: CSRF_COOKIE_HTTPONLY=True le saca a JS la lectura
// directa de la cookie, así que el token viaja en un <meta>.
function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

if (window.htmx) {
  document.body.addEventListener('htmx:configRequest', (event) => {
    event.detail.headers['X-CSRFToken'] = getCsrfToken();
  });
}
