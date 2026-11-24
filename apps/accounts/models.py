from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "관리자"
        TEACHER = "TEACHER", "강사"
        TA = "TA", "TA(조교)"  # 11/10: 강사보다 낮은 권한. 11/19부터 맡은 반 학생·반별 학습·리포트카드 작성(발송 불가)·메신저
        STUDENT = "STUDENT", "학생"
        PARENT = "PARENT", "학부모"

    role = models.CharField(
        "역할",
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        db_index=True,
    )
    display_name = models.CharField(
        "표시 이름",
        max_length=60,
        blank=True,
    )
    # 운영팀 11/17: 관리자가 만든 학생 계정은 첫 로그인 때 비밀번호를 바꾸고 이메일(필수)·DSG ID를 적습니다.
    # 인트라넷 DB는 EduTrack이 쓰지 않으므로(조회 전용), 적은 값은 '인트라넷 반영 목록'에서 운영팀이 옮겨 넣습니다.
    needs_first_setup = models.BooleanField("첫 로그인 설정 필요", default=False)
    dsg_login_id = models.CharField("DSG ID", max_length=80, blank=True)
    first_setup_at = models.DateTimeField("첫 로그인 설정한 때", null=True, blank=True)
    intranet_synced_at = models.DateTimeField("인트라넷 반영 확인한 때", null=True, blank=True)

    @property
    def effective_name(self) -> str:
        return (
            self.display_name
            or self.get_full_name()
            or self.username
        )

    @property
    def chat_name(self) -> str:
        """메신저에 보이는 이름. 학생은 '이름 · 학생번호'(대표 학생번호, 예: 김지훈D · 6333)."""
        if self.role != self.Role.STUDENT:
            return self.effective_name
        # student_links 를 미리 불러왔으면(prefetch) 그대로 쓰고, 아니면 한 번 조회한다.
        links = sorted((link for link in self.student_links.all() if link.is_active), key=lambda link: (not link.is_primary, link.pk))
        return f"{self.effective_name} · {links[0].student_no}" if links else self.effective_name

    def __str__(self) -> str:
        return self.effective_name


class StudentAccountLink(models.Model):
    """EduTrack 계정과 인트라넷 학생번호를 연결합니다."""

    class Relationship(models.TextChoices):
        SELF = "SELF", "본인"
        PARENT = "PARENT", "학부모"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_links",
        verbose_name="사용자",
    )
    student_no = models.CharField(
        "학생번호",
        max_length=50,
        db_index=True,
    )
    relationship = models.CharField(
        "관계",
        max_length=20,
        choices=Relationship.choices,
    )
    is_primary = models.BooleanField(
        "대표 학생",
        default=True,
    )
    is_active = models.BooleanField(
        "활성",
        default=True,
    )
    created_at = models.DateTimeField(
        "생성일",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "수정일",
        auto_now=True,
    )

    class Meta:
        ordering = (
            "user__username",
            "-is_primary",
            "id",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("user", "student_no"),
                name="unique_user_student_link",
            ),
        ]
        indexes = [
            models.Index(
                fields=("student_no", "is_active"),
                name="student_link_active_idx",
            ),
        ]
        verbose_name = "계정-학생 연결"
        verbose_name_plural = "계정-학생 연결"

    def __str__(self) -> str:
        return (
            f"{self.user.username} → {self.student_no} "
            f"({self.get_relationship_display()})"
        )
