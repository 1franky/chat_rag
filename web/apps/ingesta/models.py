import uuid

from django.db import models


def document_upload_path(instance: "Document", filename: str) -> str:
    # MEDIA_ROOT/<uuid>/<filename> (plan.md, Fase 3).
    return f"{instance.id}/{filename}"


class Collection(models.Model):
    """Carpeta simple para agrupar documentos (plan-v2.md, Fase 10): un
    documento pertenece a como mucho una colección, no es un sistema de
    etiquetas múltiples. Sin owner, igual que Document (uso 100% personal)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


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
    # SET_NULL (no CASCADE): borrar una colección no borra sus documentos,
    # solo los deja sin colección (plan-v2.md, Fase 10).
    collection = models.ForeignKey(
        Collection, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
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

    @property
    def collection_id_str(self) -> str | None:
        """El id de la colección, como string (o None) — así se guarda en el
        payload de Qdrant. `collection_id` (el atributo que genera Django
        para la FK) alcanza sin tocar la base, no hace falta `self.collection`."""
        return str(self.collection_id) if self.collection_id else None
