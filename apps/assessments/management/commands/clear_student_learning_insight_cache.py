from django.core.management.base import BaseCommand

from apps.assessments.cumulative_services import (
    StudentLearningInsightService,
)


class Command(BaseCommand):
    help = "학생 누적 학습 인사이트 캐시를 삭제합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "student_no",
            type=str,
        )

    def handle(self, *args, **options):
        StudentLearningInsightService().clear_cache(
            options["student_no"]
        )

        self.stdout.write(
            self.style.SUCCESS(
                "누적 학습 인사이트 캐시 삭제 완료"
            )
        )
