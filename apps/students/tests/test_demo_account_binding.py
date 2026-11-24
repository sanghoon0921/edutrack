from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.demo_account_binding import bind_demo_accounts_to_student
from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess
from apps.students.repositories import DemoStudentRepository
from apps.students.services import StudentService


@override_settings(
    STUDENT_DATA_SOURCE="demo",
    STUDENT_TEST_STUDENT_ID="6333",
    ADMIN_AUTO_LINK_TEST_ACCOUNTS=True,
    DEMO_STUDENT_USERNAME="student_test",
    DEMO_PARENT_USERNAME="parent_test",
)
class AdminSelectedStudentBindingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="selection_admin",
            password="1234",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="selection_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        self.student_test = User.objects.create_user(
            username="student_test",
            password="1234",
            role=User.Role.STUDENT,
        )
        self.parent_test = User.objects.create_user(
            username="parent_test",
            password="1234",
            role=User.Role.PARENT,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
            is_active=True,
        )

        student_service = StudentService(
            repository=DemoStudentRepository()
        )
        self.student_service_patch = patch(
            "apps.students.views.get_student_service",
            return_value=student_service,
        )
        self.course_service_patch = patch(
            "apps.students.views.get_course_service",
            return_value=SimpleNamespace(
                get_current_student_courses=lambda student_id: []
            ),
        )
        self.attendance_service_patch = patch(
            "apps.students.views.get_attendance_service",
            return_value=SimpleNamespace(),
        )
        self.student_service_patch.start()
        self.course_service_patch.start()
        self.attendance_service_patch.start()
        self.addCleanup(self.student_service_patch.stop)
        self.addCleanup(self.course_service_patch.stop)
        self.addCleanup(self.attendance_service_patch.stop)

    def test_binding_service_links_student_and_parent_to_same_student(self):
        result = bind_demo_accounts_to_student("7102")

        self.assertEqual(result.updated_count, 2)
        self.assertEqual(
            StudentAccountLink.objects.get(
                user=self.student_test,
                is_active=True,
            ).student_no,
            "7102",
        )
        self.assertEqual(
            StudentAccountLink.objects.get(
                user=self.parent_test,
                is_active=True,
            ).student_no,
            "7102",
        )

    def test_switching_student_deactivates_previous_links(self):
        bind_demo_accounts_to_student("6333")
        bind_demo_accounts_to_student("7102")

        for user in (self.student_test, self.parent_test):
            self.assertFalse(
                StudentAccountLink.objects.get(
                    user=user,
                    student_no="6333",
                ).is_active
            )
            current = StudentAccountLink.objects.get(
                user=user,
                student_no="7102",
            )
            self.assertTrue(current.is_active)
            self.assertTrue(current.is_primary)

    def test_admin_opening_student_detail_updates_demo_accounts(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse(
                "students:detail",
                kwargs={"student_id": "7102"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StudentAccountLink.objects.get(
                user=self.student_test,
                is_active=True,
            ).student_no,
            "7102",
        )
        self.assertEqual(
            StudentAccountLink.objects.get(
                user=self.parent_test,
                is_active=True,
            ).student_no,
            "7102",
        )

    def test_teacher_opening_student_detail_does_not_switch_demo_accounts(self):
        bind_demo_accounts_to_student("7102")
        self.client.force_login(self.teacher)

        with patch(
            "apps.students.views.bind_demo_accounts_to_student"
        ) as binding:
            response = self.client.get(
                reverse(
                    "students:detail",
                    kwargs={"student_id": "6333"},
                )
            )

        self.assertEqual(response.status_code, 200)
        binding.assert_not_called()
        self.assertEqual(
            StudentAccountLink.objects.get(
                user=self.student_test,
                is_active=True,
            ).student_no,
            "7102",
        )
