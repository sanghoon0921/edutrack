from django import template

from apps.content_editor.services import render_pasted_content

register = template.Library()


@register.filter
def pasted_content(value):
    return render_pasted_content(value)
