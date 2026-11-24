from django.core.management.base import BaseCommand
from django.db.utils import DatabaseError

from apps.assessments.cumulative_services import (
    StudentLearningInsightService,
)


class Command(BaseCommand):
    help = "학생의 최근 시험 누적 학습 인사이트를 확인합니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "student_no",
            type=str,
        )

    def handle(self, *args, **options):
        try:
            insight = (
                StudentLearningInsightService()
                .get_student_insight(
                    options["student_no"]
                )
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "누적 인사이트 조회 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        self.stdout.write(
            f"상태: {insight.status}"
        )

        if insight.status != "ok":
            self.stdout.write(
                insight.message
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "누적 학습 인사이트 계산 성공"
            )
        )

        self.stdout.write(
            f"분석 시험: {insight.analyzed_exam_count}회"
        )
        self.stdout.write(
            f"누적 문항: {insight.total_question_count}개"
        )
        self.stdout.write(
            f"복습 필요: {insight.review_count}개"
        )

        if insight.overall_accuracy is not None:
            self.stdout.write(
                f"누적 획득률: "
                f"{insight.overall_accuracy:.1f}%"
            )

        self.stdout.write(
            f"평균 풀이시간: "
            f"{insight.average_duration_label}"
        )

        for label, area in (
            ("강점", insight.strongest_area),
            ("우선 학습", insight.priority_area),
            ("향상", insight.improving_area),
            ("하락", insight.declining_area),
            ("시간 병목", insight.slowest_area),
        ):
            if area:
                accuracy = (
                    f"{area.accuracy_rate:.1f}%"
                    if area.accuracy_rate
                    is not None
                    else "-"
                )

                self.stdout.write(
                    f"{label}: "
                    f"{area.name}"
                    f" | {accuracy}"
                )

        self.stdout.write("")
        self.stdout.write("학습 권고")

        for item in insight.recommendations:
            self.stdout.write(
                f"- {item.title}"
            )
            self.stdout.write(
                f"  {item.action}"
            )
