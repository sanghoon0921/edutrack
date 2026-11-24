"""떠 있는 '메시지' 버튼이 화면 맨 아래 버튼(예: 학생 상세의 '출결 상세 보기')을 가리지 않게 아래 여백을 둔다."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STUDENT_DATA_SOURCE="demo")
class ChatFabSpacingTests(TestCase):
    def test_pages_with_the_message_button_mark_the_body(self):
        teacher = get_user_model().objects.create_user("fab_teacher", password="x-Fab!2026", role="TEACHER")
        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "portal-chat-fab")
        self.assertRegex(response.content.decode(), r'<body class="[^"]*\bhas-chat-fab\b')

    def test_parents_without_messenger_keep_the_normal_body(self):
        parent = get_user_model().objects.create_user("fab_parent", password="x-Fab!2026", role="PARENT")
        self.client.force_login(parent)
        html = self.client.get(reverse("dashboard"), follow=True).content.decode()
        self.assertNotIn("has-chat-fab", html)

    def test_page_bottom_is_padded_above_the_floating_button(self):
        css = (Path(settings.BASE_DIR) / "static/css/layers/95-portal-focus.css").read_text(encoding="utf-8")
        self.assertIn("body.has-chat-fab .page-shell.intranet-page-shell{padding-bottom:104px!important}", css)
        base = (Path(settings.BASE_DIR) / "templates/layouts/base.html").read_text(encoding="utf-8")
        self.assertIn("css/layers/95-portal-focus.css' %}?v=1110nv3", base)
