from time import perf_counter

from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError

from apps.assessments.cumulative_services import (
    StudentLearningInsightService,
)


class Command(BaseCommand):
    help = "학생 누적 인사이트의 최초 계산과 캐시 조회 시간을 비교합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "student_no",
            type=str,
        )

    def handle(self, *args, **options):
        service = (
            StudentLearningInsightService()
        )

        try:
            started = perf_counter()

            cold = service.get_student_insight(
                options["student_no"],
                force_refresh=True,
            )

            cold_seconds = (
                perf_counter()
                - started
            )

            started = perf_counter()

            warm = service.get_student_insight(
                options["student_no"]
            )

            warm_seconds = (
                perf_counter()
                - started
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "누적 인사이트 성능 측정 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        self.stdout.write(
            f"상태: {cold.status}"
        )
        self.stdout.write(
            f"분석 시험: {cold.analyzed_exam_count}"
        )
        self.stdout.write(
            f"최초 계산: {cold_seconds:.3f}초"
        )
        self.stdout.write(
            f"캐시 조회: {warm_seconds:.4f}초"
        )

        if cold == warm:
            self.stdout.write(
                self.style.SUCCESS(
                    "캐시 결과 일치"
                )
            )
