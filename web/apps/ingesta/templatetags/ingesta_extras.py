from django import template

register = template.Library()

_BADGE_CLASSES = {
    "pending": "bg-muted text-muted-foreground",
    "processing": "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    "indexed": "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
    "failed": "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
}


@register.filter
def status_badge_class(status: str) -> str:
    return _BADGE_CLASSES.get(status, "")
