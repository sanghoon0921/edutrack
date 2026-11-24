from __future__ import annotations

from django import template


register = template.Library()


@register.filter
def krw(value) -> str:
    try:
        amount = int(float(value or 0))
    except (TypeError, ValueError):
        amount = 0

    return f"₩{amount:,}"
