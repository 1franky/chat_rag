"""Lectura de la tabla `Document` de Django (SQLite) desde chat-rag-mcp.

`rag_list_documents` necesita filename/status/chunk_count/etc., que viven en
la base de chat-web, no en Qdrant. En vez de levantar Django completo acá
(pesado, y acopla el proceso del MCP a todo el proyecto Django) o agregar un
endpoint HTTP interno solo para esto, se lee la tabla directo con sqlite3
(stdlib) — chat-rag-mcp monta `data/sqlite` en modo solo lectura.
Es una lectura, nunca escritura: no hay riesgo de pisar al proceso de
Django, que es el único que escribe esa base.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from rag_shared.models import DocumentMeta, DocumentStatus

DB_PATH = Path(os.environ.get("DJANGO_SQLITE_PATH", "/data/sqlite/db.sqlite3"))


def _connect() -> sqlite3.Connection:
    # mode=ro: si el archivo no existe todavía (chat-web no corrió
    # migraciones aún), sqlite3 tira un error claro en vez de crear un
    # archivo vacío.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_documents() -> list[DocumentMeta]:
    if not DB_PATH.exists():
        return []

    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, filename, mime_type, status, chunk_count, uploaded_at, error_message "
            "FROM ingesta_document "
            "WHERE deleted_at IS NULL "
            "ORDER BY uploaded_at DESC"
        ).fetchall()

    return [
        DocumentMeta(
            # Django guarda los UUIDField en SQLite como hex de 32
            # caracteres SIN guiones; leyendo con sqlite3 crudo (sin pasar
            # por el ORM) llega tal cual. En Qdrant el payload usa el
            # formato CON guiones (str() de un uuid.UUID, vía el ORM) — sin
            # normalizar acá, rag_get_document_chunks no encuentra nada.
            document_id=str(uuid.UUID(row["id"])),
            filename=row["filename"],
            mime_type=row["mime_type"] or "",
            status=DocumentStatus(row["status"]),
            chunk_count=row["chunk_count"],
            uploaded_at=row["uploaded_at"],
            error_message=row["error_message"] or None,
        )
        for row in rows
    ]
