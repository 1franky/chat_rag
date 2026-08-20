import json

from django import template

register = template.Library()


@register.filter
def to_json(value) -> str:
    if value in (None, ""):
        return ""
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except TypeError:
        return str(value)
