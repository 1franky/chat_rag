from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

import structlog
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import agent
from .models import Conversation, Message, SharedLink

logger = structlog.get_logger()

SUGGESTED_PROMPTS = [
    "¿Qué documentos tienes indexados ahora mismo?",
    "Resume los puntos clave de mis documentos más recientes",
    "Ayúdame a redactar un resumen ejecutivo con base en mis documentos",
    "Explícame, paso a paso, cómo funciona este proyecto",
]


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """`/chat/`: a la conversación más reciente, o al estado vacío si no hay ninguna."""
    conversation = Conversation.objects.filter(user=request.user).first()
    if conversation is None:
        return render(request, "chat/empty.html", {"suggested_prompts": SUGGESTED_PROMPTS})
    return redirect("chat:detail", conversation_id=conversation.id)


@login_required
@require_POST
def new_conversation(request: HttpRequest) -> HttpResponse:
    # POST arbitrario (no viene de un <select> siempre, ej. el botón rápido
    # del sidebar no lo manda): default a Sonnet si falta o no es válido,
    # en vez de que un valor pisoteado tire 500 (plan-v2.md, Fase 13).
    model = request.POST.get("model", "")
    if model not in Conversation.Model.values:
        model = Conversation.Model.SONNET
    conversation = Conversation.objects.create(user=request.user, model=model)
    detail_url = reverse("chat:detail", args=[conversation.id])

    # Prompt sugerido del estado vacío (chat/empty.html): se manda como
    # querystring y el JS de la página lo autoenvía al cargar (ver
    # static/js/chat.js) — reusa el mismo flujo de streaming que un mensaje
    # tipeado a mano en vez de duplicar lógica de creación de mensajes acá.
    prompt = request.POST.get("prompt", "").strip()
    if prompt:
        detail_url = f"{detail_url}?{urlencode({'draft': prompt})}"

    return redirect(detail_url)


@login_required
def conversation_detail(request: HttpRequest, conversation_id) -> HttpResponse:
    conversation = _get_conversation_or_404(request, conversation_id)
    chat_messages = conversation.messages.all()
    active_link = conversation.shared_links.filter(revoked_at__isnull=True).first()
    return render(
        request,
        "chat/conversation.html",
        {
            "conversation": conversation,
            "chat_messages": chat_messages,
            # Solo se usan si chat_messages está vacío (conversación recién
            # creada) — ver el bloque de estado vacío en conversation.html.
            "suggested_prompts": SUGGESTED_PROMPTS,
            "share_url": _share_url(request, active_link.token) if active_link else None,
        },
    )


async def stream_message(request: HttpRequest, conversation_id) -> HttpResponse:
    # Sin @login_required/@require_POST a propósito: en esta versión de
    # Django esos decoradores no son async-aware — envuelven la vista sin
    # detectar que es una coroutine y devuelven la coroutine sin awaitear
    # ("didn't return an HttpResponse object. It returned an unawaited
    # coroutine instead"). Se resuelve a mano, con `auser()` (accessor
    # async-safe de Django) para no disparar una query sync dentro del
    # event loop.
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({"error": "No autenticado"}, status=401)

    try:
        conversation = await Conversation.objects.aget(pk=conversation_id, user=user)
    except Conversation.DoesNotExist:
        return JsonResponse({"error": "Conversación no encontrada"}, status=404)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Body inválido"}, status=400)

    user_text = (body.get("message") or "").strip()
    if not user_text:
        return JsonResponse({"error": "Mensaje vacío"}, status=400)

    await Message.objects.acreate(conversation=conversation, role=Message.Role.USER, content=user_text)
    if not conversation.title:
        await conversation.aset_title_from_message(user_text)

    async def event_stream():
        assistant_text = ""
        had_error = False
        # tool_use_id -> Message, para completar tool_result cuando llegue.
        pending_tool_messages: dict[str, Message] = {}

        await logger.ainfo(
            "chat_message_sent",
            conversation_id=str(conversation.id),
            message_length=len(user_text),
            model=conversation.model,
        )

        try:
            async for event in agent.stream_reply(conversation.agent_session_id, user_text, conversation.model):
                event_type = event["type"]

                if event_type == "token":
                    yield _sse({"type": "token", "text": event["text"]})

                elif event_type == "text_block":
                    assistant_text += event["text"]

                elif event_type == "tool_use":
                    tool_message = await Message.objects.acreate(
                        conversation=conversation,
                        role=Message.Role.TOOL,
                        tool_name=event["name"],
                        tool_args=event["input"],
                    )
                    pending_tool_messages[event["id"]] = tool_message
                    yield _sse(
                        {"type": "tool_use", "id": event["id"], "name": event["name"], "input": event["input"]}
                    )

                elif event_type == "tool_result":
                    tool_message = pending_tool_messages.get(event["tool_use_id"])
                    if tool_message is not None:
                        tool_message.tool_result = event["content"]
                        tool_message.is_error = event["is_error"]
                        await tool_message.asave(update_fields=["tool_result", "is_error"])
                    yield _sse(
                        {
                            "type": "tool_result",
                            "tool_use_id": event["tool_use_id"],
                            "is_error": event["is_error"],
                        }
                    )

                elif event_type == "error":
                    had_error = True
                    yield _sse({"type": "error", "error": event["error"]})

                elif event_type == "done":
                    if event["session_id"]:
                        conversation.agent_session_id = event["session_id"]
                        await conversation.asave(update_fields=["agent_session_id", "updated_at"])
                    await logger.ainfo(
                        "chat_turn_done",
                        conversation_id=str(conversation.id),
                        model=conversation.model,
                        resolved_model=event["resolved_model"],
                    )
                    had_error = had_error or event["is_error"]
                    if event["is_error"] and event["error"]:
                        yield _sse({"type": "error", "error": event["error"]})

        except Exception as exc:  # noqa: BLE001 — se lo mostramos al usuario y cerramos el stream
            had_error = True
            await logger.aerror("chat_stream_failed", conversation_id=str(conversation.id), exc_info=exc)
            yield _sse({"type": "error", "error": str(exc)})

        if assistant_text:
            await Message.objects.acreate(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=assistant_text,
                is_error=had_error,
            )

        yield _sse({"type": "done"})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@login_required
@require_POST
def delete_conversation(request: HttpRequest, conversation_id) -> HttpResponse:
    conversation = _get_conversation_or_404(request, conversation_id)
    conversation.delete()
    logger.info("conversation_deleted", conversation_id=str(conversation_id))

    # Borrado desde el ícono del sidebar (static/js/sidebar.js, plan-v2.md
    # Fase 8): 204 sin body — el JS decide ahí mismo si hace falta navegar
    # (borraste la conversación que tenías abierta) o solo sacar el <a> del
    # sidebar (borraste otra), sin el redirect a chat:home de siempre, que
    # sacaría al usuario de donde estaba para nada.
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return HttpResponse(status=204)

    messages.success(request, "Conversación borrada.")
    return redirect("chat:home")


@login_required
@require_GET
def export_conversation(request: HttpRequest, conversation_id) -> HttpResponse:
    conversation = _get_conversation_or_404(request, conversation_id)
    lines = [f"# {conversation.title or 'Conversación'}", ""]
    for message in conversation.messages.exclude(role=Message.Role.TOOL):
        who = "Yo" if message.role == Message.Role.USER else "Claude"
        lines.append(f"**{who}** ({message.created_at:%Y-%m-%d %H:%M}):")
        lines.append("")
        lines.append(message.content)
        lines.append("")

    response = HttpResponse("\n".join(lines), content_type="text/markdown; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{conversation.id}.md"'
    return response


@login_required
@require_POST
def share_conversation(request: HttpRequest, conversation_id) -> HttpResponse:
    """Crea (o reusa, si ya hay uno activo) el link de solo lectura de esta
    conversación — botón "Compartir" de conversation.html."""
    conversation = _get_conversation_or_404(request, conversation_id)
    link = conversation.shared_links.filter(revoked_at__isnull=True).first()
    if link is None:
        link = SharedLink.objects.create(conversation=conversation)
        logger.info("shared_link_created", conversation_id=str(conversation_id))
    return JsonResponse({"url": _share_url(request, link.token)})


@login_required
@require_POST
def revoke_share(request: HttpRequest, conversation_id) -> HttpResponse:
    """Revoca el link activo de esta conversación, si hay uno — botón
    "Revocar" de conversation.html. Idempotente: revocar sin que haya un
    link activo no es un error, simplemente no hace nada."""
    conversation = _get_conversation_or_404(request, conversation_id)
    updated = conversation.shared_links.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    if updated:
        logger.info("shared_link_revoked", conversation_id=str(conversation_id))
    return HttpResponse(status=204)


@require_GET
def shared_conversation(request: HttpRequest, token: str) -> HttpResponse:
    """Vista pública de solo lectura en `/compartido/<token>/` (plan-v2.md,
    Fase 11) — sin `@login_required` a propósito (ver
    apps/core/middlewares.py::EXEMPT_PATH_PREFIXES, que exime este prefijo
    del login forzado). 404 tanto si el token no existe como si el link ya
    fue revocado — no hay forma de distinguir "no existe" de "revocado"
    desde afuera, a propósito.

    Excluye mensajes de tool (mismo criterio que export_conversation): el
    contenido de un tool_result puede incluir fragmentos crudos de
    documentos propios — no algo para exponer en un link que se puede
    reenviar a cualquiera.
    """
    link = get_object_or_404(SharedLink, token=token, revoked_at__isnull=True)
    conversation = link.conversation
    chat_messages = conversation.messages.exclude(role=Message.Role.TOOL)
    return render(
        request,
        "chat/shared_conversation.html",
        {"conversation": conversation, "chat_messages": chat_messages},
    )


def _share_url(request: HttpRequest, token: str) -> str:
    path = reverse("shared_conversation", args=[token])
    if settings.PUBLIC_BASE_URL:
        return f"{settings.PUBLIC_BASE_URL}{path}"
    return request.build_absolute_uri(path)


def _get_conversation_or_404(request: HttpRequest, conversation_id):
    try:
        return Conversation.objects.get(pk=conversation_id, user=request.user)
    except Conversation.DoesNotExist:
        raise Http404 from None


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def grouped_conversations(user) -> dict[str, list[Conversation]]:
    """Conversaciones del usuario agrupadas por fecha (hoy/ayer/últimos 7 días/más antiguo),
    para el sidebar (plan.md, Fase 4)."""
    today = timezone.localdate()
    groups: dict[str, list[Conversation]] = defaultdict(list)
    for conversation in Conversation.objects.filter(user=user):
        day = timezone.localtime(conversation.updated_at).date()
        if day == today:
            key = "Hoy"
        elif day == today - timedelta(days=1):
            key = "Ayer"
        elif day >= today - timedelta(days=7):
            key = "Últimos 7 días"
        else:
            key = "Más antiguo"
        groups[key].append(conversation)
    return {label: groups[label] for label in ("Hoy", "Ayer", "Últimos 7 días", "Más antiguo") if groups[label]}
