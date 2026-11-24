from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DsgStudentProfile:
    """인트라넷 학생과 연결된 DSG 학생 정보입니다."""

    status: str
    dsg_student_id: str = ""
    dsg_key: str = ""
    name: str = ""
    school: str = ""
    grade: str = ""
    matched_field: str = ""


@dataclass(frozen=True)
class ExamAttemptSummary:
    """학생의 완료된 시험 응시 한 건입니다."""

    attempt_id: str
    exam_id: str
    exam_name: str
    exam_date: datetime | None

    rw_sat_score: int | None
    math_sat_score: int | None
    total_sat_score: int | None

    total_questions: int
    correct_answers: int
    wrong_answers: int
    accuracy_rate: float | None

    rw_attempted: bool
    math_attempted: bool

    score_type: str
    score_type_label: str
    display_score: int | None
    max_score: int

    delta_previous: int | None = None


@dataclass(frozen=True)
class ModuleAttemptSummary:
    """Module만 따로 본 DSG 시험 한 건입니다."""

    attempt_id: str
    module_id: str
    module_name: str
    taken_at: datetime | None
    section_label: str  # "RW", "Math", "RW·Math" 또는 ""
    total_questions: int
    correct_answers: int
    wrong_answers: int
    accuracy_rate: float | None
    answered_questions: int = 0  # 학생이 이 Module 을 따로 풀며 답을 남긴 문항 수(answer 표)


@dataclass(frozen=True)
class ScoreChartPoint:
    """SAT 총점 SVG 차트에 사용하는 좌표입니다."""

    x: float
    y: float
    score: int
    exam_name: str
    exam_date_label: str


@dataclass(frozen=True)
class StudentExamOverview:
    """학생 상세 화면에 표시할 DSG 시험 요약입니다."""

    status: str
    message: str = ""

    dsg_student_id: str = ""
    dsg_student_name: str = ""
    dsg_school_name: str = ""
    dsg_grade: str = ""
    matched_field: str = ""

    exam_count: int = 0
    full_sat_count: int = 0

    latest_total_score: int | None = None
    latest_rw_score: int | None = None
    latest_math_score: int | None = None

    average_total_score: float | None = None
    highest_total_score: int | None = None
    recent_three_average: float | None = None

    first_delta: int | None = None
    previous_delta: int | None = None
    overall_accuracy: float | None = None

    recent_attempts: tuple[ExamAttemptSummary, ...] = ()
    module_attempts: tuple[ModuleAttemptSummary, ...] = ()  # 최근 순
    chart_points: tuple[ScoreChartPoint, ...] = ()
    chart_polyline: str = ""
