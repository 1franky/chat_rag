from __future__ import annotations

from django.utils import timezone

from rag_shared.vector_store import delete_document_sync, set_document_collection_sync

from .models import Collection, Document


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
    # Borrado total (accounts/views.py::delete_all_data, Fase 5): las
    # colecciones son solo carpetas vacías a esta altura (ya no les queda
    # ningún documento), no tiene sentido dejarlas huérfanas atrás.
    Collection.objects.all().delete()


def move_document(document: Document, collection: Collection | None) -> None:
    """Mueve un documento a otra colección (o a ninguna, con None) — actualiza
    tanto la FK en Django como el `collection_id` de sus chunks ya indexados
    en Qdrant (plan-v2.md, Fase 10), para que un `rag_search` acotado a una
    colección refleje el cambio sin tener que re-indexar el documento."""
    document.collection = collection
    document.save(update_fields=["collection"])
    # Documento recién subido, todavía sin chunks indexados: no hay nada que
    # actualizar en Qdrant (process_document los va a subir ya con la
    # colección correcta cuando termine de procesar).
    if document.status == Document.Status.INDEXED:
        set_document_collection_sync(document.document_id, document.collection_id_str)
