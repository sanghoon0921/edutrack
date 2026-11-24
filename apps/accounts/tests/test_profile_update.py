from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class ProfileUpdateTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="profile_student",
            password="1234",
            display_name="기존 학생",
            email="old@example.com",
            role=User.Role.STUDENT,
        )

    def test_get_prefills_existing_identity_and_keeps_password_fields_blank(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["username"].value(), self.student.username)
        self.assertEqual(form["display_name"].value(), self.student.display_name)
        self.assertEqual(form["email"].value(), self.student.email)
        self.assertIn('value="profile_student"', response.content.decode())
        self.assertIn('value="기존 학생"', response.content.decode())
        self.assertIn('value="old@example.com"', response.content.decode())
        self.assertNotIn('value="1234"', response.content.decode())
        self.assertEqual(form["password1"].value() or "", "")
        self.assertEqual(form["password2"].value() or "", "")

    def test_user_can_update_own_information_and_password(self):
        # 11/24: 비밀번호는 8자 이상·숫자만 금지(전에는 4자 허용)
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("profile"),
            {
                "username": "profile_student_changed",
                "display_name": "수정 학생",
                "email": "new@example.com",
                "password1": "study5678",
                "password2": "study5678",
            },
        )
        self.assertRedirects(response, reverse("profile"))
        self.student.refresh_from_db()
        self.assertEqual(self.student.username, "profile_student_changed")
        self.assertEqual(self.student.display_name, "수정 학생")
        self.assertEqual(self.student.email, "new@example.com")
        self.assertTrue(self.student.check_password("study5678"))
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_three_character_password_is_rejected(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("profile"),
            {
                "username": self.student.username,
                "display_name": self.student.display_name,
                "email": self.student.email,
                "password1": "123",
                "password2": "123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("1234"))
        self.assertContains(response, "4")

    def test_header_uses_role_text_instead_of_name_initial(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="premium-role-avatar"')
        self.assertContains(response, ">학생</span>")
        self.assertContains(response, reverse("profile"))
