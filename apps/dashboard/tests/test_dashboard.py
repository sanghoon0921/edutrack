from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import (
    StudentAccountLink,
    User,
)


@override_settings(
    STUDENT_DATA_SOURCE="demo",
    ASSESSMENT_DATA_SOURCE="demo",
)
class DashboardRoleTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="admin_role_test",
            password="StrongPass!2026",
            role=User.Role.ADMIN,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_role_test",
            password="StrongPass!2026",
            role=User.Role.TEACHER,
        )
        self.student_user = User.objects.create_user(
            username="student_role_test",
            password="StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.parent_user = User.objects.create_user(
            username="parent_role_test",
            password="StrongPass!2026",
            role=User.Role.PARENT,
        )

        StudentAccountLink.objects.create(
            user=self.parent_user,
            student_no="6333",
            relationship=(
                StudentAccountLink
                .Relationship.PARENT
            ),
            is_primary=True,
            is_active=True,
        )

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("dashboard")
        )
        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertIn(
            reverse("login"),
            response.url,
        )

    def test_role_dashboards_render(self):
        cases = [
            (
                self.admin_user,
                "dashboard/admin.html",
            ),
            (
                self.teacher_user,
                "dashboard/teacher.html",
            ),
            (
                self.student_user,
                "dashboard/student.html",
            ),
            (
                self.parent_user,
                "dashboard/student.html",
            ),
        ]

        for user, template_name in cases:
            with self.subTest(
                role=user.role
            ):
                self.client.force_login(user)
                response = self.client.get(
                    reverse("dashboard")
                )
                self.assertEqual(
                    response.status_code,
                    200,
                )
                self.assertTemplateUsed(
                    response,
                    template_name,
                )
                self.client.logout()

    def test_admin_page_access_matrix(self):
        url = reverse("admin_students")

        for user, expected_status in [
            (self.admin_user, 302),  # 빈 화면 대신 실제 학생 목록으로 보냄
            (self.teacher_user, 403),
            (self.student_user, 403),
            (self.parent_user, 403),
        ]:
            with self.subTest(
                role=user.role
            ):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(url).status_code,
                    expected_status,
                )
                self.client.logout()

    def test_teacher_page_access_matrix(self):
        url = reverse("teacher_classes")

        for user, expected_status in [
            (self.admin_user, 200),
            (self.teacher_user, 200),
            (self.student_user, 403),
            (self.parent_user, 403),
        ]:
            with self.subTest(
                role=user.role
            ):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(url).status_code,
                    expected_status,
                )
                self.client.logout()

    def test_student_page_access_matrix(self):
        url = reverse("student_classes")

        for user, expected_status in [
            (self.admin_user, 200),
            (self.teacher_user, 403),
            (self.student_user, 200),
            (self.parent_user, 200),
        ]:
            with self.subTest(
                role=user.role
            ):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(url).status_code,
                    expected_status,
                )
                self.client.logout()

    def test_role_navigation_is_rendered(self):
        cases = [
            (
                self.admin_user,
                "학생 관리",
            ),
            (
                self.teacher_user,
                "담당 수업",
            ),
            (
                self.student_user,
                "내 출결",
            ),
            (
                self.parent_user,
                "수납내역",
            ),
        ]

        for user, expected_text in cases:
            with self.subTest(
                role=user.role
            ):
                self.client.force_login(user)
                response = self.client.get(
                    reverse("dashboard")
                )
                self.assertContains(
                    response,
                    expected_text,
                )
                self.client.logout()
