"""과목자료(수업 게시판) Term·Subject 드롭다운: 목록 값, 기존 값 유지, 잘못된 값 거부, 목록 실패 시 글자 칸."""
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.classroom.forms import CourseBoardForm
from apps.classroom.models import CourseBoard
from apps.dashboard.class_catalog import TermSubjectOptions
from apps.operations.models import TeacherStudentAccess


@override_settings(STUDENT_DATA_SOURCE="demo", CLASS_CATALOG_DATA_SOURCE="demo")
class BoardTermSubjectTests(TestCase):
    def setUp(self):
        self.teacher = get_user_model().objects.create_user("board_teacher", password="x-Board!2026", role="TEACHER")
        TeacherStudentAccess.objects.create(teacher=self.teacher, student_no="6333", student_name="김지훈")

    def data(self, **values):
        return {"title": "26 SAT 정규", "term": "", "subject": "", "description": "", "student_ids": "6333", **values}

    def test_term_and_subject_are_dropdowns_of_catalog_values(self):
        form = CourseBoardForm(user=self.teacher)
        self.assertIsInstance(form.fields["term"].widget, forms.Select)
        self.assertIn(("2026 여름특강", "2026 여름특강"), list(form.fields["term"].widget.choices))
        self.assertEqual(list(form.fields["subject"].widget.choices)[0], ("", "선택 안 함"))

    def test_existing_value_outside_list_is_kept(self):
        board = CourseBoard.objects.create(title="옛 게시판", term="26 여름특강", subject="Literature", created_by=self.teacher, is_published=True)
        form = CourseBoardForm(instance=board, user=self.teacher)
        self.assertIn(("26 여름특강", "26 여름특강 (기존 값)"), list(form.fields["term"].widget.choices))
        bound = CourseBoardForm(self.data(title="옛 게시판", term="26 여름특강", subject="Literature"), instance=board, user=self.teacher)
        self.assertTrue(bound.is_valid(), bound.errors)

    def test_value_outside_list_rejected_on_create(self):
        bound = CourseBoardForm(self.data(term="아무 학기", subject="AP"), user=self.teacher)
        self.assertFalse(bound.is_valid())
        self.assertIn("term", bound.errors)

    def test_list_values_and_blank_are_accepted(self):
        for term, subject in [("2026 여름특강", "SAT"), ("", "")]:
            with self.subTest(term=term):
                bound = CourseBoardForm(self.data(term=term, subject=subject), user=self.teacher)
                self.assertTrue(bound.is_valid(), bound.errors)

    def test_lookup_failure_falls_back_to_text_input(self):
        with patch("apps.classroom.forms.term_subject_options", return_value=TermSubjectOptions((), (), False)):
            form = CourseBoardForm(user=self.teacher)
            bound = CourseBoardForm(self.data(term="직접 쓴 학기"), user=self.teacher)
            self.assertTrue(bound.is_valid(), bound.errors)
        self.assertIsInstance(form.fields["term"].widget, forms.TextInput)
        self.assertIn("직접 입력", form.fields["term"].help_text)
