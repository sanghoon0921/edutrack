from time import perf_counter

from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError

from apps.assessments.detail_services import (
    ExamDetailService,
)


class Command(BaseCommand):
    help = "시험 상세의 최초 조회와 캐시 조회 시간을 비교합니다."

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
        student_no = options["student_no"]
        attempt_id = options["attempt_id"]

        service = ExamDetailService()

        try:
            started = perf_counter()

            cold_detail = service.get_attempt_detail(
                student_no,
                attempt_id,
                force_refresh=True,
            )

            cold_seconds = (
                perf_counter()
                - started
            )

            started = perf_counter()

            warm_detail = service.get_attempt_detail(
                student_no,
                attempt_id,
            )

            warm_seconds = (
                perf_counter()
                - started
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "성능 측정 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        self.stdout.write(
            f"상태: {cold_detail.status}"
        )
        self.stdout.write(
            f"문항 수: {len(cold_detail.questions)}"
        )
        self.stdout.write(
            f"최초 DB 조회: {cold_seconds:.3f}초"
        )
        self.stdout.write(
            f"캐시 조회: {warm_seconds:.4f}초"
        )

        if (
            warm_detail.status
            == cold_detail.status
        ):
            self.stdout.write(
                self.style.SUCCESS(
                    "캐시 결과 일치"
                )
            )
