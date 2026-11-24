from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        suffix = ".bin"
    return f"{uuid4().hex}{suffix}"


def pasted_image_upload_path(instance: "PastedImage", filename: str) -> str:
    return (
        f"content-editor/pasted/{timezone.localdate():%Y/%m}/"
        f"{_safe_filename(filename)}"
    )


class PastedImage(models.Model):
    class TargetType(models.TextChoices):
        DRAFT = "DRAFT", "작성 중"
        NOTICE = "NOTICE", "공지"
        ASSIGNMENT = "ASSIGNMENT", "과제"
        DISCUSSION = "DISCUSSION", "토론"

    token = models.UUIDField("본문 토큰", default=uuid4, unique=True, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pasted_images",
        verbose_name="업로드 계정",
    )
    image = models.FileField("이미지", upload_to=pasted_image_upload_path)
    original_name = models.CharField("원본 파일명", max_length=255)
    content_type = models.CharField("콘텐츠 형식", max_length=100)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    target_type = models.CharField(
        "연결 대상",
        max_length=20,
        choices=TargetType.choices,
        default=TargetType.DRAFT,
        db_index=True,
    )
    target_id = models.PositiveBigIntegerField(
        "연결 대상 번호",
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField("업로드 시각", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("수정 시각", auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(
                fields=("owner", "target_type", "target_id"),
                name="pasted_owner_target_idx",
            ),
        ]
        verbose_name = "붙여넣기 본문 이미지"
        verbose_name_plural = "붙여넣기 본문 이미지"

    @property
    def token_markup(self) -> str:
        return f"[[paste-image:{self.token}]]"

    def __str__(self) -> str:
        return f"{self.owner} · {self.original_name}"
