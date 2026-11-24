from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess

from apps.students.contracts import CourseSummary, StudentSummary
from apps.students.course_services import CourseService
from apps.students.forms import StudentSelectionField


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo")
class StudentSelectorApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="selector_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="selector_teacher", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="selector_student", password="1234", role=User.Role.STUDENT
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
            is_active=True,
        )

    def test_admin_can_search_students_by_name(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("students:selector-search"), {"q": "김지훈"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([row["student_id"] for row in payload["results"]], ["6333"])

    def test_admin_can_search_students_by_grade(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("students:selector-search"), {"q": "10학년"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["student_id"] for row in response.json()["results"]], ["6333"])

    def test_all_learning_editors_render_the_same_transfer_selector(self):
        self.client.force_login(self.admin)
        for url_name in (
            "assignments:create",
            "learning:discussion-create",
            "learning:quiz-create",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "대상 학생 선택")
                self.assertContains(response, "data-student-transfer-selector")
                self.assertNotContains(response, '<textarea name="student_ids"', html=False)

    def test_teacher_sees_only_assigned_students(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("students:selector-search"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["student_id"] for row in response.json()["results"]], ["6333"])

        blocked = self.client.get(reverse("students:selector-search"), {"q": "7102"})
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.json()["results"], [])

    def test_teacher_without_assignment_gets_clear_guidance(self):
        unassigned_teacher = User.objects.create_user(
            username="selector_unassigned_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        self.client.force_login(unassigned_teacher)

        response = self.client.get(reverse("students:selector-search"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["assigned_count"], 0)
        self.assertIn("담당 학생이 아직 배정되지 않았습니다", payload["message"])

    def test_unresolved_teacher_assignment_is_reported_instead_of_silently_disappearing(self):
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="999999",
            student_name="이전 배정 학생",
            assigned_by=self.admin,
            is_active=True,
        )
        self.client.force_login(self.teacher)

        response = self.client.get(reverse("students:selector-search"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        fallback = next(
            item for item in payload["results"] if item["student_id"] == "999999"
        )
        self.assertEqual(fallback["name"], "이전 배정 학생")
        self.assertFalse(fallback["is_resolved"])
        self.assertFalse(fallback["selectable"])
        self.assertEqual(payload["unresolved_count"], 1)

    def test_assignment_editor_renders_transfer_selector_instead_of_student_number_textarea(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("assignments:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "대상 학생 선택")
        self.assertContains(response, "data-student-transfer-selector")
        self.assertContains(response, 'name="student_ids"', html=False)
        self.assertNotContains(response, '<textarea name="student_ids"', html=False)

    def test_student_cannot_access_selector_api(self):
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(reverse("students:selector-search"), {"q": "김"}).status_code,
            403,
        )


class StudentSelectionFieldTests(TestCase):
    def test_legacy_comma_newline_input_is_supported_and_deduplicated(self):
        field = StudentSelectionField()
        self.assertEqual(field.clean("6333\n7102,6333"), ["6333", "7102"])

    def test_empty_selection_is_rejected(self):
        field = StudentSelectionField()
        with self.assertRaisesMessage(ValidationError, "대상 학생을 한 명 이상 선택해 주세요"):
            field.clean("")


class CourseHistoryServiceTests(TestCase):
    class Repository:
        def __init__(self, courses):
            self.courses = courses

        def list_by_student_id(self, student_id):
            return list(self.courses)

    def test_current_courses_are_preferred_over_completed_courses(self):
        current = CourseSummary(
            assign_id="1", class_name="현재 수업", display_status="진행중", is_active=True
        )
        completed = CourseSummary(
            assign_id="2",
            class_name="과거 수업",
            display_status="종료",
            is_active=False,
            end_date=date(2025, 12, 1),
        )
        service = CourseService(repository=self.Repository([completed, current]))
        courses, mode = service.get_preferred_student_courses("9001")
        self.assertEqual(mode, "current")
        self.assertEqual([course.assign_id for course in courses], ["1"])

    def test_completed_courses_are_used_when_current_courses_are_absent(self):
        completed = CourseSummary(
            assign_id="2",
            class_name="과거 수업",
            display_status="종료",
            is_active=False,
            end_date=date(2025, 12, 1),
        )
        service = CourseService(repository=self.Repository([completed]))
        courses, mode = service.get_preferred_student_courses("9001")
        self.assertEqual(mode, "history")
        self.assertEqual([course.assign_id for course in courses], ["2"])


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo")
class LearnerHistoryDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="history_student", password="1234", role=User.Role.STUDENT
        )
        StudentAccountLink.objects.create(
            user=self.user,
            student_no="9001",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        self.student = StudentSummary(
            student_id="9001",
            name="과거수업학생",
            grade="11학년",
            school="History International School",
        )
        self.current = CourseSummary(
            assign_id="C1",
            class_name="진행 수업",
            display_status="진행중",
            is_active=True,
            planned_count=8,
        )
        self.completed = CourseSummary(
            assign_id="H1",
            class_name="완료 수업",
            display_status="종료",
            is_active=False,
            end_date=date(2026, 5, 30),
            planned_count=12,
        )
        self.client.force_login(self.user)

    def _patch_services(self, groups):
        student_service = type(
            "StudentServiceStub",
            (),
            {"get_student": lambda _self, _student_id: self.student},
        )()
        course_service = type(
            "CourseServiceStub",
            (),
            {"get_student_course_groups": lambda _self, _student_id: groups},
        )()
        return patch("apps.dashboard.views.StudentService", return_value=student_service), patch(
            "apps.dashboard.views.CourseService", return_value=course_service
        )

    def test_attendance_falls_back_to_completed_courses(self):
        groups = {"current": [], "upcoming": [], "completed": [self.completed]}
        student_patch, course_patch = self._patch_services(groups)
        with student_patch, course_patch:
            response = self.client.get(reverse("student_attendance"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "현재 진행 중인 수업이 없어 완료된 수업을 표시합니다")
        self.assertContains(response, "완료 수업")

    def test_grades_show_only_dsg_results_without_loading_course_history(self):
        student_service = type(
            "StudentServiceStub",
            (),
            {"get_student": lambda _self, _student_id: self.student},
        )()
        with patch("apps.dashboard.views.StudentService", return_value=student_service), patch(
            "apps.dashboard.views.CourseService"
        ) as course_service:
            response = self.client.get(reverse("student_grades"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DSG 시험 성적")
        self.assertContains(response, "Digital SAT 성적")
        self.assertNotContains(response, "완료 수업")
        self.assertNotContains(response, "과거 수업")
        course_service.assert_not_called()

    def test_current_courses_are_shown_instead_of_history(self):
        groups = {
            "current": [self.current],
            "upcoming": [],
            "completed": [self.completed],
        }
        student_patch, course_patch = self._patch_services(groups)
        with student_patch, course_patch:
            response = self.client.get(reverse("student_attendance"))
        self.assertContains(response, "진행 수업")
        self.assertNotContains(response, "완료 수업")

    def test_exact_empty_message_is_shown_when_no_attendance_course_exists(self):
        groups = {"current": [], "upcoming": [], "completed": []}
        student_patch, course_patch = self._patch_services(groups)
        with student_patch, course_patch:
            attendance = self.client.get(reverse("student_attendance"))
        self.assertContains(
            attendance,
            "진행 중이거나 완료된 수업이 없습니다.",
        )
