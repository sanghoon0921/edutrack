"""Class 리스트: '배정 학생' 버튼을 누르면 그 수업의 인트라넷 배정 학생 명단을 줄 아래로 펼친다."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class ClassRosterToggleTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user("roster_admin", password="x-Roster!2026", role="ADMIN")
        self.client.force_login(self.admin)

    def test_assigned_student_count_opens_the_roster(self):
        response = self.client.get(reverse("admin_classes"))
        self.assertEqual(response.status_code, 200)
        for text in [
            f'data-class-roster-url="{reverse("students:selector-browse")}"',
            f'data-student-detail-url="{reverse("students:detail", args=["__ID__"])}"',
            'data-class-roster="1001"', 'aria-expanded="false"', "명 보기",
            "dashboard/js/class-roster.js",
        ]:
            self.assertContains(response, text)

    def test_roster_comes_from_the_shared_student_list_for_the_class(self):
        rows = self.client.get(reverse("students:selector-browse"), {"source": "intranet", "class_id": "201"}).json()["results"]
        self.assertEqual([row["student_id"] for row in rows], ["6333"])

    def test_script_pages_through_the_roster_and_shows_failures(self):
        js = (Path(settings.BASE_DIR) / "apps/dashboard/static/dashboard/js/class-roster.js").read_text(encoding="utf-8")
        for text in ["source: 'intranet'", "class_id", "page", "더 보기", "B.row(", "B.errorBox(", "aria-expanded"]:
            self.assertIn(text, js)
