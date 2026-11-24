"""공용 학생 목록 부품 서버 쪽: 행 표시 값, 듣는 수업, 담당 표시, 수업·반 드롭다운 항목."""
from dataclasses import replace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember
from apps.operations.models import TeacherStudentAccess
from apps.students import bulk_selector
from apps.students.course_repositories import DEMO_COURSES
from apps.students.student_rows import class_label, decorate


class RowDisplayTests(SimpleTestCase):
    def test_class_label_caps_at_two_names(self):
        classes = [{"id": str(i), "name": f"수업{i}"} for i in range(5)]
        self.assertEqual(class_label(classes), "수업0 · 수업1 외 3")
        self.assertEqual(class_label(classes[:2]), "수업0 · 수업1")
        self.assertEqual(class_label([]), "")

    def test_decorate_builds_display_and_search_values(self):
        row = decorate({
            "student_id": "6333", "name": "김지훈", "english_name": "Jeehoon Kim",
            "school": "Ekamai International School", "grade": "10학년", "branch": "본원",
            "classes": [{"id": "201", "name": "2026 여름특강 SAT Advanced", "status": "P"}],
        })
        self.assertEqual(row["school_grade"], "Ekamai International School · 10학년")
        self.assertEqual(row["class_label"], "2026 여름특강 SAT Advanced")
        self.assertEqual(row["class_ids"], "201")
        self.assertIn("jeehoon kim", row["search_text"])
        self.assertIn("6333", row["search_text"])

    def test_decorate_tolerates_missing_fields(self):
        row = decorate({"student_id": "9999", "name": "학생 9999"})
        self.assertEqual((row["school_grade"], row["class_label"], row["class_ids"]), ("", "", ""))
        self.assertEqual(row["classes"], [])


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class PickerApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("picker_admin", password="x-Picker!2026", role="ADMIN")
        self.teacher = User.objects.create_user("picker_teacher", password="x-Picker!2026", role="TEACHER")
        self.other_teacher = User.objects.create_user("picker_other", password="x-Picker!2026", role="TEACHER")
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈", assigned_by=self.admin)
        self.group = LearningGroup.objects.create(title="A반", created_by=self.teacher)
        GroupMember.objects.create(group=self.group, student_no="6333", student_name="김지훈")

    def browse(self, user, **query):
        self.client.force_login(user)
        return self.client.get(reverse("students:selector-browse"), query)

    def options(self, user, **query):
        self.client.force_login(user)
        return self.client.get(reverse("students:selector-options"), query)

    def test_rows_carry_active_classes_only(self):
        rows = self.browse(self.admin, q="6333").json()["results"]
        row = next(r for r in rows if r["student_id"] == "6333")
        self.assertEqual(row["classes"], [{"id": "201", "name": "2026 여름특강 SAT Advanced", "status": "P"}])
        self.assertEqual(row["class_label"], "2026 여름특강 SAT Advanced")
        self.assertEqual(row["school_grade"], "Ekamai International School · 10학년")

    def test_teacher_mode_marks_assigned_students(self):
        rows = {r["student_id"]: r for r in self.browse(self.teacher, mode="teacher").json()["results"]}
        self.assertTrue(rows["6333"]["assigned"])
        self.assertFalse(rows["7102"]["assigned"])

    def test_activity_mode_has_no_assigned_flag(self):
        rows = self.browse(self.teacher).json()["results"]
        self.assertEqual([r["student_id"] for r in rows], ["6333"])
        self.assertNotIn("assigned", rows[0])

    def test_class_lookup_failure_keeps_student_rows(self):
        with patch("apps.students.bulk_selector.current_classes_for", side_effect=OperationalError("secret-host")):
            response = self.browse(self.admin, q="6333")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["classes"], [])
        self.assertNotIn("secret-host", response.content.decode())

    def test_options_all_lists_active_classes_and_groups(self):
        data = self.options(self.admin, source="all").json()
        self.assertEqual({c["id"] for c in data["classes"]}, {"201", "203"})
        self.assertIn({"id": str(self.group.pk), "name": "A반"}, data["groups"])
        self.assertFalse(data["has_more"])

    def test_options_all_respects_teacher_scope(self):
        mine = self.options(self.teacher, source="all").json()
        self.assertEqual([c["id"] for c in mine["classes"]], ["201"])
        self.assertEqual([g["name"] for g in mine["groups"]], ["A반"])
        other = self.options(self.other_teacher, source="all").json()
        self.assertEqual((other["classes"], other["groups"]), ([], []))

    def test_options_all_class_name_query(self):
        data = self.options(self.admin, source="all", q="가을").json()
        self.assertEqual([c["id"] for c in data["classes"]], ["203"])

    def test_options_all_caps_class_list_at_50(self):
        base = DEMO_COURSES["6333"][0]
        many = {"6333": tuple(replace(base, assign_id=str(20000 + i), class_id=str(3000 + i), class_name=f"특강 {i:02}") for i in range(60))}
        with patch("apps.students.bulk_selector.DEMO_COURSES", many):
            data = self.options(self.admin, source="all").json()
        self.assertEqual(len(data["classes"]), 50)
        self.assertTrue(data["has_more"])


