from django.conf import settings
from django.db import models


class ReportBatch(models.Model):
    """한 반·한 양식·한 기간의 리포트카드 묶음. 반 공통 글(shared)은 여기에 한 번만 저장합니다."""

    group = models.ForeignKey("learning.LearningGroup", on_delete=models.CASCADE, related_name="report_batches", verbose_name="반")
    form = models.CharField("양식", max_length=20)
    title = models.CharField("제목", max_length=60)
    period_start = models.DateField("기간 시작")
    period_end = models.DateField("기간 끝")
    week_base = models.DateField("1주차 시작일")
    course_class_id = models.CharField("인트라넷 수업 번호", max_length=40, blank=True)
    course_label = models.CharField("인트라넷 수업", max_length=200, blank=True)
    shared = models.JSONField("반 공통 글", default=dict, blank=True)
    # '학생·학부모에게 공개'를 누른 때. 비어 있으면 강사·관리자만 봅니다(작성 중).
    published_at = models.DateTimeField("공개", null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-period_end", "-pk")
        verbose_name = "리포트카드 묶음"
        verbose_name_plural = "리포트카드 묶음"

    def __str__(self) -> str:
        return f"{self.group} · {self.form} · {self.period_start}~{self.period_end}"


class ReportCard(models.Model):
    """학생 한 명의 리포트카드. data = 화면에 보이는 값(자동+손으로 쓴 값), auto = 마지막으로 불러온 자동 값."""

    batch = models.ForeignKey(ReportBatch, on_delete=models.CASCADE, related_name="cards")
    student_no = models.CharField("학생번호", max_length=50)
    student_name = models.CharField("학생명", max_length=100)
    data = models.JSONField(default=dict, blank=True)
    auto = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
    # 편집 화면에서 처음 저장한 때(11/10). 비어 있으면 '작성 전'이라 목록의 '열기'가 바로 수정 화면입니다.
    saved_at = models.DateTimeField("처음 저장", null=True, blank=True)

    class Meta:
        ordering = ("student_name", "student_no")
        constraints = [models.UniqueConstraint(fields=("batch", "student_no"), name="reports_unique_batch_student")]

    def __str__(self) -> str:
        return f"{self.student_name} · {self.batch}"
