"""담당 학생 지정 세 칸: 화면 구성, 수업 검색 정확 일치·학생 수, 지운 주소, 확인 필요 학생."""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.dashboard.class_catalog import TermSubjectOptions
from apps.operations import class_student_search as cs
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class ThreeColumnAssignmentTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user("three_teacher", password="x-Three!2026", role="TEACHER")
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈")
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="99999", student_name="미확인 학생")
        self.client.force_login(self.teacher)
        self.page = reverse("operations:teacher-student-assignment")
        self.classes = reverse("operations:teacher-class-search")

    def test_page_has_three_columns_and_catalog_dropdowns(self):
        response = self.client.get(self.page)
        for text in ["① 수업 찾기", "② 인트라넷 전체 학생", "③ 현재 담당 학생", '<select name="term">', '<option value="2026 여름특강">',
                     '<select name="subject">', "data-class-results", "data-student-browser", "data-assigned-q", "× 해제"]:
            self.assertContains(response, text)
        self.assertNotContains(response, "data-search-mode")

    def test_initial_rows_include_unresolved_assigned_student(self):
        response = self.client.get(self.page)
        raw = re.search(r'<script id="teacher-assignment-initial-data" type="application/json">(.*?)</script>', response.content.decode(), re.S).group(1)
        rows = {row["student_id"]: row for row in json.loads(raw)}
        self.assertEqual(rows["6333"]["class_label"], "2026 여름특강 SAT Advanced")
        self.assertFalse(rows["99999"]["selectable"])

    def test_term_and_subject_filters_are_exact(self):
        data = self.client.get(self.classes, {"term": "2026 여름특강"}).json()
        self.assertEqual([c["id"] for c in data["classes"]], ["201"])
        self.assertEqual(self.client.get(self.classes, {"term": "2026"}).json()["total"], 0)

    def test_classes_show_student_counts(self):
        data = self.client.get(self.classes).json()
        self.assertEqual({c["id"]: c["student_count"] for c in data["classes"]}, {"201": 1, "202": 1, "203": 1})

    def test_old_student_search_address_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("operations:teacher-student-assignment-search")
        self.assertEqual(self.client.get("/operations/my-students/search/", {"q": "7102"}).status_code, 404)

    def test_roster_comes_from_shared_browser_in_teacher_mode(self):
        rows = self.client.get(reverse("students:selector-browse"), {"mode": "teacher", "source": "intranet", "class_id": "201"}).json()["results"]
        self.assertEqual([(r["student_id"], r["assigned"]) for r in rows], [("6333", True)])

    def test_script_uses_shared_parts_and_ime_safe_inputs(self):
        js = (Path(settings.BASE_DIR) / "apps/operations/static/operations/js/teacher-assignment.js").read_text(encoding="utf-8")
        for text in ["EduStudentBrowser", "mode:'teacher'", "requireInput:true", "setScope(", "B.liveInput(", "B.filterRows(", "B.row(",
                     "side==='search'&&s.selectable===false"]:
            self.assertIn(text, js)
        self.assertNotIn("data-search-mode", js)

    def test_failures_show_notice_and_retry_in_place_of_class_and_student_lists(self):
        js = (Path(settings.BASE_DIR) / "apps/operations/static/operations/js/teacher-assignment.js").read_text(encoding="utf-8")
        self.assertIn("meta?.error", js)            # ② 학생 칸: 연결 실패를 '학생 없음'과 구분
        self.assertIn("B.errorBox(", js)
        self.assertIn("()=>classSearch(page)", js)  # ① 수업 칸: 다시 시도
        self.assertIn("20000", js)                  # ① 수업 칸: 20초 제한
        self.assertContains(self.client.get(self.page), "teacher-assignment.js?v=portal4")


