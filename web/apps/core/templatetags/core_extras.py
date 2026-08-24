from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def icon(name: str, size: int = 16, cls: str = "", label: str = "") -> str:
    """Renderiza un ícono del sprite vendoreado de Lucide
    (`partials/icon_sprite.html`, incluido una sola vez en `base.html` —
    generado por `scripts/build_icon_sprite.py`, plan-v4.md Fase 23).

    Sin `label` (caso normal): `aria-hidden="true"`, ícono puramente
    decorativo. Es el caso de casi todo uso — incluyendo un botón cuyo
    único contenido visible es el ícono, siempre que el `<button>`/`<a>`
    que lo envuelve ya tenga su propio `aria-label` (patrón estándar; ver
    el botón ☰ de `base.html` — el nombre accesible lo da el botón, no el
    ícono). Con `label`: agrega `role="img"` + `aria-label` al propio
    `<svg>` — reservado para un ícono suelto que NO está envuelto en un
    control ya nombrado (ej. un ícono de estado inline). No usar ambos a
    la vez (duplica el anuncio en lectores de pantalla).

    Uso: `{% icon "menu" %}`, `{% icon "trash-2" size=18 cls="text-destructive" %}`.
    """
    classes = f"icon {cls}".strip()
    if label:
        a11y = f'role="img" aria-label="{escape(label)}"'
    else:
        a11y = 'aria-hidden="true"'
    return mark_safe(
        f'<svg class="{escape(classes)}" width="{size}" height="{size}" {a11y}>'
        f'<use href="#icon-{escape(name)}"></use></svg>'
    )
