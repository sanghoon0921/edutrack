from __future__ import annotations

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    """CSV 일괄등록·이전 작업의 요약과 실행 결과를 보관합니다."""

    class Kind(models.TextChoices):
        USERS = "USERS", "사용자·학생 연결"
        ASSIGNMENTS = "ASSIGNMENTS", "기존 과제·제출 이력"

    class Status(models.TextChoices):
        RUNNING = "RUNNING", "처리 중"
        COMPLETED = "COMPLETED", "완료"
        COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS", "일부 오류"
        FAILED = "FAILED", "실패"

    class Mode(models.TextChoices):
        CREATE_ONLY = "CREATE_ONLY", "신규만 생성"
        UPSERT = "UPSERT", "기존 데이터 갱신"

    kind = models.CharField("이전 종류", max_length=24, choices=Kind.choices, db_index=True)
    mode = models.CharField("처리 방식", max_length=24, choices=Mode.choices)
    status = models.CharField(
        "상태",
        max_length=32,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    source_filename = models.CharField("원본 파일명", max_length=255)
    source_sha256 = models.CharField("원본 SHA256", max_length=64, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_import_batches",
        verbose_name="실행 관리자",
    )
    total_rows = models.PositiveIntegerField("전체 행", default=0)
    created_count = models.PositiveIntegerField("생성", default=0)
    updated_count = models.PositiveIntegerField("갱신", default=0)
    skipped_count = models.PositiveIntegerField("건너뜀", default=0)
    error_count = models.PositiveIntegerField("오류", default=0)
    summary = models.JSONField("요약", default=dict, blank=True)
    created_at = models.DateTimeField("시작 시각", auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField("완료 시각", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("kind", "-created_at"), name="import_batch_kind_idx"),
            models.Index(fields=("status", "-created_at"), name="import_batch_status_idx"),
        ]
        verbose_name = "데이터 이전 작업"
        verbose_name_plural = "데이터 이전 작업"

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.source_filename}"


class ImportRowResult(models.Model):
    """민감정보를 제외한 행별 처리 결과만 기록합니다."""

    class Action(models.TextChoices):
        CREATED = "CREATED", "생성"
        UPDATED = "UPDATED", "갱신"
        SKIPPED = "SKIPPED", "건너뜀"
        ERROR = "ERROR", "오류"

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="row_results",
        verbose_name="이전 작업",
    )
    row_number = models.PositiveIntegerField("CSV 행 번호")
    external_key = models.CharField("외부 식별값", max_length=255, blank=True, db_index=True)
    action = models.CharField("처리 결과", max_length=16, choices=Action.choices, db_index=True)
    target_type = models.CharField("대상 유형", max_length=50, blank=True)
    target_id = models.CharField("대상 ID", max_length=50, blank=True)
    message = models.CharField("메시지", max_length=500, blank=True)
    safe_data = models.JSONField("비민감 요약", default=dict, blank=True)
    created_at = models.DateTimeField("기록 시각", auto_now_add=True)

    class Meta:
        ordering = ("row_number", "id")
        indexes = [
            models.Index(fields=("batch", "action"), name="import_row_action_idx"),
        ]
        verbose_name = "데이터 이전 행 결과"
        verbose_name_plural = "데이터 이전 행 결과"

    def __str__(self) -> str:
        return f"{self.row_number}행 · {self.get_action_display()}"


class LegacyObjectMap(models.Model):
    """기존 LMS 식별값과 신규 EduTrack 객체를 연결해 중복 이전을 방지합니다."""

    class ObjectType(models.TextChoices):
        ASSIGNMENT = "ASSIGNMENT", "과제"

    source_system = models.CharField("원본 시스템", max_length=50, default="LEGACY_LMS")
    object_type = models.CharField("객체 종류", max_length=30, choices=ObjectType.choices)
    external_key = models.CharField("기존 식별값", max_length=255)
    target_object_id = models.PositiveBigIntegerField("신규 객체 ID")
    import_batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_maps",
        verbose_name="최초 이전 작업",
    )
    created_at = models.DateTimeField("연결 생성일", auto_now_add=True)
    updated_at = models.DateTimeField("연결 수정일", auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("source_system", "object_type", "external_key"),
                name="unique_legacy_object_map",
            )
        ]
        indexes = [
            models.Index(
                fields=("object_type", "external_key"),
                name="legacy_object_lookup_idx",
            )
        ]
        verbose_name = "기존 객체 연결"
        verbose_name_plural = "기존 객체 연결"

    def __str__(self) -> str:
        return f"{self.object_type}:{self.external_key} → {self.target_object_id}"
