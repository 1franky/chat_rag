"""Generación de archivos de reportería (plan-v3.md, Fase 20) — funciones
que reciben datos ya estructurados (título + columnas + filas, ya armados
por Claude) y devuelven la ruta del archivo escrito en disco, bajo un
nombre `<uuid4>.<ext>` bien determinístico (sin tracking en DB en este v1,
ver la nota de arquitectura del plan — el nombre en sí es la única
referencia al archivo).

Vive acá (no en `rag-mcp/`) por el mismo criterio que
`embeddings.py`/`vector_store.py`: compartido en principio, aunque hoy
solo lo use `chat-rag-mcp` (las tools `report_*` de `rag-mcp/server.py`).
"""

from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path

import openpyxl

# Coincide con el mount RW nuevo de chat-rag-mcp en compose.yaml
# (`./data/media/reports:/data/media/reports`) — a diferencia del resto de
# `MODEL_CACHE_DIR`/etc., este no lo comparte chat-web via Django settings
# (no hay Django acá): chat-web sirve estos archivos calculando la misma
# ruta como `MEDIA_ROOT / "reports"` (ver apps/core/views.py::download_report).
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/data/media/reports"))

DEFAULT_TITLE = "Reporte"


def _report_path(ext: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR / f"{uuid.uuid4()}.{ext}"


def write_txt(title: str, columns: list[str], rows: list[list[str]]) -> Path:
    """Texto plano legible: título, encabezado, filas separadas por " | "."""
    path = _report_path("txt")
    lines = [title or DEFAULT_TITLE, "", " | ".join(columns), "-" * 40]
    lines += [" | ".join(str(cell) for cell in row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_csv(title: str, columns: list[str], rows: list[list[str]]) -> Path:
    """CSV estándar: sin línea de título (rompería un import directo a
    Excel/pandas, que esperan que la primera fila sea el encabezado)."""
    path = _report_path("csv")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def write_xlsx(title: str, columns: list[str], rows: list[list[str]]) -> Path:
    path = _report_path("xlsx")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    # Los nombres de hoja de Excel tienen un máximo de 31 caracteres —
    # truncar en vez de dejar que openpyxl tire ValueError.
    sheet.title = (title or DEFAULT_TITLE)[:31]
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path
