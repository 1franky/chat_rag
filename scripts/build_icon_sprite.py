#!/usr/bin/env python3
"""Genera `web/templates/partials/icon_sprite.html` a partir de los SVG
sueltos en `web/static/icons/lucide/` (plan-v4.md, Fase 23).

Los archivos de `static/icons/lucide/*.svg` son el vendoring "de
verdad" (bajados 1:1 de github.com/lucide-icons/lucide, ISC License —
ver `LICENSE` en esa misma carpeta), igual criterio que ya se usa para
Inter/Alpine/htmx: assets locales, sin CDN. Este script los combina en
UN sprite `<symbol>` incluido una sola vez en `base.html`, para no
pagar una request HTTP por ícono — cada uso en un template es liviano:

    {% icon "menu" %}

(ver `apps/core/templatetags/core_extras.py::icon`), que renderiza
`<svg class="icon"><use href="#icon-menu"></use></svg>`.

Para agregar un ícono nuevo en una fase futura: bajar el .svg de Lucide
a `static/icons/lucide/<nombre>.svg` (mismo formato que los que ya
hay: `viewBox="0 0 24 24"`, `stroke="currentColor"`) y correr:

    uv run python scripts/build_icon_sprite.py

Sin dependencias fuera de la stdlib — a propósito, no amerita agregar
una lib de parseo de SVG para esto.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "web" / "static" / "icons" / "lucide"
OUTPUT = ROOT / "web" / "templates" / "partials" / "icon_sprite.html"

SVG_NS = "http://www.w3.org/2000/svg"
NS_PREFIX = "{" + SVG_NS + "}"
# Sin esto, ElementTree serializa cada elemento con un prefijo `ns0:`
# autogenerado (namespace por default sin prefijo declarado) — lo
# registra vacío para que salga markup SVG normal sin prefijo.
ET.register_namespace("", SVG_NS)


def inner_markup(svg_path: Path) -> str:
    """Devuelve el contenido interno (paths/circles/...) de un SVG de
    Lucide, sin el <svg> exterior — eso lo pone el <symbol>. Serializa
    el <svg> completo de una (no hijo por hijo) para que el `xmlns`
    salga una sola vez en la etiqueta raíz, no repetido en cada hijo."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    raw = ET.tostring(root, encoding="unicode")
    # Saca la etiqueta <svg ...> de apertura y el </svg> de cierre,
    # dejando solo los hijos (paths/circles/rects/...).
    inner = re.sub(r"^\s*<svg\b[^>]*>", "", raw).strip()
    inner = re.sub(r"</svg>\s*$", "", inner).strip()
    lines = [line.strip() for line in inner.splitlines() if line.strip()]
    return "\n".join("      " + line for line in lines)


def main() -> None:
    svg_files = sorted(ICONS_DIR.glob("*.svg"))
    if not svg_files:
        raise SystemExit(f"No se encontraron .svg en {ICONS_DIR}")

    symbols = []
    for svg_path in svg_files:
        name = svg_path.stem
        symbols.append(
            f'    <symbol id="icon-{name}" viewBox="0 0 24 24">\n'
            f"{inner_markup(svg_path)}\n"
            f"    </symbol>"
        )

    names = ", ".join(f'"{p.stem}"' for p in svg_files)
    content = (
        "{# Generado por scripts/build_icon_sprite.py — no editar a mano. #}\n"
        "{# Íconos vendoreados de Lucide (ISC License, ver static/icons/lucide/LICENSE): #}\n"
        f"{{# {names} #}}\n"
        '<svg style="display:none" aria-hidden="true">\n'
        + "\n".join(symbols)
        + "\n</svg>\n"
    )

    # Django no tolera {# ... #} multilínea (ver el gotcha ya documentado
    # en el proyecto) — cada comment tag de arriba es de una sola línea
    # a propósito, no achicar a un solo bloque {# ... #} de varios \n.
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Escrito {OUTPUT} con {len(svg_files)} íconos: {names}")


if __name__ == "__main__":
    main()
