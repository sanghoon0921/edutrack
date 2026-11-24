from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.students.attendance_services import AttendanceService
from apps.students.contracts import AttendanceRecord, CourseSummary, StudentSummary
from apps.students.course_services import CourseService
from apps.students.services import StudentService


@override_settings(
    STUDENT_DATA_SOURCE="stage13-cache-test",
    STUDENT_PROFILE_CACHE_SECONDS=60,
    STUDENT_COURSE_CACHE_SECONDS=60,
    ATTENDANCE_CACHE_SECONDS=60,
)
class Stage13ReadCacheTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def tearDown(self) -> None:
        cache.clear()

    def test_student_profile_reuses_short_cache(self):
        class Repository:
            def __init__(self):
                self.calls = 0

            def get_by_id(self, student_id):
                self.calls += 1
                return StudentSummary(student_id=student_id, name="캐시 학생")

            def search(self, keyword):
                return []

            def list_by_ids(self, student_ids):
                return [self.get_by_id(student_id) for student_id in student_ids]

        repository = Repository()
        with patch("apps.students.services.get_student_repository", return_value=repository):
            service = StudentService()
            first = service.get_student("S-13")
            second = service.get_student("S-13")

        self.assertEqual(first, second)
        self.assertEqual(repository.calls, 1)

    def test_course_list_reuses_short_cache(self):
        class Repository:
            def __init__(self):
                self.calls = 0

            def list_by_student_id(self, student_id):
                self.calls += 1
                return [
                    CourseSummary(
                        assign_id="A-13",
                        class_name="성능 안정화 수업",
                        display_status="진행중",
                        is_active=True,
                    )
                ]

        repository = Repository()
        with patch(
            "apps.students.course_services.get_course_repository",
            return_value=repository,
        ):
            service = CourseService()
            first = service.get_student_courses("S-13")
            second = service.get_student_courses("S-13")

        self.assertEqual(first, second)
        self.assertEqual(repository.calls, 1)

    def test_bulk_attendance_reuses_course_level_cache(self):
        class Repository:
            def __init__(self):
                self.bulk_calls = 0

            def list_by_student_and_assign(self, student_id, assign_id):
                raise AssertionError("bulk loader should be used")

            def list_by_student_and_assigns(self, student_id, assign_ids):
                self.bulk_calls += 1
                return {
                    assign_id: [
                        AttendanceRecord(
                            assign_id=assign_id,
                            lesson_id=f"L-{assign_id}",
                            lesson_date=date(2026, 8, 10),
                            attendance_label="출석",
                            status_kind="present",
                        )
                    ]
                    for assign_id in assign_ids
                }

        repository = Repository()
        with patch(
            "apps.students.attendance_services.get_attendance_repository",
            return_value=repository,
        ):
            service = AttendanceService()
            first = service.get_attendance_for_courses("S-13", ["A-1", "A-2"])
            second = service.get_attendance_for_courses("S-13", ["A-1", "A-2"])

        self.assertEqual(first, second)
        self.assertEqual(repository.bulk_calls, 1)
