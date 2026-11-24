from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AreaTrendPoint:
    """한 시험에서 특정 영역의 결과입니다."""

    attempt_id: str
    exam_name: str
    exam_date_label: str
    accuracy_rate: float | None
    question_count: int
    review_count: int
    average_duration_seconds: float
    average_duration_label: str


@dataclass(frozen=True)
class CumulativeAreaInsight:
    """최근 여러 시험을 합산한 영역 분석입니다."""

    key: str
    name: str

    exam_count: int
    question_count: int
    scored_count: int
    correct_count: int
    review_count: int

    earned_score: int
    max_score: int
    accuracy_rate: float | None

    first_accuracy: float | None
    recent_accuracy: float | None
    delta: float | None
    weak_exam_count: int

    average_duration_seconds: float
    average_duration_label: str

    status: str
    status_label: str

    trend_points: tuple[AreaTrendPoint, ...] = ()


@dataclass(frozen=True)
class ReviewQueueItem:
    """누적 분석에서 우선 복습할 문항입니다."""

    attempt_id: str
    exam_id: str
    exam_name: str
    exam_date_label: str

    question_id: str
    question_no: int

    area_key: str
    area_name: str

    result_code: str
    result_label: str
    result_class: str

    selected_answer: str
    correct_answer: str

    duration_seconds: int
    duration_label: str
    is_slow: bool
    priority_score: int


@dataclass(frozen=True)
class RecentExamInsight:
    """누적 분석 화면의 최근 시험 카드입니다."""

    attempt_id: str
    exam_id: str
    exam_name: str
    exam_date_label: str

    score_type_label: str
    display_score: int | None
    max_score: int

    total_score: int | None
    rw_score: int | None
    math_score: int | None

    question_count: int
    review_count: int
    accuracy_rate: float | None

    strongest_area_name: str = ""
    priority_area_name: str = ""


@dataclass(frozen=True)
class StudyRecommendation:
    """규칙 기반 학습 권고입니다."""

    rank: int
    kind: str
    title: str
    description: str
    action: str
    area_key: str = ""
    area_name: str = ""


@dataclass(frozen=True)
class StudentLearningInsight:
    """학생의 최근 여러 시험 누적 학습 분석입니다."""

    status: str
    message: str = ""

    student_id: str = ""
    student_name: str = ""

    analyzed_exam_count: int = 0
    total_question_count: int = 0
    scored_question_count: int = 0
    correct_count: int = 0
    review_count: int = 0

    overall_accuracy: float | None = None
    average_duration_seconds: float = 0.0
    average_duration_label: str = "—"

    latest_total_score: int | None = None
    first_score_delta: int | None = None
    previous_score_delta: int | None = None

    strongest_area: CumulativeAreaInsight | None = None
    priority_area: CumulativeAreaInsight | None = None
    improving_area: CumulativeAreaInsight | None = None
    declining_area: CumulativeAreaInsight | None = None
    slowest_area: CumulativeAreaInsight | None = None

    area_insights: tuple[CumulativeAreaInsight, ...] = ()
    recent_exams: tuple[RecentExamInsight, ...] = ()
    recommendations: tuple[StudyRecommendation, ...] = ()
    review_queue: tuple[ReviewQueueItem, ...] = ()
