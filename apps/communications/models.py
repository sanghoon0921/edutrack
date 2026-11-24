from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def _safe_filename(filename: str) -> str:
    return f"{uuid4().hex}{Path(filename).suffix.lower()}"


def notice_attachment_path(instance, filename: str) -> str:
    return f"communications/notices/files/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


def notice_inline_image_path(instance, filename: str) -> str:
    return f"communications/notices/images/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


class Notice(models.Model):
    class Audience(models.TextChoices):
        """공지 대상 그룹. 공지 하나에 여러 그룹을 체크할 수 있습니다(for_* 칸)."""

        ADMIN = "ADMIN", "관리자"
        TEACHER = "TEACHER", "강사"
        STUDENT = "STUDENT", "학생"
        PARENT = "PARENT", "학부모"

    # 대상 그룹 → 이 공지에서 체크 여부를 담는 칸
    AUDIENCE_FLAGS = {
        Audience.ADMIN: "for_admin",
        Audience.TEACHER: "for_teacher",
        Audience.STUDENT: "for_student",
        Audience.PARENT: "for_parent",
    }

    class Category(models.TextChoices):
        ACADEMY = "ACADEMY", "학원 공지"
        CLASS = "CLASS", "반 공지"

    title = models.CharField("제목", max_length=200)
    content = models.TextField("내용")
    category = models.CharField(
        "구분",
        max_length=10,
        choices=Category.choices,
        default=Category.ACADEMY,
        db_index=True,
        help_text="학원 운영 전체에 대한 공지인지, 한 반에 대한 공지인지 고릅니다.",
    )
    group = models.ForeignKey(
        "learning.LearningGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notices",
        verbose_name="반",
        help_text="반 공지일 때 그 반 학생·학부모와 그 반 강사에게만 보입니다.",
    )
    for_admin = models.BooleanField("대상: 관리자", default=False)
    for_teacher = models.BooleanField("대상: 강사", default=False)
    for_student = models.BooleanField("대상: 학생", default=False)
    for_parent = models.BooleanField("대상: 학부모", default=False)
    is_pinned = models.BooleanField("상단 고정", default=False, db_index=True)
    is_published = models.BooleanField("공개", default=False, db_index=True)
    published_at = models.DateTimeField("공개일", null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_notices",
        verbose_name="작성자",
    )
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("-is_pinned", "-published_at", "-created_at", "-id")
        indexes = [
            models.Index(
                fields=("is_published", "-published_at"),
                name="notice_visible_idx",
            ),
        ]
        verbose_name = "공지사항"
        verbose_name_plural = "공지사항"

    @property
    def audiences(self) -> list[str]:
        """체크된 대상 그룹 값(ADMIN·TEACHER·STUDENT·PARENT 순서)."""
        return [value for value, flag in self.AUDIENCE_FLAGS.items() if getattr(self, flag)]

    def set_audiences(self, values) -> None:
        for value, flag in self.AUDIENCE_FLAGS.items():
            setattr(self, flag, value in values)

    @property
    def audience_display(self) -> str:
        """목록·상세에 보이는 대상: 네 그룹 모두면 '전체', 아니면 '강사 · 학부모'처럼."""
        chosen = self.audiences
        if len(chosen) == len(self.AUDIENCE_FLAGS):
            return "전체"
        return " · ".join(self.Audience(value).label for value in chosen) or "대상 없음"

    def save(self, *args, **kwargs) -> None:
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        elif not self.is_published:
            self.published_at = None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


class NoticeAttachment(models.Model):
    notice = models.ForeignKey(
        Notice,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="공지",
    )
    file = models.FileField("파일", upload_to=notice_attachment_path)
    original_name = models.CharField("원본 파일명", max_length=255)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    uploaded_at = models.DateTimeField("업로드 시각", auto_now_add=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "공지 첨부파일"
        verbose_name_plural = "공지 첨부파일"

    def __str__(self) -> str:
        return self.original_name


class NoticeInlineImage(models.Model):
    notice = models.ForeignKey(
        Notice,
        on_delete=models.CASCADE,
        related_name="inline_images",
        verbose_name="공지",
    )
    file = models.FileField("이미지", upload_to=notice_inline_image_path)
    original_name = models.CharField("원본 파일명", max_length=255)
    size = models.PositiveBigIntegerField("파일 크기", default=0)
    uploaded_at = models.DateTimeField("업로드 시각", auto_now_add=True)

    class Meta:
        ordering = ("id",)
        verbose_name = "공지 본문 이미지"
        verbose_name_plural = "공지 본문 이미지"

    def __str__(self) -> str:
        return self.original_name


class NoticeRead(models.Model):
    notice = models.ForeignKey(
        Notice,
        on_delete=models.CASCADE,
        related_name="read_records",
        verbose_name="공지사항",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notice_reads",
        verbose_name="사용자",
    )
    read_at = models.DateTimeField("읽은 시각", default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("notice", "user"),
                name="unique_notice_read_user",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "-read_at"), name="notice_read_user_idx"),
        ]
        verbose_name = "공지 읽음"
        verbose_name_plural = "공지 읽음"

    def __str__(self) -> str:
        return f"{self.user} · {self.notice}"


class Notification(models.Model):
    class Kind(models.TextChoices):
        NOTICE = "NOTICE", "공지사항"
        ASSIGNMENT = "ASSIGNMENT", "새 과제"
        SUBMISSION = "SUBMISSION", "과제 제출"
        FEEDBACK = "FEEDBACK", "피드백"
        SYSTEM = "SYSTEM", "시스템"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="사용자",
    )
    kind = models.CharField(
        "알림 종류",
        max_length=20,
        choices=Kind.choices,
        default=Kind.SYSTEM,
        db_index=True,
    )
    title = models.CharField("제목", max_length=200)
    message = models.TextField("내용", blank=True)
    target_url = models.CharField("이동 주소", max_length=500, blank=True)
    event_key = models.CharField("중복 방지 키", max_length=255, blank=True)
    is_read = models.BooleanField("읽음", default=False, db_index=True)
    read_at = models.DateTimeField("읽은 시각", null=True, blank=True)
    created_at = models.DateTimeField("생성일", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "event_key"),
                condition=~Q(event_key=""),
                name="unique_user_notification_event",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "is_read", "-created_at"),
                name="notification_inbox_idx",
            ),
        ]
        verbose_name = "사이트 알림"
        verbose_name_plural = "사이트 알림"

    def mark_read(self) -> None:
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=("is_read", "read_at"))

    def __str__(self) -> str:
        return f"{self.user} · {self.title}"
