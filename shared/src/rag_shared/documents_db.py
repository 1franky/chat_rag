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

from rag_shared.models import CollectionMeta, DocumentMeta, DocumentStatus

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
            "SELECT d.id, d.filename, d.mime_type, d.status, d.chunk_count, d.uploaded_at, "
            "       d.error_message, c.name AS collection_name "
            "FROM ingesta_document d "
            "LEFT JOIN ingesta_collection c ON c.id = d.collection_id "
            "WHERE d.deleted_at IS NULL "
            "ORDER BY d.uploaded_at DESC"
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
            collection=row["collection_name"],
        )
        for row in rows
    ]


def list_collections() -> list[CollectionMeta]:
    """Colecciones existentes (plan-v2.md, Fase 10), con cuántos documentos
    activos tiene cada una — para que `rag_list_collections` le muestre a
    Claude algo más útil que solo el nombre."""
    if not DB_PATH.exists():
        return []

    with _connect() as conn:
        rows = conn.execute(
            "SELECT c.name AS name, COUNT(d.id) AS document_count "
            "FROM ingesta_collection c "
            "LEFT JOIN ingesta_document d ON d.collection_id = c.id AND d.deleted_at IS NULL "
            "GROUP BY c.id, c.name "
            "ORDER BY c.name"
        ).fetchall()

    return [CollectionMeta(name=row["name"], document_count=row["document_count"]) for row in rows]


def resolve_collection_id(name: str) -> str | None:
    """El id (con guiones, formato Qdrant) de la colección con ese nombre
    exacto, o None si no existe — para que `rag_search(collection=...)`
    pueda resolver el nombre que le pasa Claude al filtro real de Qdrant."""
    if not DB_PATH.exists():
        return None

    with _connect() as conn:
        row = conn.execute("SELECT id FROM ingesta_collection WHERE name = ?", (name,)).fetchone()

    return str(uuid.UUID(row["id"])) if row else None
