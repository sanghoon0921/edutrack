from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{uuid4().hex}{suffix}"


def assignment_upload_path(instance: "Assignment", filename: str) -> str:
    return f"assignments/materials/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


def submission_upload_path(instance: "Submission", filename: str) -> str:
    student_id = instance.recipient.student_id if instance.recipient_id else "unknown"
    return f"assignments/submissions/{student_id}/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


class Assignment(models.Model):
    group = models.ForeignKey(
        "learning.LearningGroup",
        on_delete=models.SET_NULL,
        related_name="assignments",
        null=True,
        blank=True,
        verbose_name="그룹",
    )
    title = models.CharField("과제 제목", max_length=200)
    description = models.TextField("과제 내용")
    available_from = models.DateTimeField(
        "공개 시작",
        null=True,
        blank=True,
        db_index=True,
    )
    due_at = models.DateTimeField("마감일", db_index=True)
    points = models.PositiveIntegerField("배점", default=10)
    submission_type = models.CharField("제출 유형", max_length=10, choices=[("BOTH", "텍스트 또는 파일"), ("FILE", "파일 업로드"), ("TEXT", "텍스트 답안")], default="BOTH")
    attachment = models.FileField(
        "과제 첨부파일",
        upload_to=assignment_upload_path,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_assignments",
        verbose_name="등록자",
    )
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "과제"
        verbose_name_plural = "과제"

    @property
    def is_overdue(self) -> bool:
        return self.due_at < timezone.now()

    @property
    def is_available(self) -> bool:
        return bool(
            self.is_published
            and (self.available_from is None or self.available_from <= timezone.now())
        )

    @property
    def can_submit(self) -> bool:
        return self.is_available and not self.is_overdue

    @property
    def schedule_status(self) -> str:
        if not self.is_published:
            return "DRAFT"
        if self.available_from and self.available_from > timezone.now():
            return "UPCOMING"
        if self.is_overdue:
            return "CLOSED"
        return "OPEN"

    @property
    def schedule_label(self) -> str:
        return {
            "DRAFT": "임시저장",
            "UPCOMING": "공개 예정",
            "CLOSED": "마감",
            "OPEN": "진행 중",
        }[self.schedule_status]

    def __str__(self) -> str:
        return self.title


class AssignmentRecipient(models.Model):
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="과제",
    )
    student_id = models.CharField("학생번호", max_length=50, db_index=True)
    student_name = models.CharField("학생명", max_length=100)
    created_at = models.DateTimeField("배정일", auto_now_add=True)

    class Meta:
        ordering = ("student_name", "student_id")
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "student_id"),
                name="uniq_assignment_recipient",
            )
        ]
        indexes = [
            models.Index(
                fields=("student_id", "assignment"),
                name="assign_recipient_lookup",
            )
        ]
        verbose_name = "과제 대상 학생"
        verbose_name_plural = "과제 대상 학생"

    @property
    def submission_object(self) -> "Submission | None":
        try:
            return self.submission
        except Submission.DoesNotExist:
            return None

    @property
    def status_code(self) -> str:
        submission = self.submission_object
        if submission is not None and submission.feedback_at is not None:
            return "FEEDBACK_COMPLETE"
        if submission is not None and submission.submitted_at is not None:
            return "SUBMITTED"
        if self.assignment.is_overdue:
            return "OVERDUE"
        return "PENDING"

    @property
    def status_label(self) -> str:
        return {
            "PENDING": "미제출",
            "SUBMITTED": "제출완료",
            "FEEDBACK_COMPLETE": "피드백완료",
            "OVERDUE": "마감지남",
        }[self.status_code]

    def __str__(self) -> str:
        return f"{self.assignment.title} · {self.student_name}"


class Submission(models.Model):
    recipient = models.OneToOneField(
        AssignmentRecipient,
        on_delete=models.CASCADE,
        related_name="submission",
        verbose_name="과제 대상",
    )
    text_answer = models.TextField("텍스트 답안", blank=True)
    attachment = models.FileField(
        "제출파일",
        upload_to=submission_upload_path,
        blank=True,
    )
    submitted_at = models.DateTimeField("제출일", null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)
    attachment_name = models.CharField("제출 원본 파일명", max_length=255, blank=True)
    score = models.DecimalField("점수", max_digits=10, decimal_places=2, null=True, blank=True)
    feedback = models.TextField("강사 피드백", blank=True)
    feedback_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_submissions",
        verbose_name="피드백 작성자",
        null=True,
        blank=True,
    )
    feedback_at = models.DateTimeField("피드백 작성일", null=True, blank=True)

    class Meta:
        ordering = ("-submitted_at", "-updated_at")
        verbose_name = "과제 제출"
        verbose_name_plural = "과제 제출"

    @property
    def has_content(self) -> bool:
        return bool(self.text_answer.strip() or self.attachment or (self.pk and self.extra_files.exists()))

    def __str__(self) -> str:
        return f"{self.recipient.student_name} · {self.recipient.assignment.title}"
