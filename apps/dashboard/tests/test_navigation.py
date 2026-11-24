from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo")
class Stage14NavigationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="stage14_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="stage14_teacher", password="1234", role=User.Role.TEACHER
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )

    def test_authenticated_pages_show_prominent_back_button(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-smart-back")
        self.assertContains(response, "뒤로가기")

    def test_teacher_home_prioritizes_notices_chat_and_direct_assignment_link(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "담당 학생 바로 선택")
        self.assertContains(response, "공지사항")
        self.assertContains(response, "data-home-chat-list")
        self.assertNotContains(response, "data-teacher-student-picker")
        self.assertContains(response, reverse("operations:teacher-student-assignment"))

    def test_teacher_assigned_student_list_can_filter_by_school_or_name(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("students:list"), {"q": "Ekamai"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "김지훈")
        self.assertContains(response, "담당 학생 이름·번호·학교 검색")

        empty = self.client.get(reverse("students:list"), {"q": "없는학생"})
        self.assertEqual(empty.status_code, 200)
        self.assertNotContains(empty, "김지훈")
