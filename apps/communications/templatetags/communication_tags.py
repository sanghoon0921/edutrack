import re

from django import template
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.content_editor.services import replace_pasted_tokens_in_escaped_text

register = template.Library()


@register.filter
def notice_content(notice):
    text = escape(notice.content or "")
    images = list(notice.inline_images.all())

    def replace(match):
        index = int(match.group(1)) - 1
        if index < 0 or index >= len(images):
            return '<span class="notice-missing-image">[이미지를 찾을 수 없습니다]</span>'
        image = images[index]
        url = reverse(
            "communications:notice-inline-image",
            kwargs={"notice_id": notice.pk, "image_id": image.pk},
        )
        alt = escape(image.original_name)
        return f'<figure class="notice-inline-figure"><img src="{url}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption></figure>'

    text = re.sub(r"\[\[image:(\d+)\]\]", replace, text)
    text = replace_pasted_tokens_in_escaped_text(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return mark_safe(text)
