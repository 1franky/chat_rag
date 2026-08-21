from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse

# Prefijos de URL accesibles sin sesión iniciada. Uso 100% personal: todo lo
# demás requiere login (no hay vista de registro).
EXEMPT_PATH_PREFIXES = (
    "/login/",
    "/static/",
    "/healthz",
    # Vista pública de solo lectura de una conversación compartida (Fase 11,
    # plan-v2.md) — la vista misma controla el acceso por token, no por
    # sesión.
    "/compartido/",
)


class LoginRequiredMiddleware:
    """Fuerza login en todas las URLs salvo EXEMPT_PATH_PREFIXES."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated and not self._is_exempt(request.path):
            login_url = getattr(settings, "LOGIN_URL", reverse("accounts:login"))
            return redirect_to_login(request.get_full_path(), login_url=login_url)
        return self.get_response(request)

    @staticmethod
    def _is_exempt(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)
