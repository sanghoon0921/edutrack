from __future__ import annotations

from django.conf import settings
from django.db import models


class AccountAuditLog(models.Model):
    """운영자가 계정과 담당 학생을 변경한 내역을 보존합니다."""

    class Action(models.TextChoices):
        USER_CREATED = "USER_CREATED", "계정 생성"
        USER_UPDATED = "USER_UPDATED", "계정 수정"
        PROFILE_UPDATED = "PROFILE_UPDATED", "내 정보 수정"
        PASSWORD_RESET = "PASSWORD_RESET", "비밀번호 변경"
        LINK_ADDED = "LINK_ADDED", "학생 연결 추가"
        LINK_PRIMARY = "LINK_PRIMARY", "대표 학생 변경"
        LINK_DEACTIVATED = "LINK_DEACTIVATED", "학생 연결 해제"
        TEACHER_STUDENT_ADDED = "TEACHER_STUDENT_ADDED", "담당 학생 배정"
        TEACHER_STUDENT_REMOVED = "TEACHER_STUDENT_REMOVED", "담당 학생 해제"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_operation_logs",
        verbose_name="처리자",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_change_logs",
        verbose_name="대상 계정",
    )
    action = models.CharField(
        "작업",
        max_length=40,
        choices=Action.choices,
        db_index=True,
    )
    summary = models.CharField("요약", max_length=255)
    metadata = models.JSONField("변경 정보", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("접속 IP", null=True, blank=True)
    created_at = models.DateTimeField("처리 시각", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("target_user", "-created_at"),
                name="account_audit_target_idx",
            ),
            models.Index(
                fields=("action", "-created_at"),
                name="account_audit_action_idx",
            ),
        ]
        verbose_name = "계정 운영 기록"
        verbose_name_plural = "계정 운영 기록"

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.summary}"


class TeacherStudentAccess(models.Model):
    """강사가 조회·배정할 수 있는 담당 학생 범위를 명시합니다."""

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_student_accesses",
        verbose_name="강사",
    )
    student_no = models.CharField("학생번호", max_length=50, db_index=True)
    student_name = models.CharField("학생명", max_length=100, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_teacher_student_accesses",
        verbose_name="배정 관리자",
    )
    is_active = models.BooleanField("배정 활성", default=True, db_index=True)
    created_at = models.DateTimeField("배정일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("student_name", "student_no")
        constraints = [
            models.UniqueConstraint(
                fields=("teacher", "student_no"),
                name="uniq_teacher_student_access",
            )
        ]
        indexes = [
            models.Index(
                fields=("teacher", "is_active", "student_no"),
                name="teacher_student_scope_idx",
            )
        ]
        verbose_name = "강사 담당 학생"
        verbose_name_plural = "강사 담당 학생"

    def __str__(self) -> str:
        label = self.student_name or self.student_no
        return f"{self.teacher.effective_name} → {label}"
