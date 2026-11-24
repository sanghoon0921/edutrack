from __future__ import annotations

import re
from collections.abc import Iterable
from uuid import UUID

from django.db import transaction
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe

from .models import PastedImage


PASTED_TOKEN_RE = re.compile(
    r"\[\[paste-image:(?P<token>[0-9a-fA-F-]{32,36})\]\]"
)


def extract_pasted_tokens(text: str | None) -> list[UUID]:
    values: list[UUID] = []
    for match in PASTED_TOKEN_RE.finditer(text or ""):
        try:
            token = UUID(match.group("token"))
        except (TypeError, ValueError):
            continue
        if token not in values:
            values.append(token)
    return values


def _delete_images(images: Iterable[PastedImage]) -> None:
    for image in images:
        image.delete()


@transaction.atomic
def sync_pasted_images(
    *,
    text: str | None,
    owner,
    target_type: str,
    target_id: int,
) -> None:
    """본문 토큰을 대상 레코드에 연결하고 제거된 기존 이미지는 함께 정리합니다."""

    tokens = extract_pasted_tokens(text)
    token_strings = [str(token) for token in tokens]

    # 현재 사용자가 작성 중 업로드한 이미지 또는 같은 대상에 이미 연결된 이미지만
    # 연결할 수 있습니다. 다른 작성자의 토큰을 복사해도 대상이 변경되지 않습니다.
    allowed = PastedImage.objects.filter(owner=owner, token__in=token_strings).filter(
        target_type__in=(PastedImage.TargetType.DRAFT, target_type)
    )
    for image in allowed:
        if image.target_type == target_type and image.target_id not in (None, target_id):
            continue
        image.target_type = target_type
        image.target_id = target_id
        image.save(update_fields=("target_type", "target_id", "updated_at"))

    # 권한 검사가 끝난 저장 View에서만 호출되므로, 다른 관리자가 수정한 경우에도
    # 해당 대상에서 본문 토큰이 제거된 오래된 이미지를 함께 정리합니다.
    stale = list(
        PastedImage.objects.filter(
            target_type=target_type,
            target_id=target_id,
        ).exclude(token__in=token_strings)
    )
    _delete_images(stale)


def delete_target_images(*, target_type: str, target_id: int) -> None:
    _delete_images(
        list(
            PastedImage.objects.filter(
                target_type=target_type,
                target_id=target_id,
            )
        )
    )


def replace_pasted_tokens_in_escaped_text(escaped_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group("token")
        try:
            url = reverse("content-editor:image", kwargs={"token": token})
        except Exception:
            return '<span class="rich-paste-missing">[이미지를 표시할 수 없습니다]</span>'
        return (
            '<figure class="rich-paste-figure">'
            f'<img src="{escape(url)}" alt="본문 이미지" loading="lazy">'
            "</figure>"
        )

    return PASTED_TOKEN_RE.sub(replace, escaped_text)


def render_pasted_content(text: str | None):
    escaped_text = escape(text or "")
    escaped_text = replace_pasted_tokens_in_escaped_text(escaped_text)
    escaped_text = (
        escaped_text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "<br>")
    )
    return mark_safe(escaped_text)
