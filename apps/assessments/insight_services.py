from __future__ import annotations

from collections import defaultdict
from statistics import median

from .detail_contracts import (
    ExamQuestionDetail,
)
from .insight_contracts import (
    AreaInsight,
    ExamInsightOverview,
)


REVIEW_CODES = {
    "WRONG",
    "PARTIAL",
    "UNANSWERED",
    "FREE_RESPONSE",
}

SCORED_CODES = {
    "CORRECT",
    "WRONG",
    "PARTIAL",
    "UNANSWERED",
}


class ExamInsightService:
    """캐시된 문항을 이용해 추가 DB 조회 없이 인사이트를 계산합니다."""

    def build(
        self,
        questions: tuple[
            ExamQuestionDetail,
            ...
        ] | list[ExamQuestionDetail],
    ) -> ExamInsightOverview:
        items = list(questions)

        if not items:
            return ExamInsightOverview(
                status="empty",
            )

        slow_question_ids = (
            self._slow_question_ids(
                items
            )
        )

        grouped: dict[
            str,
            list[ExamQuestionDetail],
        ] = defaultdict(list)

        area_names: dict[
            str,
            str,
        ] = {}

        for question in items:
            key, name = self._area(
                question
            )

            grouped[key].append(
                question
            )
            area_names[key] = name

        area_insights = [
            self._build_area(
                key=key,
                name=area_names[key],
                questions=area_questions,
            )
            for key, area_questions
            in grouped.items()
        ]

        # 우선 복습 영역부터 보이도록 낮은 획득률 순으로 정렬합니다.
        area_insights.sort(
            key=lambda area: (
                area.accuracy_rate
                if area.accuracy_rate
                is not None
                else 101.0,
                -area.question_count,
                area.name,
            )
        )

        scored_areas = [
            area
            for area in area_insights
            if (
                area.accuracy_rate
                is not None
                and area.scored_count > 0
            )
        ]

        strongest_area = (
            max(
                scored_areas,
                key=lambda area: (
                    area.accuracy_rate,
                    area.scored_count,
                    area.question_count,
                ),
            )
            if scored_areas
            else None
        )

        priority_candidates = [
            area
            for area in scored_areas
            if area.scored_count >= 2
        ] or scored_areas

        priority_area = (
            min(
                priority_candidates,
                key=lambda area: (
                    area.accuracy_rate,
                    -area.scored_count,
                    area.name,
                ),
            )
            if priority_candidates
            else None
        )

        duration_areas = [
            area
            for area in area_insights
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

        priority_questions = [
            question
            for question in items
            if question.result_code
            in REVIEW_CODES
        ]

        priority_questions.sort(
            key=lambda question: (
                self._review_priority(
                    question.result_code
                ),
                -question.duration_seconds,
                question.question_no,
            )
        )

        return ExamInsightOverview(
            status="ok",
            total_count=len(items),
            correct_count=self._count(
                items,
                "CORRECT",
            ),
            review_count=len(
                priority_questions
            ),
            wrong_count=self._count(
                items,
                "WRONG",
            ),
            partial_count=self._count(
                items,
                "PARTIAL",
            ),
            unanswered_count=self._count(
                items,
                "UNANSWERED",
            ),
            direct_input_count=self._count(
                items,
                "FREE_RESPONSE",
            ),
            slow_count=len(
                slow_question_ids
            ),
            area_insights=tuple(
                area_insights
            ),
            strongest_area=(
                strongest_area
            ),
            priority_area=(
                priority_area
            ),
            slowest_area=(
                slowest_area
            ),
            slow_question_ids=tuple(
                slow_question_ids
            ),
            priority_question_ids=tuple(
                question.question_id
                for question
                in priority_questions
            ),
        )

    def _build_area(
        self,
        *,
        key: str,
        name: str,
        questions: list[
            ExamQuestionDetail
        ],
    ) -> AreaInsight:
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
            self._status(
                accuracy_rate
            )
        )

        return AreaInsight(
            key=key,
            name=name,
            question_count=len(
                questions
            ),
            scored_count=len(
                scored_questions
            ),
            correct_count=self._count(
                questions,
                "CORRECT",
            ),
            partial_count=self._count(
                questions,
                "PARTIAL",
            ),
            wrong_count=self._count(
                questions,
                "WRONG",
            ),
            unanswered_count=self._count(
                questions,
                "UNANSWERED",
            ),
            direct_input_count=self._count(
                questions,
                "FREE_RESPONSE",
            ),
            review_count=sum(
                question.result_code
                in REVIEW_CODES
                for question in questions
            ),
            earned_score=earned_score,
            max_score=max_score,
            accuracy_rate=accuracy_rate,
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
            status_label=status_label,
        )

    @staticmethod
    def _count(
        questions: list[
            ExamQuestionDetail
        ],
        result_code: str,
    ) -> int:
        return sum(
            question.result_code
            == result_code
            for question in questions
        )

    @staticmethod
    def _status(
        accuracy_rate: float | None,
    ) -> tuple[str, str]:
        if accuracy_rate is None:
            return (
                "unknown",
                "계산 제외",
            )

        if accuracy_rate >= 80:
            return (
                "strong",
                "강점",
            )

        if accuracy_rate >= 60:
            return (
                "stable",
                "보통",
            )

        return (
            "priority",
            "우선 복습",
        )

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

    @staticmethod
    def _review_priority(
        result_code: str,
    ) -> int:
        order = {
            "UNANSWERED": 0,
            "WRONG": 1,
            "PARTIAL": 2,
            "FREE_RESPONSE": 3,
        }

        return order.get(
            result_code,
            9,
        )

    @classmethod
    def area_for_question(
        cls,
        question: ExamQuestionDetail,
    ) -> tuple[str, str]:
        return cls._area(question)

    @staticmethod
    def _area(
        question: ExamQuestionDetail,
    ) -> tuple[str, str]:
        section_name = (
            question.section_name.strip()
            or "기타"
        )

        topic_parts = [
            part.strip()
            for part in (
                question.topic
                or ""
            ).split(">")
            if part.strip()
        ]

        first_topic = (
            topic_parts[0]
            if topic_parts
            else ""
        )

        normalized = (
            first_topic
            .replace("&", "")
            .replace(" ", "")
            .upper()
        )

        code_map = {
            "M": "Math",
            "MATH": "Math",
            "RW": "Reading & Writing",
            "R&W": "Reading & Writing",
            "READINGWRITING": (
                "Reading & Writing"
            ),
        }

        if normalized in code_map:
            name = code_map[
                normalized
            ]

        elif (
            first_topic
            and len(first_topic) >= 5
            and not first_topic.isupper()
        ):
            name = first_topic

        elif (
            first_topic
            and " " in first_topic
        ):
            name = first_topic

        else:
            name = section_name

        key = (
            name.casefold()
            .replace(" ", "-")
        )

        return key, name

    @staticmethod
    def _slow_question_ids(
        questions: list[
            ExamQuestionDetail
        ],
    ) -> list[str]:
        durations = [
            question.duration_seconds
            for question in questions
            if question.duration_seconds > 0
        ]

        if not durations:
            return []

        threshold = max(
            90,
            int(
                median(durations)
                * 1.5
            ),
        )

        slow_questions = [
            question
            for question in questions
            if (
                question.duration_seconds
                >= threshold
            )
        ]

        # 모든 문항이 빠른 시험에서도 의미 있는 최장 문항 하나는 표시합니다.
        if (
            not slow_questions
            and max(durations) >= 60
        ):
            slow_questions = [
                max(
                    questions,
                    key=lambda question: (
                        question.duration_seconds
                    ),
                )
            ]

        slow_questions.sort(
            key=lambda question: (
                -question.duration_seconds,
                question.question_no,
            )
        )

        return [
            question.question_id
            for question in slow_questions
        ]
