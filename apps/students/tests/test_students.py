from unittest.mock import patch

from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.models import TeacherStudentAccess

from apps.students.attendance_repositories import (
    DemoAttendanceRepository,
)
from apps.students.attendance_services import (
    AttendanceService,
)
from apps.students.course_repositories import (
    DemoCourseRepository,
)
from apps.students.course_services import CourseService
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import StudentService


@override_settings(
    STUDENT_DATA_SOURCE="demo",
    ASSESSMENT_DATA_SOURCE="demo",
    STUDENT_TEST_STUDENT_ID="6333",
)
class StudentPageTests(TestCase):
    """
    학생 페이지 권한·검색·상세 테스트입니다.

    운영용 intranet·dsg DB에는 접근하지 않고
    Demo Repository를 View getter에 주입합니다.
    """

    def setUp(self):
        student_service = StudentService(
            repository=DemoStudentRepository()
        )

        course_service = CourseService(
            repository=DemoCourseRepository()
        )

        attendance_service = AttendanceService(
            repository=DemoAttendanceRepository()
        )

        self.service_patchers = [
            patch(
                "apps.students.views.get_student_service",
                return_value=student_service,
            ),
            patch(
                "apps.students.views.get_course_service",
                return_value=course_service,
            ),
            patch(
                "apps.students.views.get_attendance_service",
                return_value=attendance_service,
            ),
        ]

        for patcher in self.service_patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

        self.admin_user = User.objects.create_user(
            username="student_page_admin",
            password="Admin!2026",
            role=User.Role.ADMIN,
        )

        self.teacher_user = User.objects.create_user(
            username="student_page_teacher",
            password="Teacher!2026",
            role=User.Role.TEACHER,
        )

        self.student_user = User.objects.create_user(
            username="student_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )

        TeacherStudentAccess.objects.create(
            teacher=self.teacher_user,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin_user,
            is_active=True,
        )

    def test_unauthenticated_user_is_redirected(self):
        response = self.client.get(
            reverse("students:list")
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertIn(
            reverse("login"),
            response.url,
        )

    def test_admin_can_access_student_list(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse("students:list")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "학생 관리",
        )

    def test_teacher_can_access_student_list(self):
        self.client.force_login(
            self.teacher_user
        )

        response = self.client.get(
            reverse("students:list")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_teacher_can_search_only_within_assigned_students(self):
        self.client.force_login(self.teacher_user)

        assigned_response = self.client.get(
            reverse("students:list"),
            {"q": "김지훈"},
        )
        self.assertEqual(assigned_response.status_code, 200)
        self.assertTrue(assigned_response.context["assigned_mode"])
        self.assertIsNotNone(assigned_response.context["form"])
        self.assertContains(assigned_response, "김지훈")
        self.assertNotContains(assigned_response, "박서연")

        unassigned_response = self.client.get(
            reverse("students:list"),
            {"q": "박서연"},
        )
        self.assertEqual(unassigned_response.status_code, 200)
        self.assertEqual(unassigned_response.context["students"], [])
        self.assertNotContains(unassigned_response, "김지훈")

    def test_teacher_can_access_assigned_student_only(self):
        self.client.force_login(self.teacher_user)
        assigned = self.client.get(
            reverse("students:detail", kwargs={"student_id": "6333"})
        )
        unassigned = self.client.get(
            reverse("students:detail", kwargs={"student_id": "7102"})
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(unassigned.status_code, 403)

    def test_student_cannot_access_student_list(self):
        self.client.force_login(
            self.student_user
        )

        response = self.client.get(
            reverse("students:list")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_search_by_name(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse("students:list"),
            {
                "q": "김지훈",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "김지훈",
        )

        self.assertContains(
            response,
            "6333",
        )

    def test_search_by_student_id(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse("students:list"),
            {
                "q": "6333",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "김지훈",
        )

    def test_admin_can_access_student_detail(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse(
                "students:detail",
                kwargs={
                    "student_id": "6333",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "김지훈",
        )

        self.assertContains(
            response,
            "현재 수강 중인 수업",
        )

    def test_student_can_access_own_detail(self):
        self.client.force_login(
            self.student_user
        )

        response = self.client.get(
            reverse("students:my-detail")
        )

        self.assertRedirects(
            response,
            reverse(
                "students:detail",
                kwargs={
                    "student_id": "6333",
                },
            ),
        )

    def test_completed_course_attendance_can_be_opened_without_records(self):
        self.client.force_login(self.student_user)
        response = self.client.get(
            reverse(
                "students:attendance",
                kwargs={"student_id": "6333", "assign_id": "10002"},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "완료된 수업의 출결 기록입니다")
        self.assertContains(response, "해당 수업의 출결 기록이 없습니다")

    def test_student_cannot_access_other_detail(self):
        self.client.force_login(
            self.student_user
        )

        response = self.client.get(
            reverse(
                "students:detail",
                kwargs={
                    "student_id": "7102",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_unknown_student_returns_404(self):
        self.client.force_login(
            self.admin_user
        )

        response = self.client.get(
            reverse(
                "students:detail",
                kwargs={
                    "student_id": "not-found",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )
