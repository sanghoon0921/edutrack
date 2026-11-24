from __future__ import annotations

from django.core.management.base import (
    BaseCommand,
)
from django.db.utils import DatabaseError

from apps.assessments.detail_services import (
    ExamDetailService,
)
from apps.assessments.insight_services import (
    ExamInsightService,
)


class Command(BaseCommand):
    help = (
        "시험 상세 캐시 데이터를 이용해 "
        "영역별 인사이트를 확인합니다."
    )

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
        try:
            detail = (
                ExamDetailService()
                .get_attempt_detail(
                    options["student_no"],
                    options["attempt_id"],
                )
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "시험 인사이트 조회 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        if detail.status != "ok":
            self.stdout.write(
                f"상태: {detail.status}"
            )
            self.stdout.write(
                detail.message
            )
            return

        insight = ExamInsightService().build(
            detail.questions
        )

        self.stdout.write(
            self.style.SUCCESS(
                "시험 인사이트 계산 성공"
            )
        )

        self.stdout.write(
            f"전체 문항: {insight.total_count}"
        )
        self.stdout.write(
            f"복습 필요: {insight.review_count}"
        )
        self.stdout.write(
            f"느린 문항: {insight.slow_count}"
        )

        if insight.strongest_area:
            self.stdout.write(
                "강점 영역: "
                f"{insight.strongest_area.name}"
                " | "
                f"{insight.strongest_area.accuracy_rate:.1f}%"
            )

        if insight.priority_area:
            self.stdout.write(
                "우선 복습: "
                f"{insight.priority_area.name}"
                " | "
                f"{insight.priority_area.accuracy_rate:.1f}%"
            )

        if insight.slowest_area:
            self.stdout.write(
                "가장 느린 영역: "
                f"{insight.slowest_area.name}"
                " | 평균 "
                f"{insight.slowest_area.average_duration_label}"
            )

        self.stdout.write("")
        self.stdout.write("영역별 분석")

        for area in insight.area_insights:
            accuracy_text = (
                f"{area.accuracy_rate:.1f}%"
                if area.accuracy_rate
                is not None
                else "-"
            )

            self.stdout.write(
                (
                    f"- {area.name}"
                    f" | {area.question_count}문항"
                    f" | 획득률 {accuracy_text}"
                    f" | 복습 {area.review_count}"
                    f" | 평균 {area.average_duration_label}"
                )
            )
