from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone


def _safe_filename(filename: str) -> str:
    return f"{uuid4().hex}{Path(filename).suffix.lower()}"


def discussion_upload_path(instance, filename: str) -> str:
    return f"learning/discussions/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


def discussion_comment_upload_path(instance, filename: str) -> str:
    return f"learning/discussion-comments/{timezone.localdate():%Y/%m}/{_safe_filename(filename)}"


class LearningGroup(models.Model):
    title = models.CharField("그룹명", max_length=120)
    description = models.CharField("설명", max_length=255, blank=True)
    # 시즌(예: 26FW, 2627WT). 반 목록에서 Term 으로 거릅니다(운영팀 10/29).
    term = models.CharField("Term", max_length=60, blank=True, db_index=True)  # 11/20: 인트라넷 Term 이름(예: 2026 가을 정규)
    sort_order = models.PositiveIntegerField("정렬 순서", default=0, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_learning_groups",
        verbose_name="등록자",
    )
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("sort_order", "title", "id")
        verbose_name = "학습 그룹"
        verbose_name_plural = "학습 그룹"

    def __str__(self) -> str:
        return self.title


class Discussion(models.Model):
    group = models.ForeignKey(
        LearningGroup,
        on_delete=models.SET_NULL,
        related_name="discussions",
        null=True,
        blank=True,
        verbose_name="그룹",
    )
    title = models.CharField("토론 제목", max_length=200)
    content = models.TextField("토론 안내")
    attachment = models.FileField(
        "첨부파일",
        upload_to=discussion_upload_path,
        blank=True,
    )
    available_from = models.DateTimeField("공개 시작", null=True, blank=True, db_index=True)
    due_at = models.DateTimeField("댓글 마감", db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_discussions",
        verbose_name="등록자",
    )
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "토론"
        verbose_name_plural = "토론"

    @property
    def is_available(self) -> bool:
        return bool(
            self.is_published
            and (self.available_from is None or self.available_from <= timezone.now())
        )

    @property
    def is_closed(self) -> bool:
        return self.due_at < timezone.now()

    @property
    def can_comment(self) -> bool:
        return self.is_available and not self.is_closed

    def __str__(self) -> str:
        return self.title


class DiscussionRecipient(models.Model):
    discussion = models.ForeignKey(
        Discussion,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="토론",
    )
    student_id = models.CharField("학생번호", max_length=50, db_index=True)
    student_name = models.CharField("학생명", max_length=100)
    created_at = models.DateTimeField("배정일", auto_now_add=True)

    class Meta:
        ordering = ("student_name", "student_id")
        constraints = [
            models.UniqueConstraint(
                fields=("discussion", "student_id"),
                name="uniq_discussion_recipient",
            )
        ]
        indexes = [
            models.Index(
                fields=("student_id", "discussion"),
                name="discussion_recipient_lookup",
            )
        ]
        verbose_name = "토론 대상 학생"
        verbose_name_plural = "토론 대상 학생"

    def __str__(self) -> str:
        return f"{self.discussion.title} · {self.student_name}"


class DiscussionComment(models.Model):
    discussion = models.ForeignKey(
        Discussion,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="토론",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="discussion_comments",
        verbose_name="작성자",
    )
    student_id = models.CharField("학생번호", max_length=50, blank=True, db_index=True)
    content = models.TextField("댓글")
    attachment = models.FileField(
        "첨부파일",
        upload_to=discussion_comment_upload_path,
        blank=True,
    )
    created_at = models.DateTimeField("작성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "토론 댓글"
        verbose_name_plural = "토론 댓글"

    def __str__(self) -> str:
        return f"{self.discussion.title} · {self.author.effective_name}"


class Quiz(models.Model):
    group = models.ForeignKey(
        LearningGroup,
        on_delete=models.SET_NULL,
        related_name="quizzes",
        null=True,
        blank=True,
        verbose_name="그룹",
    )
    title = models.CharField("퀴즈 제목", max_length=200)
    description = models.TextField("안내", blank=True)
    available_from = models.DateTimeField("응시 시작", null=True, blank=True, db_index=True)
    due_at = models.DateTimeField("응시 마감", db_index=True)
    time_limit_minutes = models.PositiveIntegerField("제한 시간(분)", default=30)
    max_attempts = models.PositiveSmallIntegerField("최대 응시 횟수", default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_quizzes",
        verbose_name="등록자",
    )
    is_published = models.BooleanField("학생 공개", default=True, db_index=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "퀴즈"
        verbose_name_plural = "퀴즈"

    @property
    def is_available(self) -> bool:
        return bool(
            self.is_published
            and (self.available_from is None or self.available_from <= timezone.now())
        )

    @property
    def is_closed(self) -> bool:
        return self.due_at < timezone.now()

    @property
    def can_attempt(self) -> bool:
        return self.is_available and not self.is_closed

    @property
    def total_points(self) -> int:
        return sum(question.points for question in self.questions.all())

    def __str__(self) -> str:
        return self.title


class QuizRecipient(models.Model):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="recipients",
        verbose_name="퀴즈",
    )
    student_id = models.CharField("학생번호", max_length=50, db_index=True)
    student_name = models.CharField("학생명", max_length=100)
    created_at = models.DateTimeField("배정일", auto_now_add=True)

    class Meta:
        ordering = ("student_name", "student_id")
        constraints = [
            models.UniqueConstraint(
                fields=("quiz", "student_id"),
                name="uniq_quiz_recipient",
            )
        ]
        indexes = [
            models.Index(
                fields=("student_id", "quiz"),
                name="quiz_recipient_lookup",
            )
        ]
        verbose_name = "퀴즈 대상 학생"
        verbose_name_plural = "퀴즈 대상 학생"

    def __str__(self) -> str:
        return f"{self.quiz.title} · {self.student_name}"


class QuizQuestion(models.Model):
    class Type(models.TextChoices):
        # Canvas 퀴즈 7가지(Canvas 퀴즈 형식 순서) + 예전 단답형. 채점·검증은 apps/learning/quiz_types.py
        CATEGORIZATION = "CATEGORY", "범주화"
        MULTIPLE_CHOICE = "MCQ", "객관식"
        MULTIPLE_ANSWERS = "MULTI", "복수 응답"
        FILL_IN_BLANK = "FILL", "빈칸 채우기"
        ORDERING = "ORDER", "순서 맞추기"
        MATCHING = "MATCH", "짝 맞추기"
        TRUE_FALSE = "TF", "참/거짓"
        SHORT_ANSWER = "SHORT", "단답형"

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="퀴즈",
    )
    question_type = models.CharField(
        "문항 유형",
        max_length=10,
        choices=Type.choices,
        default=Type.MULTIPLE_CHOICE,
    )
    prompt = models.TextField("문항")
    points = models.PositiveIntegerField("배점", default=1)
    order = models.PositiveIntegerField("문항 순서", default=1, db_index=True)
    correct_text = models.CharField("단답 정답", max_length=255, blank=True)
    # 빈칸·순서·짝·범주화의 정답 구성. 객관식·복수 응답·참/거짓은 QuizChoice 를 씁니다.
    config = models.JSONField("유형별 정답 구성", default=dict, blank=True)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "퀴즈 문항"
        verbose_name_plural = "퀴즈 문항"

    def __str__(self) -> str:
        return f"{self.quiz.title} · {self.order}번"


class QuizChoice(models.Model):
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="choices",
        verbose_name="문항",
    )
    text = models.CharField("선택지", max_length=500)
    is_correct = models.BooleanField("정답", default=False)
    order = models.PositiveIntegerField("순서", default=1)

    class Meta:
        ordering = ("order", "id")
        verbose_name = "퀴즈 선택지"
        verbose_name_plural = "퀴즈 선택지"

    def __str__(self) -> str:
        return self.text


class QuizAttempt(models.Model):
    recipient = models.ForeignKey(
        QuizRecipient,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name="퀴즈 대상",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="quiz_attempts",
        verbose_name="응시 계정",
    )
    attempt_no = models.PositiveSmallIntegerField("응시 회차")
    started_at = models.DateTimeField("시작 시각", default=timezone.now)
    submitted_at = models.DateTimeField("제출 시각", null=True, blank=True)
    score = models.DecimalField("점수", max_digits=8, decimal_places=2, default=0)
    max_score = models.DecimalField("총점", max_digits=8, decimal_places=2, default=0)

    manual_score = models.DecimalField("강사 조정 점수", max_digits=8, decimal_places=2, null=True, blank=True)
    feedback = models.TextField("강사 총평", blank=True)
    feedback_at = models.DateTimeField(null=True, blank=True)
    feedback_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="quiz_reviews")

    @property
    def final_score(self):
        return self.manual_score if self.manual_score is not None else self.score

    class Meta:
        ordering = ("-attempt_no", "-started_at")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "attempt_no"),
                name="uniq_quiz_recipient_attempt",
            )
        ]
        verbose_name = "퀴즈 응시"
        verbose_name_plural = "퀴즈 응시"

    def __str__(self) -> str:
        return f"{self.recipient.student_name} · {self.recipient.quiz.title} · {self.attempt_no}회"


class QuizAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="응시",
    )
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
        verbose_name="문항",
    )
    selected_choice = models.ForeignKey(
        QuizChoice,
        on_delete=models.SET_NULL,
        related_name="selected_answers",
        null=True,
        blank=True,
        verbose_name="선택 답안",
    )
    text_answer = models.CharField("단답 답안", max_length=500, blank=True)
    # 유형별 답안(복수 응답 고른 보기, 빈칸 답, 순서, 짝, 범주). 예전 답안은 비어 있고 selected_choice·text_answer 를 씁니다.
    response = models.JSONField("유형별 답안", default=dict, blank=True)
    earned_points = models.DecimalField("획득 점수", max_digits=8, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "question"),
                name="uniq_quiz_attempt_question",
            )
        ]
        verbose_name = "퀴즈 답안"
        verbose_name_plural = "퀴즈 답안"

    def __str__(self) -> str:
        return f"{self.attempt} · {self.question.order}번"
