"""DSG 성적의 Module 탭: Module만 따로 본 시험목록."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.assessments import repositories
from apps.assessments.contracts import ModuleAttemptSummary
from apps.assessments.repositories import DemoAssessmentRepository, DsgAssessmentRepository
from apps.assessments.services import AssessmentService


class ModuleAttemptServiceTests(SimpleTestCase):
    def test_demo_student_has_module_tests_newest_first(self):
        overview = AssessmentService(repository=DemoAssessmentRepository()).get_student_overview("6333")
        self.assertEqual(overview.status, "ok")
        names = [m.module_name for m in overview.module_attempts]
        self.assertEqual(names, ["RW Module 2 · Hard", "Math Module 1"])
        latest = overview.module_attempts[0]
        self.assertEqual((latest.section_label, latest.correct_answers, latest.total_questions), ("RW", 20, 27))

    def test_module_tests_are_shown_even_without_full_exams(self):
        class OnlyModules(DemoAssessmentRepository):
            def list_exam_attempts(self, dsg_student_id):
                return []

        overview = AssessmentService(repository=OnlyModules()).get_student_overview("6333")
        self.assertEqual(overview.status, "empty")
        self.assertEqual(len(overview.module_attempts), 2)


@override_settings(STUDENT_DATA_SOURCE="demo", ASSESSMENT_DATA_SOURCE="demo")
class ModuleTabPageTests(TestCase):
    def test_student_detail_shows_exam_and_module_tabs(self):
        admin = get_user_model().objects.create_user("module_admin", password="x-Module!2026", role="ADMIN")
        self.client.force_login(admin)
        response = self.client.get(reverse("students:detail", args=["6333"]))
        self.assertEqual(response.status_code, 200)
        for text in ['data-score-tab="exam"', 'data-score-tab="module"', "Module 시험", "RW Module 2 · Hard", "20 / 27"]:
            self.assertContains(response, text)

    def test_module_without_correct_counts_shows_answered_questions(self):
        class NoCounts(DemoAssessmentRepository):
            def list_module_attempts(self, dsg_student_id):
                return [ModuleAttemptSummary(attempt_id="9", module_id="9", module_name="26 Summer SEC 28", taken_at=datetime(2026, 9, 26, 19),
                                             section_label="RW", total_questions=12, correct_answers=0, wrong_answers=0,
                                             accuracy_rate=0.0, answered_questions=12)]
        admin = get_user_model().objects.create_user("module_admin2", password="x-Module!2026", role="ADMIN")
        self.client.force_login(admin)
        with patch("apps.assessments.services.get_assessment_repository", return_value=NoCounts()):
            response = self.client.get(reverse("students:detail", args=["6333"]))
        self.assertContains(response, "26 Summer SEC 28")
        self.assertContains(response, "12 / 12")
        self.assertContains(response, "푼 문항")
        self.assertNotContains(response, "정답 0 · 오답 0")
