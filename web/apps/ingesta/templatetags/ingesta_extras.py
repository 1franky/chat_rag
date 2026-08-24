from django import template

register = template.Library()

_BADGE_CLASSES = {
    "pending": "bg-muted text-muted-foreground",
    "processing": "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    "indexed": "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
    "failed": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
}

# Ícono por estado (plan-v4.md, Fase 25): mismo criterio de estado que
# _BADGE_CLASSES (color), acá el ícono del sprite de Lucide — "processing"
# usa `loader-circle` con la clase `animate-spin` puesta a mano en el
# template (no acá, es un detalle de layout, no de estado).
_STATUS_ICONS = {
    "pending": "clock",
    "processing": "loader-circle",
    "indexed": "check",
    "failed": "circle-alert",
}


@register.filter
def status_badge_class(status: str) -> str:
    return _BADGE_CLASSES.get(status, "")


@register.filter
def status_icon(status: str) -> str:
    return _STATUS_ICONS.get(status, "")
