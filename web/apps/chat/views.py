from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseNotAllowed,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import agent
from .models import Conversation, Message


@login_required
def home(request: HttpRequest) -> HttpResponse:
    """`/chat/`: a la conversación más reciente, o al estado vacío si no hay ninguna."""
    conversation = Conversation.objects.filter(user=request.user).first()
    if conversation is None:
        return render(request, "chat/empty.html")
    return redirect("chat:detail", conversation_id=conversation.id)


@login_required
@require_POST
def new_conversation(request: HttpRequest) -> HttpResponse:
    conversation = Conversation.objects.create(user=request.user)
    return redirect("chat:detail", conversation_id=conversation.id)


@login_required
def conversation_detail(request: HttpRequest, conversation_id) -> HttpResponse:
    conversation = _get_conversation_or_404(request, conversation_id)
    messages = conversation.messages.all()
    return render(
        request,
        "chat/conversation.html",
        {"conversation": conversation, "chat_messages": messages},
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

        try:
            async for event in agent.stream_reply(conversation.agent_session_id, user_text):
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
                    had_error = had_error or event["is_error"]
                    if event["is_error"] and event["error"]:
                        yield _sse({"type": "error", "error": event["error"]})

        except Exception as exc:  # noqa: BLE001 — se lo mostramos al usuario y cerramos el stream
            had_error = True
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
