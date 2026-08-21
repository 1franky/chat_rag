import secrets
import uuid

from django.conf import settings
from django.db import models

TITLE_MAX_LENGTH = 60


def _generate_share_token() -> str:
    # 32 bytes de entropía (no adivinable), url-safe: viaja directo en la
    # URL pública /compartido/<token>/ sin necesitar encoding.
    return secrets.token_urlsafe(32)


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=255, blank=True, default="")
    # session_id que devuelve el Agent SDK (ResultMessage.session_id): se usa
    # para `resume` en el siguiente mensaje y así mantener el contexto de la
    # conversación entre requests (ver chat/agent.py).
    agent_session_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversación {self.id}"

    async def aset_title_from_message(self, text: str) -> None:
        if self.title:
            return
        text = " ".join(text.split())
        self.title = text[:TITLE_MAX_LENGTH] + ("…" if len(text) > TITLE_MAX_LENGTH else "")
        await self.asave(update_fields=["title"])


class SharedLink(models.Model):
    """Link de solo lectura para compartir una conversación (plan-v2.md,
    Fase 11) — separado de Conversation (no un campo único ahí) para poder
    tener más de un link histórico y revocar sin invalidar el resto."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="shared_links")
    token = models.CharField(max_length=64, unique=True, default=_generate_share_token, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "activo" if self.revoked_at is None else "revocado"
        return f"Link de {self.conversation_id} ({state})"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Usuario"
        ASSISTANT = "assistant", "Asistente"
        TOOL = "tool", "Tool"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    # Solo tiene sentido cuando role == TOOL.
    tool_name = models.CharField(max_length=255, blank=True, default="")
    tool_args = models.JSONField(null=True, blank=True)
    tool_result = models.JSONField(null=True, blank=True)
    is_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.get_role_display()}: {self.content[:50]}"
