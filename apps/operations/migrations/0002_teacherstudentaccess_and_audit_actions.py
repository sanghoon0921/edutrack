from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("USER_CREATED", "계정 생성"),
                    ("USER_UPDATED", "계정 수정"),
                    ("PROFILE_UPDATED", "내 정보 수정"),
                    ("PASSWORD_RESET", "비밀번호 변경"),
                    ("LINK_ADDED", "학생 연결 추가"),
                    ("LINK_PRIMARY", "대표 학생 변경"),
                    ("LINK_DEACTIVATED", "학생 연결 해제"),
                    ("TEACHER_STUDENT_ADDED", "담당 학생 배정"),
                    ("TEACHER_STUDENT_REMOVED", "담당 학생 해제"),
                ],
                db_index=True,
                max_length=40,
                verbose_name="작업",
            ),
        ),
        migrations.CreateModel(
            name="TeacherStudentAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("student_no", models.CharField(db_index=True, max_length=50, verbose_name="학생번호")),
                ("student_name", models.CharField(blank=True, max_length=100, verbose_name="학생명")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="배정 활성")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="배정일")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정일")),
                ("assigned_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_teacher_student_accesses", to=settings.AUTH_USER_MODEL, verbose_name="배정 관리자")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teacher_student_accesses", to=settings.AUTH_USER_MODEL, verbose_name="강사")),
            ],
            options={
                "verbose_name": "강사 담당 학생",
                "verbose_name_plural": "강사 담당 학생",
                "ordering": ("student_name", "student_no"),
            },
        ),
        migrations.AddConstraint(
            model_name="teacherstudentaccess",
            constraint=models.UniqueConstraint(fields=("teacher", "student_no"), name="uniq_teacher_student_access"),
        ),
        migrations.AddIndex(
            model_name="teacherstudentaccess",
            index=models.Index(fields=["teacher", "is_active", "student_no"], name="teacher_student_scope_idx"),
        ),
    ]
