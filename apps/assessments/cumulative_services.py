from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from django.conf import settings
from config.cache_utils import safe_cache_delete, safe_cache_get, safe_cache_set

from .cumulative_contracts import (
    AreaTrendPoint,
    CumulativeAreaInsight,
    RecentExamInsight,
    ReviewQueueItem,
    StudentLearningInsight,
    StudyRecommendation,
)
from .detail_services import ExamDetailService
from .insight_services import (
    ExamInsightService,
    REVIEW_CODES,
    SCORED_CODES,
)
from .services import AssessmentService


CACHE_VERSION = "v1"


class StudentLearningInsightService:
    """최근 여러 시험을 합산해 학생별 누적 인사이트를 계산합니다."""

    def __init__(
        self,
        *,
        assessment_service: AssessmentService | None = None,
        detail_service: ExamDetailService | None = None,
        exam_insight_service: ExamInsightService | None = None,
    ) -> None:
        self.assessment_service = (
            assessment_service
            or AssessmentService()
        )
        self.detail_service = (
            detail_service
            or ExamDetailService()
        )
        self.exam_insight_service = (
            exam_insight_service
            or ExamInsightService()
        )

    @staticmethod
    def cache_key(
        student_id: str,
        max_attempts: int,
    ) -> str:
        return (
            "edutrack:student-learning-insight:"
            f"{CACHE_VERSION}:"
            f"{student_id.strip()}:"
            f"{max_attempts}"
        )

    def clear_cache(
        self,
        student_id: str,
        *,
        max_attempts: int | None = None,
    ) -> None:
        attempts = (
            max_attempts
            or int(
                getattr(
                    settings,
                    "STUDENT_INSIGHT_MAX_ATTEMPTS",
                    5,
                )
            )
        )

        safe_cache_delete(
            self.cache_key(
                student_id,
                attempts,
            )
        )

    def get_student_insight(
        self,
        student_id: str,
        *,
        force_refresh: bool = False,
    ) -> StudentLearningInsight:
        cleaned_student_id = (
            student_id.strip()
        )

        max_attempts = max(
            1,
            min(
                8,
                int(
                    getattr(
                        settings,
                        "STUDENT_INSIGHT_MAX_ATTEMPTS",
                        5,
                    )
                ),
            ),
        )

        key = self.cache_key(
            cleaned_student_id,
            max_attempts,
        )

        if not force_refresh:
            cached = safe_cache_get(key)

            if cached is not None:
                return cached

        insight = self._build(
            cleaned_student_id,
            max_attempts=max_attempts,
        )

        timeout = int(
            getattr(
                settings,
                "STUDENT_INSIGHT_CACHE_SECONDS",
                1800,
            )
        )

        if timeout > 0:
            safe_cache_set(
                key,
                insight,
                timeout=timeout,
            )

        return insight

    def _build(
        self,
        student_id: str,
        *,
        max_attempts: int,
    ) -> StudentLearningInsight:
        overview = (
            self.assessment_service
            .get_student_overview(
                student_id
            )
        )

        if overview.status != "ok":
            return StudentLearningInsight(
                status=overview.status,
                message=(
                    overview.message
                    or "성적 데이터를 확인할 수 없습니다."
                ),
                student_id=student_id,
            )

        selected_attempts = list(
            overview.recent_attempts[
                :max_attempts
            ]
        )

        # 오래된 시험부터 최근 시험 순으로 분석합니다.
        selected_attempts.reverse()

        loaded: list[
            dict[str, Any]
        ] = []

        for attempt in selected_attempts:
            detail = (
                self.detail_service
                .get_attempt_detail(
                    student_id,
                    attempt.attempt_id,
                )
            )

            if (
                detail.status != "ok"
                or not detail.questions
            ):
                continue

            single_insight = (
                self.exam_insight_service
                .build(
                    detail.questions
                )
            )

            loaded.append(
                {
                    "attempt": attempt,
                    "detail": detail,
                    "insight": single_insight,
                }
            )

        if not loaded:
            return StudentLearningInsight(
                status="empty",
                message=(
                    "누적 분석에 사용할 문항 데이터가 없습니다."
                ),
                student_id=student_id,
                student_name=(
                    overview.dsg_student_name
                ),
                latest_total_score=(
                    overview.latest_total_score
                ),
                first_score_delta=(
                    overview.first_delta
                ),
                previous_score_delta=(
                    overview.previous_delta
                ),
            )

        area_snapshots: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        area_questions: dict[
            str,
            list,
        ] = defaultdict(list)

        area_names: dict[
            str,
            str,
        ] = {}

        recent_exams: list[
            RecentExamInsight
        ] = []

        review_queue: list[
            ReviewQueueItem
        ] = []

        all_questions = []

        for loaded_item in loaded:
            attempt = loaded_item[
                "attempt"
            ]
            detail = loaded_item[
                "detail"
            ]
            single = loaded_item[
                "insight"
            ]

            all_questions.extend(
                detail.questions
            )

            exam_date_label = (
                attempt.exam_date.strftime(
                    "%Y.%m.%d"
                )
                if attempt.exam_date
                else "날짜 미확인"
            )

            recent_exams.append(
                RecentExamInsight(
                    attempt_id=(
                        attempt.attempt_id
                    ),
                    exam_id=(
                        attempt.exam_id
                    ),
                    exam_name=(
                        attempt.exam_name
                    ),
                    exam_date_label=(
                        exam_date_label
                    ),
                    score_type_label=(
                        attempt.score_type_label
                    ),
                    display_score=(
                        attempt.display_score
                    ),
                    max_score=(
                        attempt.max_score
                    ),
                    total_score=(
                        attempt.total_sat_score
                    ),
                    rw_score=(
                        attempt.rw_sat_score
                    ),
                    math_score=(
                        attempt.math_sat_score
                    ),
                    question_count=len(
                        detail.questions
                    ),
                    review_count=(
                        single.review_count
                    ),
                    accuracy_rate=(
                        detail.item_score_rate
                    ),
                    strongest_area_name=(
                        single.strongest_area.name
                        if single.strongest_area
                        else ""
                    ),
                    priority_area_name=(
                        single.priority_area.name
                        if single.priority_area
                        else ""
                    ),
                )
            )

            for area in (
                single.area_insights
            ):
                area_snapshots[
                    area.key
                ].append(
                    {
                        "attempt": attempt,
                        "area": area,
                        "exam_date_label": (
                            exam_date_label
                        ),
                    }
                )

                area_names[
                    area.key
                ] = area.name

            slow_ids = set(
                single.slow_question_ids
            )

            for question in detail.questions:
                key, name = (
                    self.exam_insight_service
                    .area_for_question(
                        question
                    )
                )

                area_names[key] = name
                area_questions[key].append(
                    question
                )

                if (
                    question.result_code
                    not in REVIEW_CODES
                ):
                    continue

                priority_score = (
                    self._review_priority(
                        question.result_code
                    )
                )

                if (
                    single.priority_area
                    and key
                    == single.priority_area.key
                ):
                    priority_score += 20

                is_slow = (
                    question.question_id
                    in slow_ids
                )

                if is_slow:
                    priority_score += 10

                review_queue.append(
                    ReviewQueueItem(
                        attempt_id=(
                            attempt.attempt_id
                        ),
                        exam_id=(
                            attempt.exam_id
                        ),
                        exam_name=(
                            attempt.exam_name
                        ),
                        exam_date_label=(
                            exam_date_label
                        ),
                        question_id=(
                            question.question_id
                        ),
                        question_no=(
                            question.question_no
                        ),
                        area_key=key,
                        area_name=name,
                        result_code=(
                            question.result_code
                        ),
                        result_label=(
                            question.result_label
                        ),
                        result_class=(
                            question.result_class
                        ),
                        selected_answer=(
                            question.selected_answer
                        ),
                        correct_answer=(
                            question.correct_answer
                        ),
                        duration_seconds=(
                            question.duration_seconds
                        ),
                        duration_label=(
                            question.duration_label
                        ),
                        is_slow=is_slow,
                        priority_score=(
                            priority_score
                        ),
                    )
                )

        cumulative_areas = [
            self._build_cumulative_area(
                key=key,
                name=area_names[key],
                questions=area_questions[key],
                snapshots=area_snapshots.get(
                    key,
                    [],
                ),
            )
            for key in area_questions
        ]

        cumulative_areas.sort(
            key=lambda area: (
                area.accuracy_rate
                if area.accuracy_rate
                is not None
                else 101.0,
                -area.question_count,
                area.name,
            )
        )

        qualified_areas = [
            area
            for area in cumulative_areas
            if (
                area.accuracy_rate
                is not None
                and area.scored_count >= 3
            )
        ] or [
            area
            for area in cumulative_areas
            if area.accuracy_rate
            is not None
        ]

        strongest_area = (
            max(
                qualified_areas,
                key=lambda area: (
                    area.accuracy_rate,
                    area.scored_count,
                ),
            )
            if qualified_areas
            else None
        )

        priority_area = (
            min(
                qualified_areas,
                key=lambda area: (
                    area.accuracy_rate,
                    -area.weak_exam_count,
                    -area.scored_count,
                ),
            )
            if qualified_areas
            else None
        )

        improving_candidates = [
            area
            for area in cumulative_areas
            if (
                area.delta
                is not None
                and area.delta >= 10
            )
        ]

        improving_area = (
            max(
                improving_candidates,
                key=lambda area: (
                    area.delta,
                    area.exam_count,
                ),
            )
            if improving_candidates
            else None
        )

        declining_candidates = [
            area
            for area in cumulative_areas
            if (
                area.delta
                is not None
                and area.delta <= -10
            )
        ]

        declining_area = (
            min(
                declining_candidates,
                key=lambda area: (
                    area.delta,
                    -area.exam_count,
                ),
            )
            if declining_candidates
            else None
        )

        duration_areas = [
            area
            for area in cumulative_areas
            if (
                area.average_duration_seconds
                > 0
            )
        ]

        slowest_area = (
            max(
                duration_areas,
                key=lambda area: (
                    area.average_duration_seconds,
                    area.question_count,
                ),
            )
            if duration_areas
            else None
        )

        scored_questions = [
            question
            for question in all_questions
            if question.result_code
            in SCORED_CODES
        ]

        earned_score = sum(
            question.earned_score
            for question in scored_questions
        )

        max_score = sum(
            question.max_score
            for question in scored_questions
        )

        overall_accuracy = (
            earned_score
            / max_score
            * 100
            if max_score > 0
            else None
        )

        positive_durations = [
            question.duration_seconds
            for question in all_questions
            if question.duration_seconds > 0
        ]

        average_duration = (
            sum(positive_durations)
            / len(positive_durations)
            if positive_durations
            else 0.0
        )

        review_queue.sort(
            key=lambda item: (
                -item.priority_score,
                -item.duration_seconds,
                item.exam_date_label,
                item.question_no,
            )
        )

        recommendations = (
            self._recommendations(
                priority_area=priority_area,
                improving_area=(
                    improving_area
                ),
                declining_area=(
                    declining_area
                ),
                slowest_area=(
                    slowest_area
                ),
                strongest_area=(
                    strongest_area
                ),
                review_count=len(
                    review_queue
                ),
            )
        )

        # 화면에서는 최근 시험이 위로 오도록 역순 표시합니다.
        recent_exams.reverse()

        return StudentLearningInsight(
            status="ok",
            student_id=student_id,
            student_name=(
                overview.dsg_student_name
            ),
            analyzed_exam_count=len(
                loaded
            ),
            total_question_count=len(
                all_questions
            ),
            scored_question_count=len(
                scored_questions
            ),
            correct_count=sum(
                question.result_code
                == "CORRECT"
                for question in all_questions
            ),
            review_count=len(
                review_queue
            ),
            overall_accuracy=(
                overall_accuracy
            ),
            average_duration_seconds=round(
                average_duration,
                1,
            ),
            average_duration_label=(
                self._duration_label(
                    average_duration
                )
            ),
            latest_total_score=(
                overview.latest_total_score
            ),
            first_score_delta=(
                overview.first_delta
            ),
            previous_score_delta=(
                overview.previous_delta
            ),
            strongest_area=(
                strongest_area
            ),
            priority_area=(
                priority_area
            ),
            improving_area=(
                improving_area
            ),
            declining_area=(
                declining_area
            ),
            slowest_area=(
                slowest_area
            ),
            area_insights=tuple(
                cumulative_areas
            ),
            recent_exams=tuple(
                recent_exams
            ),
            recommendations=tuple(
                recommendations
            ),
            review_queue=tuple(
                review_queue[:18]
            ),
        )

    def _build_cumulative_area(
        self,
        *,
        key: str,
        name: str,
        questions: list,
        snapshots: list[
            dict[str, Any]
        ],
    ) -> CumulativeAreaInsight:
        scored_questions = [
            question
            for question in questions
            if question.result_code
            in SCORED_CODES
        ]

        earned_score = sum(
            question.earned_score
            for question in scored_questions
        )

        max_score = sum(
            question.max_score
            for question in scored_questions
        )

        accuracy_rate = (
            earned_score
            / max_score
            * 100
            if max_score > 0
            else None
        )

        trend_points = [
            AreaTrendPoint(
                attempt_id=(
                    snapshot[
                        "attempt"
                    ].attempt_id
                ),
                exam_name=(
                    snapshot[
                        "attempt"
                    ].exam_name
                ),
                exam_date_label=(
                    snapshot[
                        "exam_date_label"
                    ]
                ),
                accuracy_rate=(
                    snapshot[
                        "area"
                    ].accuracy_rate
                ),
                question_count=(
                    snapshot[
                        "area"
                    ].question_count
                ),
                review_count=(
                    snapshot[
                        "area"
                    ].review_count
                ),
                average_duration_seconds=(
                    snapshot[
                        "area"
                    ].average_duration_seconds
                ),
                average_duration_label=(
                    snapshot[
                        "area"
                    ].average_duration_label
                ),
            )
            for snapshot in snapshots
        ]

        valid_rates = [
            point.accuracy_rate
            for point in trend_points
            if point.accuracy_rate
            is not None
        ]

        first_accuracy = (
            valid_rates[0]
            if valid_rates
            else None
        )

        recent_accuracy = (
            valid_rates[-1]
            if valid_rates
            else None
        )

        delta = (
            recent_accuracy
            - first_accuracy
            if (
                first_accuracy
                is not None
                and recent_accuracy
                is not None
                and len(valid_rates) >= 2
            )
            else None
        )

        weak_exam_count = sum(
            point.accuracy_rate
            is not None
            and point.accuracy_rate < 60
            for point in trend_points
        )

        positive_durations = [
            question.duration_seconds
            for question in questions
            if question.duration_seconds > 0
        ]

        average_duration = (
            sum(positive_durations)
            / len(positive_durations)
            if positive_durations
            else 0.0
        )

        status, status_label = (
            self._area_status(
                accuracy_rate=(
                    accuracy_rate
                ),
                delta=delta,
                weak_exam_count=(
                    weak_exam_count
                ),
            )
        )

        return CumulativeAreaInsight(
            key=key,
            name=name,
            exam_count=len(
                trend_points
            ),
            question_count=len(
                questions
            ),
            scored_count=len(
                scored_questions
            ),
            correct_count=sum(
                question.result_code
                == "CORRECT"
                for question in questions
            ),
            review_count=sum(
                question.result_code
                in REVIEW_CODES
                for question in questions
            ),
            earned_score=(
                earned_score
            ),
            max_score=max_score,
            accuracy_rate=(
                accuracy_rate
            ),
            first_accuracy=(
                first_accuracy
            ),
            recent_accuracy=(
                recent_accuracy
            ),
            delta=delta,
            weak_exam_count=(
                weak_exam_count
            ),
            average_duration_seconds=round(
                average_duration,
                1,
            ),
            average_duration_label=(
                self._duration_label(
                    average_duration
                )
            ),
            status=status,
            status_label=(
                status_label
            ),
            trend_points=tuple(
                trend_points
            ),
        )

    @staticmethod
    def _area_status(
        *,
        accuracy_rate: float | None,
        delta: float | None,
        weak_exam_count: int,
    ) -> tuple[str, str]:
        if accuracy_rate is None:
            return (
                "unknown",
                "계산 제외",
            )

        if (
            accuracy_rate < 60
            or weak_exam_count >= 2
        ):
            return (
                "priority",
                "우선 학습",
            )

        if (
            delta is not None
            and delta <= -10
        ):
            return (
                "declining",
                "하락",
            )

        if (
            delta is not None
            and delta >= 10
        ):
            return (
                "improving",
                "향상",
            )

        if accuracy_rate >= 80:
            return (
                "strong",
                "강점",
            )

        return (
            "stable",
            "유지",
        )

    @staticmethod
    def _review_priority(
        result_code: str,
    ) -> int:
        return {
            "UNANSWERED": 100,
            "WRONG": 90,
            "PARTIAL": 80,
            "FREE_RESPONSE": 70,
        }.get(
            result_code,
            0,
        )

    def _recommendations(
        self,
        *,
        priority_area,
        improving_area,
        declining_area,
        slowest_area,
        strongest_area,
        review_count: int,
    ) -> list[StudyRecommendation]:
        recommendations: list[
            StudyRecommendation
        ] = []

        if priority_area:
            recommendations.append(
                StudyRecommendation(
                    rank=1,
                    kind="priority",
                    title=(
                        f"{priority_area.name}를 "
                        "가장 먼저 복습"
                    ),
                    description=(
                        f"누적 획득률 "
                        f"{priority_area.accuracy_rate:.1f}%이며 "
                        f"최근 시험 중 "
                        f"{priority_area.weak_exam_count}회가 "
                        "60% 미만입니다."
                    ),
                    action=(
                        f"해당 영역 복습 문항 "
                        f"{priority_area.review_count}개를 "
                        "오답 근거와 함께 다시 풉니다."
                    ),
                    area_key=(
                        priority_area.key
                    ),
                    area_name=(
                        priority_area.name
                    ),
                )
            )

        if (
            declining_area
            and (
                not priority_area
                or declining_area.key
                != priority_area.key
            )
        ):
            recommendations.append(
                StudyRecommendation(
                    rank=len(
                        recommendations
                    ) + 1,
                    kind="declining",
                    title=(
                        f"{declining_area.name} "
                        "하락 원인 확인"
                    ),
                    description=(
                        f"최초 대비 최근 획득률이 "
                        f"{declining_area.delta:.1f}%p "
                        "하락했습니다."
                    ),
                    action=(
                        "최근 시험과 이전 시험의 "
                        "오답 유형을 비교하고 "
                        "개념 누락과 시간 부족을 구분합니다."
                    ),
                    area_key=(
                        declining_area.key
                    ),
                    area_name=(
                        declining_area.name
                    ),
                )
            )

        if (
            slowest_area
            and slowest_area.average_duration_seconds
            >= 60
        ):
            recommendations.append(
                StudyRecommendation(
                    rank=len(
                        recommendations
                    ) + 1,
                    kind="speed",
                    title=(
                        f"{slowest_area.name} "
                        "시간 제한 연습"
                    ),
                    description=(
                        "문항당 평균 풀이시간이 "
                        f"{slowest_area.average_duration_label}로 "
                        "가장 깁니다."
                    ),
                    action=(
                        "정답률을 유지하면서 "
                        "문항당 목표 시간을 설정한 "
                        "짧은 세트 훈련을 진행합니다."
                    ),
                    area_key=(
                        slowest_area.key
                    ),
                    area_name=(
                        slowest_area.name
                    ),
                )
            )

        if review_count > 0:
            recommendations.append(
                StudyRecommendation(
                    rank=len(
                        recommendations
                    ) + 1,
                    kind="review",
                    title=(
                        f"복습 큐 {review_count}문항 정리"
                    ),
                    description=(
                        "무응답·오답·부분점수·직접입력 "
                        "문항을 우선순위로 정렬했습니다."
                    ),
                    action=(
                        "상위 문항부터 다시 풀고 "
                        "틀린 이유를 개념·판단·시간으로 "
                        "분류해 기록합니다."
                    ),
                )
            )

        if (
            improving_area
            and len(recommendations) < 4
        ):
            recommendations.append(
                StudyRecommendation(
                    rank=len(
                        recommendations
                    ) + 1,
                    kind="improving",
                    title=(
                        f"{improving_area.name} "
                        "상승 흐름 유지"
                    ),
                    description=(
                        f"최초 대비 최근 획득률이 "
                        f"+{improving_area.delta:.1f}%p "
                        "향상됐습니다."
                    ),
                    action=(
                        "현재 풀이 방식을 유지하고 "
                        "난도가 높은 문항으로 확장합니다."
                    ),
                    area_key=(
                        improving_area.key
                    ),
                    area_name=(
                        improving_area.name
                    ),
                )
            )

        if (
            strongest_area
            and not recommendations
        ):
            recommendations.append(
                StudyRecommendation(
                    rank=1,
                    kind="strong",
                    title=(
                        f"{strongest_area.name} "
                        "강점 유지"
                    ),
                    description=(
                        f"누적 획득률 "
                        f"{strongest_area.accuracy_rate:.1f}%로 "
                        "가장 안정적입니다."
                    ),
                    action=(
                        "주 1회 짧은 유지 세트로 "
                        "감각을 유지합니다."
                    ),
                    area_key=(
                        strongest_area.key
                    ),
                    area_name=(
                        strongest_area.name
                    ),
                )
            )

        return recommendations[:4]

    @staticmethod
    def _duration_label(
        seconds: float,
    ) -> str:
        if seconds <= 0:
            return "—"

        rounded = int(
            round(seconds)
        )

        minutes, remainder = divmod(
            rounded,
            60,
        )

        if minutes:
            return (
                f"{minutes}분 "
                f"{remainder}초"
            )

        return f"{remainder}초"
