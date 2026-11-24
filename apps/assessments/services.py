from __future__ import annotations

import logging
from dataclasses import replace
from statistics import mean

from django.db import DatabaseError

from .contracts import (
    ExamAttemptSummary,
    ScoreChartPoint,
    StudentExamOverview,
)
from .repositories import (
    AssessmentRepository,
    get_assessment_repository,
)

logger = logging.getLogger(__name__)
MODULE_ATTEMPT_LIMIT = 10


class AssessmentService:
    """학생의 DSG 시험 결과와 요약지표를 계산합니다."""

    def __init__(
        self,
        repository: AssessmentRepository | None = None,
    ) -> None:
        self.repository = (
            repository
            or get_assessment_repository()
        )

    def get_student_overview(
        self,
        intranet_student_id: str,
    ) -> StudentExamOverview:
        profile = (
            self.repository.get_student_profile(
                intranet_student_id
            )
        )

        if profile.status != "ok":
            messages = {
                "disabled": (
                    "DSG 성적 기능이 비활성화되어 있습니다."
                ),
                "not_found": (
                    "인트라넷 학생 정보를 찾지 못했습니다."
                ),
                "not_connected": (
                    "이 학생은 DSG 계정이 연결되지 않았습니다."
                ),
                "mapping_not_found": (
                    "인트라넷 dsg_id와 일치하는 DSG 학생을 찾지 못했습니다."
                ),
            }

            return StudentExamOverview(
                status=profile.status,
                message=messages.get(
                    profile.status,
                    "DSG 학생 연결 상태를 확인해 주세요.",
                ),
            )

        attempts = (
            self.repository.list_exam_attempts(
                profile.dsg_student_id
            )
        )
        module_attempts = self._recent_module_attempts(
            profile.dsg_student_id
        )

        if not attempts:
            return StudentExamOverview(
                status="empty",
                message=(
                    "완료된 DSG 시험 결과가 없습니다."
                ),
                dsg_student_id=(
                    profile.dsg_student_id
                ),
                dsg_student_name=profile.name,
                dsg_school_name=profile.school,
                dsg_grade=profile.grade,
                matched_field=(
                    profile.matched_field
                ),
                module_attempts=module_attempts,
            )

        attempts_with_delta = (
            self._attach_previous_delta(
                attempts
            )
        )

        full_attempts = [
            attempt
            for attempt in attempts_with_delta
            if (
                attempt.score_type == "FULL"
                and attempt.total_sat_score
                is not None
            )
        ]

        latest_full = (
            full_attempts[-1]
            if full_attempts
            else None
        )

        total_scores = [
            attempt.total_sat_score
            for attempt in full_attempts
            if attempt.total_sat_score
            is not None
        ]

        average_total_score = (
            mean(total_scores)
            if total_scores
            else None
        )

        highest_total_score = (
            max(total_scores)
            if total_scores
            else None
        )

        recent_three_scores = (
            total_scores[-3:]
        )

        recent_three_average = (
            mean(recent_three_scores)
            if recent_three_scores
            else None
        )

        first_delta = None
        previous_delta = None

        if len(total_scores) >= 2:
            first_delta = (
                total_scores[-1]
                - total_scores[0]
            )
            previous_delta = (
                total_scores[-1]
                - total_scores[-2]
            )

        total_questions = sum(
            attempt.total_questions
            for attempt in attempts_with_delta
            if attempt.total_questions > 0
        )

        correct_answers = sum(
            attempt.correct_answers
            for attempt in attempts_with_delta
            if attempt.total_questions > 0
        )

        overall_accuracy = (
            correct_answers
            / total_questions
            * 100
            if total_questions > 0
            else None
        )

        chart_points, chart_polyline = (
            self._build_chart(
                full_attempts[-8:]
            )
        )

        return StudentExamOverview(
            status="ok",
            dsg_student_id=(
                profile.dsg_student_id
            ),
            dsg_student_name=profile.name,
            dsg_school_name=profile.school,
            dsg_grade=profile.grade,
            matched_field=(
                profile.matched_field
            ),
            exam_count=len(
                attempts_with_delta
            ),
            full_sat_count=len(
                full_attempts
            ),
            latest_total_score=(
                latest_full.total_sat_score
                if latest_full
                else None
            ),
            latest_rw_score=(
                latest_full.rw_sat_score
                if latest_full
                else None
            ),
            latest_math_score=(
                latest_full.math_sat_score
                if latest_full
                else None
            ),
            average_total_score=(
                average_total_score
            ),
            highest_total_score=(
                highest_total_score
            ),
            recent_three_average=(
                recent_three_average
            ),
            first_delta=first_delta,
            previous_delta=previous_delta,
            overall_accuracy=(
                overall_accuracy
            ),
            recent_attempts=tuple(
                reversed(
                    attempts_with_delta[-6:]
                )
            ),
            chart_points=tuple(
                chart_points
            ),
            chart_polyline=chart_polyline,
            module_attempts=module_attempts,
        )

    def _recent_module_attempts(self, dsg_student_id: str) -> tuple:
        """Module만 따로 본 시험을 최근 순으로. 읽지 못해도 Exam 성적은 그대로 보이게 빈 목록을 돌려줍니다."""
        try:
            rows = self.repository.list_module_attempts(dsg_student_id)
        except DatabaseError as exc:
            logger.warning("dsg_module_attempts_unavailable type=%s", type(exc).__name__)
            return ()
        return tuple(reversed(rows[-MODULE_ATTEMPT_LIMIT:]))

    @staticmethod
    def _attach_previous_delta(
        attempts: list[
            ExamAttemptSummary
        ],
    ) -> list[ExamAttemptSummary]:
        previous_by_type: dict[
            str,
            int,
        ] = {}

        result: list[
            ExamAttemptSummary
        ] = []

        for attempt in attempts:
            delta_previous = None

            if (
                attempt.display_score
                is not None
                and attempt.score_type
                in previous_by_type
            ):
                delta_previous = (
                    attempt.display_score
                    - previous_by_type[
                        attempt.score_type
                    ]
                )

            result.append(
                replace(
                    attempt,
                    delta_previous=(
                        delta_previous
                    ),
                )
            )

            if attempt.display_score is not None:
                previous_by_type[
                    attempt.score_type
                ] = attempt.display_score

        return result

    @staticmethod
    def _build_chart(
        full_attempts: list[
            ExamAttemptSummary
        ],
    ) -> tuple[
        list[ScoreChartPoint],
        str,
    ]:
        if not full_attempts:
            return [], ""

        count = len(full_attempts)

        if count == 1:
            x_values = [50.0]
        else:
            x_values = [
                8.0
                + (
                    index
                    * 84.0
                    / (count - 1)
                )
                for index in range(count)
            ]

        points: list[
            ScoreChartPoint
        ] = []

        for x, attempt in zip(
            x_values,
            full_attempts,
        ):
            score = (
                attempt.total_sat_score
                or 400
            )

            bounded_score = max(
                400,
                min(1600, score),
            )

            y = (
                88.0
                - (
                    (bounded_score - 400)
                    / 1200
                    * 76.0
                )
            )

            date_label = (
                attempt.exam_date.strftime(
                    "%m.%d"
                )
                if attempt.exam_date
                else "-"
            )

            points.append(
                ScoreChartPoint(
                    x=round(x, 2),
                    y=round(y, 2),
                    score=score,
                    exam_name=(
                        attempt.exam_name
                    ),
                    exam_date_label=(
                        date_label
                    ),
                )
            )

        polyline = " ".join(
            f"{point.x},{point.y}"
            for point in points
        )

        return points, polyline
