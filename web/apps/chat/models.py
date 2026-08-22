import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

TITLE_MAX_LENGTH = 60


def _generate_share_token() -> str:
    # 32 bytes de entropía (no adivinable), url-safe: viaja directo en la
    # URL pública /compartido/<token>/ sin necesitar encoding.
    return secrets.token_urlsafe(32)


class Conversation(models.Model):
    class Model(models.TextChoices):
        # Alias del Agent SDK ("sonnet"/"opus"), no un ID de modelo pineado
        # (plan-v2.md, Fase 13) — el SDK/CLI los resuelve a la versión
        # vigente de cada uno, así no hay que tocar este código cada vez
        # que Anthropic libera un modelo nuevo.
        SONNET = "sonnet", "Sonnet"
        OPUS = "opus", "Opus"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=255, blank=True, default="")
    # session_id que devuelve el Agent SDK (ResultMessage.session_id): se usa
    # para `resume` en el siguiente mensaje y así mantener el contexto de la
    # conversación entre requests (ver chat/agent.py).
    agent_session_id = models.CharField(max_length=64, blank=True, default="")
    # Elegido al crear la conversación, no editable después (plan-v2.md,
    # Fase 13) — cambiar de modelo a mitad de una conversación ya resumida
    # por `agent_session_id` es confuso (el contexto previo quedó generado
    # por el otro modelo).
    model = models.CharField(max_length=16, choices=Model.choices, default=Model.SONNET)
    # Suma de ResultMessage.total_cost_usd de todos los turnos (plan-v3.md,
    # Fase 14) — Decimal para no arrastrar errores de redondeo binario de
    # float al acumular; SQLite no tiene problema con DecimalField de Django.
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal("0"))
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
