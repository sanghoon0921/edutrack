from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{uuid4().hex}{suffix}"


def course_resource_upload_path(instance: "CourseResource", filename: str) -> str:
    board_id = instance.category.board_id if instance.category_id else "draft"
    return (
        f"classroom/resources/{board_id}/{timezone.localdate():%Y/%m}/"
        f"{_safe_filename(filename)}"
    )


class CourseBoard(models.Model):
    title = models.CharField("과목명", max_length=200)
    term = models.CharField("Term", max_length=120, blank=True)
    subject = models.CharField("Subject", max_length=120, blank=True)
    description = models.TextField("과목 안내", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_course_boards",
        verbose_name="등록자",
    )
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    sort_order = models.PositiveIntegerField("정렬 순서", default=0, db_index=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("sort_order", "-updated_at", "id")
        verbose_name = "과목 자료 공간"
        verbose_name_plural = "과목 자료 공간"

    def __str__(self) -> str:
        return self.title


class CourseBoardRecipient(models.Model):
    board = models.ForeignKey(
        CourseBoard,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="과목",
    )
    student_id = models.CharField("학생번호", max_length=50, db_index=True)
    student_name = models.CharField("학생명", max_length=100)
    created_at = models.DateTimeField("배정일", auto_now_add=True)

    class Meta:
        ordering = ("student_name", "student_id")
        constraints = [
            models.UniqueConstraint(
                fields=("board", "student_id"),
                name="uniq_course_board_recipient",
            )
        ]
        indexes = [
            models.Index(
                fields=("student_id", "board"),
                name="course_board_recipient_idx",
            )
        ]
        verbose_name = "과목 대상 학생"
        verbose_name_plural = "과목 대상 학생"

    def __str__(self) -> str:
        return f"{self.board.title} · {self.student_name}"


class CourseCategory(models.Model):
    board = models.ForeignKey(
        CourseBoard,
        on_delete=models.CASCADE,
        related_name="categories",
        verbose_name="과목",
    )
    title = models.CharField("카테고리명", max_length=120)
    description = models.CharField("설명", max_length=255, blank=True)
    sort_order = models.PositiveIntegerField("정렬 순서", default=0, db_index=True)
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("board", "title"),
                name="uniq_course_category_title",
            )
        ]
        verbose_name = "과목 자료 카테고리"
        verbose_name_plural = "과목 자료 카테고리"

    def __str__(self) -> str:
        return f"{self.board.title} · {self.title}"


class CourseResource(models.Model):
    class Type(models.TextChoices):
        PDF = "PDF", "PDF"
        FILE = "FILE", "일반 파일"
        LINK = "LINK", "외부 링크"

    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.CASCADE,
        related_name="resources",
        verbose_name="카테고리",
    )
    title = models.CharField("자료명", max_length=220)
    resource_type = models.CharField(
        "자료 유형",
        max_length=10,
        choices=Type.choices,
        default=Type.PDF,
        db_index=True,
    )
    description = models.TextField("자료 설명", blank=True)
    file = models.FileField(
        "업로드 파일",
        upload_to=course_resource_upload_path,
        blank=True,
    )
    external_url = models.URLField("외부 링크", max_length=500, blank=True)
    original_name = models.CharField("원본 파일명", max_length=255, blank=True)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    sort_order = models.PositiveIntegerField("정렬 순서", default=0, db_index=True)
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_course_resources",
        verbose_name="등록자",
    )
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "과목 자료"
        verbose_name_plural = "과목 자료"

    @property
    def is_pdf(self) -> bool:
        return self.resource_type == self.Type.PDF and bool(self.file)

    def __str__(self) -> str:
        return self.title
