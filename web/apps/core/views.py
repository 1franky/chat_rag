from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone


def healthz(request: HttpRequest) -> HttpResponse:
    """Endpoint de healthcheck (sin auth). Usado por el healthcheck de chat-web en compose.yaml."""
    return HttpResponse("ok", content_type="text/plain")


def download_report(request: HttpRequest, filename: str) -> HttpResponse:
    """`/reportes/<filename>`: sirve un archivo generado por las tools
    `report_*` de chat-rag-mcp (plan-v3.md, Fase 20). Sin modelo en Django
    (sin tracking en DB en este v1, ver la nota de arquitectura del plan)
    — el nombre de archivo (`<uuid4>.<ext>`, armado por
    `rag_shared/reports.py`) es la única referencia.

    Sin @login_required explícito, mismo criterio que `metrics`:
    LoginRequiredMiddleware ya protege todo lo que no esté en
    EXEMPT_PATH_PREFIXES, y este path no está ahí.
    """
    path = (settings.REPORTS_DIR / filename).resolve()
    # Defensa contra path traversal: aunque el <str:filename> de la URL no
    # deja pasar "/" (así que un ".." solo no alcanzaría para escapar del
    # directorio), resolver la ruta y confirmar que sigue adentro de
    # REPORTS_DIR no depende de esa garantía del router.
    if settings.REPORTS_DIR.resolve() not in path.parents or not path.is_file():
        raise Http404
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


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
