from __future__ import annotations

from django.utils import timezone

from rag_shared.vector_store import delete_document_sync

from .models import Document


def delete_document(document: Document) -> None:
    """Borra un documento: chunks en Qdrant, archivo en MEDIA_ROOT y soft-delete
    en la base (compartido por la vista de borrado individual y por
    `delete_all_documents`, ver accounts/views.py Fase 5)."""
    delete_document_sync(document.document_id)
    document.file.delete(save=False)
    document.deleted_at = timezone.now()
    document.save(update_fields=["deleted_at"])


def delete_all_documents() -> None:
    for document in Document.objects.active():
        delete_document(document)
