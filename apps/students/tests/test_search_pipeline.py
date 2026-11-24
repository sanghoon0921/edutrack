from django.test import (
    TestCase,
    override_settings,
)

from apps.students.forms import StudentSearchForm
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import StudentService


class StudentSearchPipelineTests(
    TestCase
):
    def setUp(self):
        self.repository = (
            DemoStudentRepository()
        )
        self.service = StudentService(
            repository=self.repository
        )

    def test_search_by_name(self):
        rows = self.service.search_students(
            "김지훈"
        )

        self.assertEqual(
            len(rows),
            1,
        )
        self.assertEqual(
            rows[0].student_id,
            "6333",
        )

    def test_search_by_student_id(self):
        rows = self.service.search_students(
            "6333"
        )

        self.assertEqual(
            len(rows),
            1,
        )

    def test_search_form_accepts_one_character(self):
        form = StudentSearchForm(
            {
                "q": "김",
            }
        )

        self.assertTrue(
            form.is_valid()
        )

    @override_settings(
        STUDENT_TEST_STUDENT_ID="6333"
    )
    def test_student_test_account_mapping(self):
        student_id = (
            self.service
            .get_student_id_for_username(
                "student_test"
            )
        )

        self.assertEqual(
            student_id,
            "6333",
        )
