"""메신저 이름 표시: 학생은 '이름 · 학생번호'(예: 김지훈D · 6333), 그 밖의 계정은 이름만."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink
from apps.lms.models import Conversation, ConversationMember, Message
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo")
class ChatNameTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.teacher = User.objects.create_user("chat_teacher", password="x-Chat!2026", role="TEACHER", display_name="박선생")
        self.student = User.objects.create_user("chat_student", password="x-Chat!2026", role="STUDENT", display_name="김지훈D")
        StudentAccountLink.objects.create(user=self.student, student_no="6333", relationship="SELF", is_primary=True)
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈D")  # 강사는 담당 학생과만 대화
        self.conv = Conversation.objects.create(title="", created_by=self.teacher)
        for user in (self.teacher, self.student):
            ConversationMember.objects.create(conversation=self.conv, user=user)
        Message.objects.create(conversation=self.conv, sender=self.student, body="안녕하세요")

    def test_student_name_shows_student_number(self):
        self.assertEqual(self.student.chat_name, "김지훈D · 6333")
        self.assertEqual(self.teacher.chat_name, "박선생")

    def test_student_without_a_link_shows_the_name_only(self):
        other = get_user_model().objects.create_user("chat_nolink", password="x-Chat!2026", role="STUDENT", display_name="이서연")
        self.assertEqual(other.chat_name, "이서연")

    def test_conversation_list_snapshot_and_page_use_the_numbered_name(self):
        self.client.force_login(self.teacher)
        summary = self.client.get(reverse("lms:chat-summary")).json()
        self.assertIn("김지훈D · 6333", str(summary))
        snapshot = self.client.get(reverse("lms:chat-snapshot", args=[self.conv.pk])).json()
        self.assertIn("김지훈D · 6333", str(snapshot))
        page = self.client.get(reverse("lms:conversation", args=[self.conv.pk]))
        self.assertContains(page, "김지훈D · 6333")
