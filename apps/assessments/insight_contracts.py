from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaInsight:
    """한 시험의 영역별 성취도입니다."""

    key: str
    name: str

    question_count: int
    scored_count: int

    correct_count: int
    partial_count: int
    wrong_count: int
    unanswered_count: int
    direct_input_count: int
    review_count: int

    earned_score: int
    max_score: int
    accuracy_rate: float | None

    average_duration_seconds: float
    average_duration_label: str

    status: str
    status_label: str


@dataclass(frozen=True)
class ExamInsightOverview:
    """단일 시험의 강점·취약영역·필터 요약입니다."""

    status: str

    total_count: int = 0
    correct_count: int = 0
    review_count: int = 0
    wrong_count: int = 0
    partial_count: int = 0
    unanswered_count: int = 0
    direct_input_count: int = 0
    slow_count: int = 0

    area_insights: tuple[AreaInsight, ...] = ()

    strongest_area: AreaInsight | None = None
    priority_area: AreaInsight | None = None
    slowest_area: AreaInsight | None = None

    slow_question_ids: tuple[str, ...] = ()
    priority_question_ids: tuple[str, ...] = ()
