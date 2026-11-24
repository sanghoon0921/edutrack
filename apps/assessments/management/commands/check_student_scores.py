from __future__ import annotations

from django.core.management.base import (
    BaseCommand,
)
from django.db.utils import DatabaseError

from apps.assessments.services import (
    AssessmentService,
)


class Command(BaseCommand):
    help = (
        "인트라넷 학생번호 기준으로 "
        "DSG 시험 점수 요약을 확인합니다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "student_no",
            type=str,
            help="인트라넷 student_info.student_no",
        )

    def handle(self, *args, **options):
        student_no = (
            options["student_no"].strip()
        )

        try:
            overview = (
                AssessmentService()
                .get_student_overview(
                    student_no
                )
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "DSG 성적 조회 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        self.stdout.write(
            f"상태: {overview.status}"
        )

        if overview.status != "ok":
            self.stdout.write(
                overview.message
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "DSG 성적 조회 성공"
            )
        )
        self.stdout.write(
            f"DSG student_id: "
            f"{overview.dsg_student_id}"
        )
        self.stdout.write(
            f"매핑 컬럼: "
            f"{overview.matched_field or '-'}"
        )
        self.stdout.write(
            f"전체 시험: {overview.exam_count}회"
        )
        self.stdout.write(
            f"전체 SAT: "
            f"{overview.full_sat_count}회"
        )
        self.stdout.write(
            f"최근 총점: "
            f"{overview.latest_total_score or '-'}"
        )
        self.stdout.write(
            f"최근 RW: "
            f"{overview.latest_rw_score or '-'}"
        )
        self.stdout.write(
            f"최근 Math: "
            f"{overview.latest_math_score or '-'}"
        )
        self.stdout.write(
            (
                "평균 총점: "
                f"{overview.average_total_score:.1f}"
                if overview.average_total_score
                is not None
                else "평균 총점: -"
            )
        )
        self.stdout.write(
            f"최고 총점: "
            f"{overview.highest_total_score or '-'}"
        )
        self.stdout.write(
            (
                "전체 정답률: "
                f"{overview.overall_accuracy:.1f}%"
                if overview.overall_accuracy
                is not None
                else "전체 정답률: -"
            )
        )
        self.stdout.write("")
        self.stdout.write("최근 시험")

        for attempt in (
            overview.recent_attempts
        ):
            date_text = (
                attempt.exam_date.strftime(
                    "%Y-%m-%d"
                )
                if attempt.exam_date
                else "-"
            )

            self.stdout.write(
                (
                    f"- {date_text}"
                    f" | {attempt.exam_name}"
                    f" | {attempt.score_type_label}"
                    f" | {attempt.display_score or '-'}"
                    f"/{attempt.max_score}"
                )
            )
