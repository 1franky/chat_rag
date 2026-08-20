from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from rag_shared.models import TextBlock


def parse(path: Path) -> Iterator[TextBlock]:
    sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl", dtype=str)
    for sheet_name, df in sheets.items():
        df = df.fillna("")
        if df.empty:
            continue
        lines = [" | ".join(str(c) for c in df.columns)]
        lines += [" | ".join(str(v) for v in row) for row in df.itertuples(index=False)]
        text = "\n".join(lines).strip()
        if text:
            yield TextBlock(text=text, section=sheet_name)
