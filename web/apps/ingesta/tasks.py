from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task

from rag_shared.chunker import chunk_blocks
from rag_shared.embeddings import embed_passages, embed_passages_sparse
from rag_shared.mime import detect_mime_type
from rag_shared.models import Chunk
from rag_shared.parsers import UnsupportedMimeType, get_parser
from rag_shared.vector_store import ensure_collection_sync, upsert_chunks_sync

from .models import Document

logger = logging.getLogger(__name__)

# Batch de embeddings (plan.md, sección 2.1): grande para aprovechar mejor
# la vCPU, pero acotado para no acumular todo el documento en memoria.
EMBED_BATCH_SIZE = 32


@shared_task(bind=True, max_retries=0)
def process_document(self, document_id: str) -> None:
    """Parsea, chunkea, embebe e indexa un Document en Qdrant.

    1. Carga el Document, lo marca `processing`
    2. Detecta el mime type real (no confía en la extensión)
    3. Parsea -> chunks
    4. Embebe en batches
    5. Upsert en Qdrant
    6. Marca `indexed` y actualiza chunk_count
    7. Si algo falla en el medio, marca `failed` con el mensaje de error
    """
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        logger.warning("process_document: el Document %s ya no existe", document_id)
        return

    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message"])

    try:
        _process(document)
    except Exception as exc:
        logger.exception("process_document: fallo indexando %s (%s)", document_id, document.filename)
        document.status = Document.Status.FAILED
        document.error_message = str(exc)[:2000]
        document.save(update_fields=["status", "error_message"])


def _process(document: Document) -> None:
    path = Path(document.file.path)

    mime_type = detect_mime_type(path)
    document.mime_type = mime_type
    document.save(update_fields=["mime_type"])

    try:
        parser = get_parser(mime_type)
    except UnsupportedMimeType as exc:
        raise ValueError(f"Tipo de archivo no soportado: {mime_type}") from exc

    text_blocks = list(chunk_blocks(parser(path)))

    if not text_blocks:
        # Documento válido pero sin texto extraíble (ej. PDF escaneado y el
        # OCR tampoco sacó nada): queda indexado con 0 chunks, no es un error.
        document.status = Document.Status.INDEXED
        document.chunk_count = 0
        document.save(update_fields=["status", "chunk_count"])
        return

    chunks = [
        Chunk(
            document_id=document.document_id,
            chunk_index=i,
            text=block.text,
            page=block.page,
            section=block.section,
        )
        for i, block in enumerate(text_blocks)
    ]

    ensure_collection_sync()

    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[start : start + EMBED_BATCH_SIZE]
        texts = [chunk.text for chunk in batch]
        vectors = embed_passages(texts)
        sparse_vectors = embed_passages_sparse(texts)
        upsert_chunks_sync(
            document.document_id, batch, vectors, sparse_vectors, collection_id=document.collection_id_str
        )

    document.status = Document.Status.INDEXED
    document.chunk_count = len(chunks)
    document.save(update_fields=["status", "chunk_count"])
