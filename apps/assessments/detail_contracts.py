from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QuestionChoiceDetail:
    """문항 선택지입니다."""

    choice_id: str
    choice_no: str
    content: str
    content_type: str
    partial_score: int
    is_correct: bool
    is_selected: bool = False


@dataclass(frozen=True)
class ExamQuestionDetail:
    """학생의 시험 문항 응답 한 건입니다."""

    question_id: str
    question_no: int
    section_id: str
    section_name: str
    module_id: str
    module_name: str

    content_type: str
    question_text: str
    media_url: str
    topic: str

    selected_answer: str
    correct_answer: str

    result_code: str
    result_label: str
    result_class: str

    earned_score: int
    max_score: int

    duration_seconds: int
    duration_label: str
    bookmark: bool
    annotation: str

    choices: tuple[QuestionChoiceDetail, ...] = ()


@dataclass(frozen=True)
class ExamAttemptHeader:
    """시험 응시 결과 상단 요약입니다."""

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
    total_duration_seconds: int
    total_duration_label: str


@dataclass(frozen=True)
class ExamAttemptDetail:
    """시험 상세 페이지 전체 데이터입니다."""

    status: str
    message: str = ""

    student_id: str = ""
    student_name: str = ""
    dsg_student_id: str = ""

    attempt: ExamAttemptHeader | None = None
    questions: tuple[ExamQuestionDetail, ...] = ()

    correct_count: int = 0
    partial_count: int = 0
    wrong_count: int = 0
    unanswered_count: int = 0
    free_response_count: int = 0

    earned_score: int = 0
    max_score: int = 0
    item_score_rate: float | None = None
