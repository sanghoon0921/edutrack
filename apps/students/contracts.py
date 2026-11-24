from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class StudentSummary:
    """학생 검색과 상세 화면에서 사용하는 공통 데이터입니다."""

    student_id: str = ""
    name: str = ""
    english_name: str = ""
    grade: str = ""
    country: str = ""
    city: str = ""
    school: str = ""
    branch: str = ""
    status: str = ""
    dsg_id: str = ""
    dsg_connected: bool = False


@dataclass(frozen=True)
class CourseSummary:
    """학생에게 연결된 수업의 화면 표시용 요약입니다."""

    assign_id: str = ""
    class_id: str = ""
    class_name: str = ""
    subject_name: str = ""
    term_name: str = ""
    branch_name: str = ""
    teacher_names: str = ""
    schedule_summary: str = ""
    learning_methods: str = ""

    start_date: date | None = None
    end_date: date | None = None
    first_lesson_date: date | None = None
    last_lesson_date: date | None = None
    next_lesson_date: date | None = None

    planned_count: int = 0
    display_status: str = ""
    is_active: bool = False


@dataclass(frozen=True)
class AttendanceRecord:
    """학생 수업 한 회차의 출결 및 등록 상태입니다."""

    assign_id: str = ""
    lesson_id: str = ""
    lesson_date: date | None = None
    lesson_type: str = ""
    time_summary: str = ""
    lesson_way: str = ""
    attendance_code: str = ""
    attendance_label: str = ""
    status_kind: str = ""
    attendance_type: str = ""
    payment_code: str = ""
    payment_label: str = ""
    is_student_cancelled: bool = False
    is_class_cancelled: bool = False
    # 녹화(RC) 회차의 녹화본 발송 일시(인트라넷의 녹화본 발송 완료 기록 중 가장 최근). 없으면 발송 전.
    recording_sent_at: datetime | None = None


@dataclass(frozen=True)
class AttendanceSummary:
    """선택한 수업의 출결 요약입니다."""

    scheduled_count: int = 0
    completed_count: int = 0
    recognized_count: int = 0
    present_count: int = 0
    absent_count: int = 0
    late_count: int = 0
    recorded_count: int = 0
    upcoming_count: int = 0
    unprocessed_count: int = 0
    cancelled_count: int = 0
    holiday_count: int = 0
    attendance_rate: float | None = None
