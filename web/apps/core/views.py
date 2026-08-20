from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


def healthz(request: HttpRequest) -> HttpResponse:
    """Endpoint de healthcheck (sin auth). Usado por el healthcheck de chat-web en compose.yaml."""
    return HttpResponse("ok", content_type="text/plain")


def root(request: HttpRequest) -> HttpResponse:
    """`/`: redirige a `/chat/` (LoginRequiredMiddleware ya se encarga de
    mandar a `/login/` si no hay sesión iniciada)."""
    return redirect("chat:placeholder")
