from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone


def healthz(request: HttpRequest) -> HttpResponse:
    """Endpoint de healthcheck (sin auth). Usado por el healthcheck de chat-web en compose.yaml."""
    return HttpResponse("ok", content_type="text/plain")


def root(request: HttpRequest) -> HttpResponse:
    """`/`: redirige a `/chat/` (LoginRequiredMiddleware ya se encarga de
    mandar a `/login/` si no hay sesión iniciada)."""
    return redirect("chat:home")


def metrics(request: HttpRequest) -> JsonResponse:
    """`/metrics`: contador básico de conversaciones, docs indexados y
    errores de las últimas 24h, para vista interna (plan.md, Fase 7).

    Sin @login_required explícito: LoginRequiredMiddleware ya protege todo
    lo que no esté en EXEMPT_PATH_PREFIXES (apps/core/middlewares.py), y
    /metrics no está ahí — no es un endpoint público.
    """
    # Imports acá adentro (no al tope del módulo) para no crear una
    # dependencia de import-time entre apps.core y apps.chat/apps.ingesta —
    # las tres son independientes entre sí salvo por esta vista.
    from apps.chat.models import Conversation, Message
    from apps.ingesta.models import Document

    since = timezone.now() - timezone.timedelta(hours=24)

    documents_by_status = dict(
        Document.objects.active().values("status").annotate(count=Count("id")).values_list("status", "count")
    )

    return JsonResponse(
        {
            "conversations": {
                "total": Conversation.objects.count(),
                "last_24h": Conversation.objects.filter(created_at__gte=since).count(),
            },
            "documents": {
                "total_active": Document.objects.active().count(),
                "by_status": documents_by_status,
            },
            "errors_last_24h": {
                "chat_messages": Message.objects.filter(is_error=True, created_at__gte=since).count(),
                "documents": Document.objects.filter(status=Document.Status.FAILED, uploaded_at__gte=since).count(),
            },
        }
    )
