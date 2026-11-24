from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .contracts import CourseSummary


class CourseRepository(Protocol):
    """학생별 수업 목록 Repository의 공통 규격입니다."""

    def list_by_student_id(
        self,
        student_id: str,
    ) -> list[CourseSummary]:
        ...


DEMO_COURSES: dict[str, tuple[CourseSummary, ...]] = {
    "6333": (
        CourseSummary(
            assign_id="10001",
            class_id="201",
            class_name="2026 여름특강 SAT Advanced",
            subject_name="SAT",
            term_name="2026 여름특강",
            branch_name="온라인",
            teacher_names="Tony T",
            schedule_summary="Reading · Writing · Math",
            learning_methods="온라인",
            start_date=date(2026, 7, 20),
            end_date=date(2026, 8, 14),
            first_lesson_date=date(2026, 7, 20),
            last_lesson_date=date(2026, 8, 14),
            next_lesson_date=date(2026, 7, 27),
            planned_count=12,
            display_status="진행중",
            is_active=True,
        ),
        CourseSummary(
            assign_id="10002",
            class_id="202",
            class_name="2026 봄학기 Academic Writing",
            subject_name="Academic Writing",
            term_name="2026 봄학기",
            branch_name="온라인",
            teacher_names="Michelle T",
            schedule_summary="Academic Writing",
            learning_methods="온라인",
            start_date=date(2026, 3, 7),
            end_date=date(2026, 5, 30),
            first_lesson_date=date(2026, 3, 7),
            last_lesson_date=date(2026, 5, 30),
            next_lesson_date=None,
            planned_count=12,
            display_status="종료",
            is_active=False,
        ),
    ),
    "6334": (
        CourseSummary(
            assign_id="10003",
            class_id="203",
            class_name="2026 가을정규 SAT",
            subject_name="SAT",
            term_name="2026 가을정규",
            branch_name="온라인",
            teacher_names="Daniel T",
            schedule_summary="SAT",
            learning_methods="온라인",
            start_date=date(2026, 8, 23),
            end_date=date(2026, 11, 29),
            first_lesson_date=date(2026, 8, 23),
            last_lesson_date=date(2026, 11, 29),
            next_lesson_date=date(2026, 8, 23),
            planned_count=15,
            display_status="예정",
            is_active=False,
        ),
    ),
}


class DemoCourseRepository:
    """자동 테스트용 모의 수업 Repository입니다."""

    def list_by_student_id(
        self,
        student_id: str,
    ) -> list[CourseSummary]:
        return list(
            DEMO_COURSES.get(
                student_id.strip(),
                (),
            )
        )


def _to_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_int(value) -> int:
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_date(value) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    cleaned_value = str(value).strip()

    if not cleaned_value:
        return None

    for date_format in (
        "%Y-%m-%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(
                cleaned_value,
                date_format,
            ).date()
        except ValueError:
            continue

    return None


def _fetch_all_as_dicts(cursor) -> list[dict]:
    columns = [
        column[0]
        for column in cursor.description
    ]

    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


class IntranetCourseRepository:
    """실제 서비스에서는 사내 인트라넷 DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def get_course_repository() -> CourseRepository:
    data_source = getattr(
        settings,
        "STUDENT_DATA_SOURCE",
        "demo",
    ).strip().lower()

    if data_source == "demo":
        return DemoCourseRepository()

    if data_source == "intranet":
        return IntranetCourseRepository()

    raise ImproperlyConfigured(
        "STUDENT_DATA_SOURCE는 "
        "'demo' 또는 'intranet'이어야 합니다."
    )
