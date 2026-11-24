from unittest.mock import patch

from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from apps.accounts.models import (
    StudentAccountLink,
    User,
)
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
class ParentPortalTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username="parent_portal_test",
            password="Parent!2026",
            role=User.Role.PARENT,
            display_name="김지훈 학부모",
        )
        self.student = User.objects.create_user(
            username="student_portal_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )

        StudentAccountLink.objects.create(
            user=self.parent,
            student_no="6333",
            relationship=(
                StudentAccountLink
                .Relationship.PARENT
            ),
            is_primary=True,
            is_active=True,
        )

        student_service = StudentService(
            repository=DemoStudentRepository()
        )
        course_service = CourseService(
            repository=DemoCourseRepository()
        )
        attendance_service = AttendanceService(
            repository=DemoAttendanceRepository()
        )

        patchers = [
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

        for patcher in patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

    def test_parent_uses_premium_student_dashboard(self):
        self.client.force_login(
            self.parent
        )

        response = self.client.get(
            reverse("dashboard")
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTemplateUsed(
            response,
            "dashboard/student.html",
        )
        # 11/10: 학부모 홈도 학생 홈과 같은 구성(한눈에 보기 + 자녀 학습 메뉴)
        self.assertContains(
            response,
            "data-home-insights",
        )
        self.assertContains(
            response,
            "자녀의 수업과",
        )
        self.assertContains(
            response,
            "수납내역",
        )

    def test_student_navigation_has_no_billing(self):
        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse("dashboard")
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertNotContains(
            response,
            "수납내역",
        )

    def test_parent_can_open_linked_student_detail(self):
        self.client.force_login(
            self.parent
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

    def test_parent_cannot_open_other_student(self):
        self.client.force_login(
            self.parent
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
