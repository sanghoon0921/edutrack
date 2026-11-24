from __future__ import annotations

from datetime import date

from django.conf import settings

from config.cache_utils import build_cache_key, safe_cache_get, safe_cache_set

from .contracts import CourseSummary
from .course_repositories import CourseRepository, get_course_repository


CACHE_VERSION = "v1"


class CourseService:
    """학생별 수업 조회와 현재·예정·과거 분류를 처리합니다."""

    CURRENT_STATUSES = {"진행중", "진행 중", "수강중", "수강 중"}
    UPCOMING_STATUSES = {"예정", "등록", "대기"}
    COMPLETED_STATUSES = {"종료", "완료", "수강완료", "수강 완료"}
    EXCLUDED_STATUSES = {"폐강", "취소", "수업취소", "사용중지", "미승인"}

    def __init__(self, repository: CourseRepository | None = None) -> None:
        self._uses_default_repository = repository is None
        self.repository = repository or get_course_repository()

    @staticmethod
    def _cache_key(student_id: str) -> str:
        source = str(getattr(settings, "STUDENT_DATA_SOURCE", "intranet")).strip()
        return build_cache_key(
            "student-courses",
            CACHE_VERSION,
            source,
            student_id,
        )

    def get_student_courses(self, student_id: str) -> list[CourseSummary]:
        cleaned_student_id = student_id.strip()
        if not cleaned_student_id:
            return []

        timeout = (
            max(0, int(getattr(settings, "STUDENT_COURSE_CACHE_SECONDS", 60)))
            if self._uses_default_repository
            else 0
        )
        key = self._cache_key(cleaned_student_id)
        if timeout > 0:
            cached = safe_cache_get(key)
            if isinstance(cached, list):
                return cached

        courses = self.repository.list_by_student_id(cleaned_student_id)
        if timeout > 0:
            safe_cache_set(key, courses, timeout=timeout)
        return courses

    @classmethod
    def _is_current(cls, course: CourseSummary) -> bool:
        return bool(
            course.is_active
            and course.display_status.strip() in cls.CURRENT_STATUSES
        )

    @classmethod
    def _is_upcoming(cls, course: CourseSummary) -> bool:
        status = course.display_status.strip()
        return bool(
            not cls._is_current(course)
            and status not in cls.EXCLUDED_STATUSES
            and status in cls.UPCOMING_STATUSES
        )

    @classmethod
    def _is_completed(cls, course: CourseSummary) -> bool:
        status = course.display_status.strip()
        if status in cls.EXCLUDED_STATUSES or cls._is_current(course):
            return False
        if status in cls.COMPLETED_STATUSES:
            return True
        end_date = course.end_date or course.last_lesson_date
        return bool(end_date and end_date < date.today() and not course.is_active)

    @staticmethod
    def _recent_date(course: CourseSummary) -> date:
        return (
            course.end_date
            or course.last_lesson_date
            or course.start_date
            or course.first_lesson_date
            or date.min
        )

    def classify_courses(
        self,
        courses: list[CourseSummary],
    ) -> dict[str, list[CourseSummary]]:
        current = [course for course in courses if self._is_current(course)]
        upcoming = [course for course in courses if self._is_upcoming(course)]
        completed = [course for course in courses if self._is_completed(course)]

        current.sort(
            key=lambda course: (
                course.next_lesson_date or date.max,
                course.class_name,
            )
        )
        upcoming.sort(
            key=lambda course: (
                course.start_date or course.first_lesson_date or date.max,
                course.class_name,
            )
        )
        completed.sort(
            key=lambda course: (self._recent_date(course), course.class_name),
            reverse=True,
        )
        return {
            "current": current,
            "upcoming": upcoming,
            "completed": completed,
        }

    def get_student_course_groups(
        self,
        student_id: str,
    ) -> dict[str, list[CourseSummary]]:
        return self.classify_courses(self.get_student_courses(student_id))

    def get_current_student_courses(self, student_id: str) -> list[CourseSummary]:
        """학생 기본 화면에 표시할 현재 진행 중 수업만 반환합니다."""
        return self.get_student_course_groups(student_id)["current"]

    def get_completed_student_courses(self, student_id: str) -> list[CourseSummary]:
        """종료일이 최근인 순서로 완료된 과거 수업을 반환합니다."""
        return self.get_student_course_groups(student_id)["completed"]

    def get_preferred_student_courses(
        self,
        student_id: str,
    ) -> tuple[list[CourseSummary], str]:
        """현재 수업을 우선하고, 없을 때만 완료된 과거 수업으로 대체합니다."""
        groups = self.get_student_course_groups(student_id)
        if groups["current"]:
            return groups["current"], "current"
        if groups["completed"]:
            return groups["completed"], "history"
        return [], "empty"
