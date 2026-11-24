# Generated for EduTrack Stage 14.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.content_editor.models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PastedImage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="본문 토큰")),
                ("image", models.FileField(upload_to=apps.content_editor.models.pasted_image_upload_path, verbose_name="이미지")),
                ("original_name", models.CharField(max_length=255, verbose_name="원본 파일명")),
                ("content_type", models.CharField(max_length=100, verbose_name="콘텐츠 형식")),
                ("size", models.PositiveBigIntegerField(default=0, verbose_name="파일 크기")),
                ("target_type", models.CharField(choices=[("DRAFT", "작성 중"), ("NOTICE", "공지"), ("ASSIGNMENT", "과제"), ("DISCUSSION", "토론")], db_index=True, default="DRAFT", max_length=20, verbose_name="연결 대상")),
                ("target_id", models.PositiveBigIntegerField(blank=True, db_index=True, null=True, verbose_name="연결 대상 번호")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="업로드 시각")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="수정 시각")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pasted_images", to=settings.AUTH_USER_MODEL, verbose_name="업로드 계정")),
            ],
            options={
                "verbose_name": "붙여넣기 본문 이미지",
                "verbose_name_plural": "붙여넣기 본문 이미지",
                "ordering": ("created_at", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="pastedimage",
            index=models.Index(fields=["owner", "target_type", "target_id"], name="pasted_owner_target_idx"),
        ),
    ]
