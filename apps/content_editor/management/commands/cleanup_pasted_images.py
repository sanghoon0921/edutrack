from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.content_editor.models import PastedImage


class Command(BaseCommand):
    help = "저장되지 않은 오래된 붙여넣기 이미지를 삭제합니다."

    def handle(self, *args, **options):
        hours = max(1, int(getattr(settings, "PASTED_IMAGE_DRAFT_TTL_HOURS", 48)))
        cutoff = timezone.now() - timedelta(hours=hours)
        queryset = PastedImage.objects.filter(
            target_type=PastedImage.TargetType.DRAFT,
            created_at__lt=cutoff,
        )
        count = queryset.count()
        for image in queryset.iterator():
            image.delete()
        self.stdout.write(self.style.SUCCESS(f"오래된 작성 중 이미지 {count}개를 정리했습니다."))
