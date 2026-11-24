from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.assignments.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(
            settings.AUTH_USER_MODEL
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="Assignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        max_length=200,
                        verbose_name="과제 제목",
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        verbose_name="과제 내용",
                    ),
                ),
                (
                    "due_at",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="마감일",
                    ),
                ),
                (
                    "attachment",
                    models.FileField(
                        blank=True,
                        upload_to=(
                            apps.assignments.models
                            .assignment_upload_path
                        ),
                        verbose_name="과제 첨부파일",
                    ),
                ),
                (
                    "is_published",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                        verbose_name="학생 공개",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="등록일",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="수정일",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models
                            .deletion.PROTECT
                        ),
                        related_name=(
                            "created_assignments"
                        ),
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="등록자",
                    ),
                ),
            ],
            options={
                "verbose_name": "과제",
                "verbose_name_plural": "과제",
                "ordering": (
                    "-created_at",
                    "-id",
                ),
            },
        ),
        migrations.CreateModel(
            name="AssignmentRecipient",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "student_id",
                    models.CharField(
                        db_index=True,
                        max_length=50,
                        verbose_name="학생번호",
                    ),
                ),
                (
                    "student_name",
                    models.CharField(
                        max_length=100,
                        verbose_name="학생명",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name="배정일",
                    ),
                ),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models
                            .deletion.CASCADE
                        ),
                        related_name="recipients",
                        to="assignments.assignment",
                        verbose_name="과제",
                    ),
                ),
            ],
            options={
                "verbose_name": (
                    "과제 대상 학생"
                ),
                "verbose_name_plural": (
                    "과제 대상 학생"
                ),
                "ordering": (
                    "student_name",
                    "student_id",
                ),
            },
        ),
        migrations.CreateModel(
            name="Submission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "text_answer",
                    models.TextField(
                        blank=True,
                        verbose_name="텍스트 답안",
                    ),
                ),
                (
                    "attachment",
                    models.FileField(
                        blank=True,
                        upload_to=(
                            apps.assignments.models
                            .submission_upload_path
                        ),
                        verbose_name="제출파일",
                    ),
                ),
                (
                    "submitted_at",
                    models.DateTimeField(
                        blank=True,
                        db_index=True,
                        null=True,
                        verbose_name="제출일",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name="수정일",
                    ),
                ),
                (
                    "feedback",
                    models.TextField(
                        blank=True,
                        verbose_name="강사 피드백",
                    ),
                ),
                (
                    "feedback_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="피드백 작성일",
                    ),
                ),
                (
                    "feedback_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=(
                            django.db.models
                            .deletion.SET_NULL
                        ),
                        related_name=(
                            "reviewed_submissions"
                        ),
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="피드백 작성자",
                    ),
                ),
                (
                    "recipient",
                    models.OneToOneField(
                        on_delete=(
                            django.db.models
                            .deletion.CASCADE
                        ),
                        related_name="submission",
                        to=(
                            "assignments."
                            "assignmentrecipient"
                        ),
                        verbose_name="과제 대상",
                    ),
                ),
            ],
            options={
                "verbose_name": "과제 제출",
                "verbose_name_plural": (
                    "과제 제출"
                ),
                "ordering": (
                    "-submitted_at",
                    "-updated_at",
                ),
            },
        ),
        migrations.AddConstraint(
            model_name=(
                "assignmentrecipient"
            ),
            constraint=(
                models.UniqueConstraint(
                    fields=(
                        "assignment",
                        "student_id",
                    ),
                    name=(
                        "uniq_assignment_recipient"
                    ),
                )
            ),
        ),
        migrations.AddIndex(
            model_name=(
                "assignmentrecipient"
            ),
            index=models.Index(
                fields=(
                    "student_id",
                    "assignment",
                ),
                name=(
                    "assign_recipient_lookup"
                ),
            ),
        ),
    ]
