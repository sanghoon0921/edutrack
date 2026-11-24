from __future__ import annotations

from django.core.management.base import (
    BaseCommand,
)
from django.db.utils import DatabaseError

from apps.assessments.detail_services import (
    ExamDetailService,
)


class Command(BaseCommand):
    help = (
        "학생번호와 시험 응시 ID 기준으로 "
        "시험 문항 상세를 확인합니다."
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
                    options[
                        "student_no"
                    ],
                    options[
                        "attempt_id"
                    ],
                )
            )

        except DatabaseError as error:
            self.stdout.write(
                self.style.ERROR(
                    "시험 상세 조회 실패"
                )
            )
            self.stdout.write(str(error))
            raise

        self.stdout.write(
            f"상태: {detail.status}"
        )

        if detail.status != "ok":
            self.stdout.write(
                detail.message
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "시험 상세 조회 성공"
            )
        )
        self.stdout.write(
            f"학생: {detail.student_name}"
        )
        self.stdout.write(
            f"시험: "
            f"{detail.attempt.exam_name}"
        )
        self.stdout.write(
            f"시험 응시 ID: "
            f"{detail.attempt.attempt_id}"
        )
        self.stdout.write(
            f"exam_id: "
            f"{detail.attempt.exam_id}"
        )
        self.stdout.write(
            f"문항: {len(detail.questions)}개"
        )
        self.stdout.write(
            f"정답 {detail.correct_count}"
            f" | 부분 {detail.partial_count}"
            f" | 오답 {detail.wrong_count}"
            f" | 무응답 {detail.unanswered_count}"
            f" | 직접입력 {detail.free_response_count}"
        )

        for item in detail.questions[:20]:
            self.stdout.write(
                (
                    f"- {item.question_no}번"
                    f" | {item.result_label}"
                    f" | 학생 {item.selected_answer or '-'}"
                    f" | 정답 {item.correct_answer}"
                    f" | {item.earned_score}/{item.max_score}"
                )
            )
