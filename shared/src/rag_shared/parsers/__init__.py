"""Factory de parsers por mime type. Cada parser expone
`parse(path: Path) -> Iterator[TextBlock]` (interfaz común).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Callable

from rag_shared.models import TextBlock

from . import csv as csv_parser
from . import docx as docx_parser
from . import image as image_parser
from . import md as md_parser
from . import pdf as pdf_parser
from . import pptx as pptx_parser
from . import txt as txt_parser
from . import xlsx as xlsx_parser

ParserFn = Callable[[Path], Iterator[TextBlock]]

_PARSERS: dict[str, ParserFn] = {
    "application/pdf": pdf_parser.parse,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": docx_parser.parse,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": pptx_parser.parse,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": xlsx_parser.parse,
    "text/csv": csv_parser.parse,
    "text/markdown": md_parser.parse,
    "text/plain": txt_parser.parse,
    "image/png": image_parser.parse,
    "image/jpeg": image_parser.parse,
}


class UnsupportedMimeType(ValueError):
    """El documento subido no tiene parser para su mime type."""


def get_parser(mime_type: str) -> ParserFn:
    try:
        return _PARSERS[mime_type]
    except KeyError:
        raise UnsupportedMimeType(mime_type) from None


def supported_mime_types() -> list[str]:
    return list(_PARSERS)
