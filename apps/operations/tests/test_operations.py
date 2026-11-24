from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import StudentAccountLink, User

from apps.operations.models import AccountAuditLog, TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo", STUDENT_TEST_STUDENT_ID="6333")
class OperationsPermissionAndWorkflowTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="root_admin",
            password="1234",
            display_name="최고관리자",
            role=User.Role.ADMIN,
        )
        self.admin = User.objects.create_user(
            username="operations_admin",
            password="1234",
            display_name="일반 관리자",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="operations_teacher",
            password="1234",
            display_name="김강사",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="operations_student",
            password="1234",
            display_name="김학생",
            role=User.Role.STUDENT,
        )
        self.parent = User.objects.create_user(
            username="operations_parent",
            password="1234",
            display_name="김학부모",
            role=User.Role.PARENT,
        )
        self.student_lookup = patch(
            "apps.students.services.StudentService.get_student",
            side_effect=lambda student_no: SimpleNamespace(
                student_id=str(student_no),
                name={"6333": "김지훈", "7102": "박서연"}.get(str(student_no), ""),
            )
            if str(student_no) in {"6333", "7102"}
            else None,
        )
        self.student_lookup.start()
        self.addCleanup(self.student_lookup.stop)

    def test_unauthenticated_user_is_redirected(self):
        response = self.client.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_non_admin_cannot_access_operations(self):
        for user in (self.teacher, self.student, self.parent):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("operations:dashboard"))
                self.assertEqual(response.status_code, 403)

    def test_admin_dashboard_and_navigation_render(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("operations:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "계정관리")
        self.assertContains(response, reverse("operations:user-list"))
        self.assertContains(response, "담당 학생 배정")
        self.assertNotContains(response, "최근 등록 계정")
        self.assertNotContains(response, "학생 미연결")

    def test_user_list_searches_without_activation_filter(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("operations:user-list"), {"q": "김강사"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.teacher.username)
        self.assertNotContains(response, "활성·비활성")

    def test_normal_admin_can_create_teacher_with_password(self):
        # 11/24: 비밀번호는 8자 이상·숫자만 금지(전에는 4자 허용)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:user-create"),
            {
                "username": "created_teacher",
                "display_name": "신규 강사",
                "email": "teacher@example.com",
                "role": User.Role.TEACHER,
                "student_no": "",
                "password1": "edutrack1234",
                "password2": "edutrack1234",
            },
        )
        self.assertEqual(response.status_code, 302)
        created = User.objects.get(username="created_teacher")
        self.assertTrue(created.check_password("edutrack1234"))
        self.assertTrue(created.is_active)
        self.assertTrue(
            AccountAuditLog.objects.filter(
                target_user=created,
                action=AccountAuditLog.Action.USER_CREATED,
            ).exists()
        )

    def test_three_character_password_is_rejected(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:user-create"),
            {
                "username": "short_password_user",
                "display_name": "짧은 비밀번호",
                "email": "",
                "role": User.Role.TEACHER,
                "student_no": "",
                "password1": "123",
                "password2": "123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="short_password_user").exists())
        self.assertContains(response, "4")

    def test_normal_admin_cannot_create_admin_account(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:user-create"),
            {
                "username": "forbidden_admin",
                "display_name": "금지 관리자",
                "email": "",
                "role": User.Role.ADMIN,
                "student_no": "",
                "password1": "edutrack1234",
                "password2": "edutrack1234",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="forbidden_admin").exists())

    def test_superuser_can_create_admin_account(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("operations:user-create"),
            {
                "username": "created_admin",
                "display_name": "추가 관리자",
                "email": "",
                "role": User.Role.ADMIN,
                "student_no": "",
                "password1": "edutrack1234",
                "password2": "edutrack1234",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="created_admin").role, User.Role.ADMIN)

    def test_normal_admin_updates_profile_and_password_but_not_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:user-update", kwargs={"user_id": self.teacher.pk}),
            {
                "username": "teacher_changed",
                "display_name": "변경 강사",
                "email": "changed@example.com",
                "role": User.Role.PARENT,
                "password1": "edutrack5678",
                "password2": "edutrack5678",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.username, "teacher_changed")
        self.assertEqual(self.teacher.display_name, "변경 강사")
        self.assertEqual(self.teacher.role, User.Role.TEACHER)
        self.assertTrue(self.teacher.check_password("edutrack5678"))

    def test_superuser_can_change_role(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("operations:user-update", kwargs={"user_id": self.teacher.pk}),
            {
                "username": self.teacher.username,
                "display_name": self.teacher.display_name,
                "email": self.teacher.email,
                "role": User.Role.PARENT,
                "password1": "",
                "password2": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, User.Role.PARENT)

    def test_normal_admin_cannot_view_or_edit_admin_accounts(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(
                reverse("operations:user-detail", kwargs={"user_id": self.superuser.pk})
            ).status_code,
            403,
        )
        other_admin = User.objects.create_user(
            username="other_admin", password="1234", role=User.Role.ADMIN
        )
        self.assertEqual(
            self.client.get(
                reverse("operations:user-update", kwargs={"user_id": other_admin.pk})
            ).status_code,
            403,
        )

    def test_removed_deactivation_and_separate_password_routes_do_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("operations:user-toggle-status", kwargs={"user_id": self.teacher.pk})
        with self.assertRaises(NoReverseMatch):
            reverse("operations:user-password", kwargs={"user_id": self.teacher.pk})

    def test_student_and_parent_links_are_managed(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:link-add", kwargs={"user_id": self.parent.pk}),
            {"student_no": "6333", "is_primary": "on"},
        )
        self.assertEqual(response.status_code, 302)
        first = StudentAccountLink.objects.get(user=self.parent, student_no="6333")
        self.assertTrue(first.is_primary)
        self.client.post(
            reverse("operations:link-add", kwargs={"user_id": self.parent.pk}),
            {"student_no": "7102"},
        )
        self.assertEqual(
            StudentAccountLink.objects.filter(user=self.parent, is_active=True).count(), 2
        )
        self.client.post(
            reverse(
                "operations:link-primary",
                kwargs={"user_id": self.parent.pk, "link_id": first.pk},
            )
        )
        first.refresh_from_db()
        self.assertTrue(first.is_primary)

    def test_student_cannot_have_two_active_links(self):
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse("operations:link-add", kwargs={"user_id": self.student.pk}),
            {"student_no": "7102"},
        )
        self.assertFalse(
            StudentAccountLink.objects.filter(
                user=self.student, student_no="7102", is_active=True
            ).exists()
        )

    def test_teacher_student_access_add_and_remove(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("operations:teacher-access-add", kwargs={"user_id": self.teacher.pk}),
            {"student_no": "6333"},
        )
        self.assertEqual(response.status_code, 302)
        access = TeacherStudentAccess.objects.get(teacher=self.teacher, student_no="6333")
        self.assertTrue(access.is_active)
        remove_response = self.client.post(
            reverse(
                "operations:teacher-access-remove",
                kwargs={"user_id": self.teacher.pk, "access_id": access.pk},
            )
        )
        self.assertEqual(remove_response.status_code, 302)
        access.refresh_from_db()
        self.assertFalse(access.is_active)

    def test_audit_log_list_is_admin_only(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("operations:audit-list")).status_code, 200)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("operations:audit-list")).status_code, 403)
