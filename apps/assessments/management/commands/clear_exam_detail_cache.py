from django.core.management.base import BaseCommand

from apps.assessments.detail_services import (
    ExamDetailService,
)


class Command(BaseCommand):
    help = "선택 시험의 5C 상세 캐시를 삭제합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "student_no",
            type=str,
        )
        parser.add_argument(
            "attempt_id",
            type=str,
        )

    def handle(self, *args, **options):
        ExamDetailService().clear_attempt_cache(
            options["student_no"],
            options["attempt_id"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                "시험 상세 캐시 삭제 완료"
            )
        )
