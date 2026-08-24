"""Generación de archivos de reportería (plan-v3.md, Fases 20-21) —
funciones que reciben datos ya estructurados (título + columnas + filas, o
título + secciones, ya armados por Claude) y devuelven la ruta del
archivo escrito en disco, bajo un nombre `<uuid4>.<ext>` bien
determinístico (sin tracking en DB en este v1, ver la nota de
arquitectura del plan — el nombre en sí es la única referencia al
archivo).

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

from rag_shared.models import ReportSection

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


def _body_lines(body: str) -> list[str]:
    return [line.strip() for line in body.splitlines() if line.strip()]


def write_docx(title: str, sections: list[ReportSection]) -> Path:
    """Documento Word (plan-v3.md, Fase 21): título + una secuencia de
    secciones (encabezado + párrafos/bullets), sin diseño elaborado."""
    import docx

    path = _report_path("docx")
    document = docx.Document()
    document.add_heading(title or DEFAULT_TITLE, level=0)
    for section in sections:
        document.add_heading(section.heading, level=1)
        for line in _body_lines(section.body):
            if line.startswith(("- ", "* ")):
                document.add_paragraph(line[2:], style="List Bullet")
            else:
                document.add_paragraph(line)
    document.save(path)
    return path


def write_pptx(title: str, sections: list[ReportSection]) -> Path:
    """Presentación PowerPoint (plan-v3.md, Fase 21): portada + una
    diapositiva por sección, layout título+contenido de la plantilla
    default de python-pptx (`slide_layouts[1]`, placeholder de contenido
    en el índice 1 — confirmado, no asumido: la plantilla default varía
    entre versiones de python-pptx/PowerPoint)."""
    from pptx import Presentation

    path = _report_path("pptx")
    presentation = Presentation()
    cover = presentation.slides.add_slide(presentation.slide_layouts[0])
    cover.shapes.title.text = title or DEFAULT_TITLE

    content_layout = presentation.slide_layouts[1]
    for section in sections:
        slide = presentation.slides.add_slide(content_layout)
        slide.shapes.title.text = section.heading
        lines = _body_lines(section.body)
        text_frame = slide.placeholders[1].text_frame
        text_frame.text = lines[0] if lines else ""
        for line in lines[1:]:
            text_frame.add_paragraph().text = line

    presentation.save(path)
    return path


# fpdf2 con las fuentes core (Helvetica) solo soporta latin-1 estricto para
# el texto — no cp1252/WinAnsi pese a ser lo que uno esperaría de un PDF:
# cualquier raya larga ("—") o comilla tipográfica ("“"/"”"), MUY comunes en
# la prosa que arma Claude, tira FPDFUnicodeEncodingException y aborta la
# generación entera (confirmado probándolo, no es una suposición). Mapear
# la puntuación "inteligente" más común a su equivalente ASCII/latin-1 antes
# de pasarle nada a fpdf2, y `errors="replace"` como red de seguridad final
# para cualquier otro caracter fuera de rango (ej. emoji) en vez de que
# rompa — se pierde ese caracter puntual, no el reporte entero.
_PDF_CHAR_MAP = str.maketrans(
    {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "•": "-"}
)


def _pdf_safe(text: str) -> str:
    return text.translate(_PDF_CHAR_MAP).encode("latin-1", errors="replace").decode("latin-1")


def write_pdf(title: str, sections: list[ReportSection]) -> Path:
    """PDF (plan-v3.md, Fase 21): título + secuencia de secciones. fpdf2 en
    vez de reportlab — más simple para este caso de uso (texto simple, sin
    layout elaborado en v1)."""
    from fpdf import FPDF, XPos, YPos

    path = _report_path("pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 10, _pdf_safe(title or DEFAULT_TITLE), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    for section in sections:
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, _pdf_safe(section.heading), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 11)
        for line in _body_lines(section.body):
            # Los bullets en PDF son un simple "- " a mano (no hay un
            # equivalente directo a "List Bullet" de docx/pptx sin agregar
            # más complejidad de layout) — igual de legible en v1.
            prefix = "- " if line.startswith(("- ", "* ")) else ""
            text = line[2:] if prefix else line
            pdf.multi_cell(0, 6, _pdf_safe(prefix + text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)
    pdf.output(str(path))
    return path
