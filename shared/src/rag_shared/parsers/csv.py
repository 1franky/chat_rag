from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from rag_shared.models import TextBlock


def parse(path: Path) -> Iterator[TextBlock]:
    # sep=None + engine="python": autodetecta el delimitador (coma, punto y
    # coma, tab) en vez de asumir coma siempre.
    df = pd.read_csv(path, dtype=str, keep_default_na=False, sep=None, engine="python")
    if df.empty:
        return
    lines = [" | ".join(str(c) for c in df.columns)]
    lines += [" | ".join(str(v) for v in row) for row in df.itertuples(index=False)]
    text = "\n".join(lines).strip()
    if text:
        yield TextBlock(text=text)
