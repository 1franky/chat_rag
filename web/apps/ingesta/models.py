import uuid

from django.db import models


def document_upload_path(instance: "Document", filename: str) -> str:
    # MEDIA_ROOT/<uuid>/<filename> (plan.md, Fase 3).
    return f"{instance.id}/{filename}"


class DocumentQuerySet(models.QuerySet):
    def active(self):
        """Documentos no borrados (soft-delete)."""
        return self.filter(deleted_at__isnull=True)


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        INDEXED = "indexed", "Indexado"
        FAILED = "failed", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path)
    # Mime type "del navegador" al subir; la task de ingesta lo pisa con la
    # detección real (rag_shared.mime.detect_mime_type) apenas arranca.
    mime_type = models.CharField(max_length=127, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")
    # Soft-delete: el borrado "real" del archivo/chunks en Qdrant lo hace la
    # vista de borrado; este campo solo lo saca de las listas.
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.filename

    @property
    def document_id(self) -> str:
        """El id, como string — así se guarda en el payload de Qdrant."""
        return str(self.id)
