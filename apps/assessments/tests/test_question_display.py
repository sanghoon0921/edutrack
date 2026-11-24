from django.test import SimpleTestCase

from apps.assessments.detail_repositories import (
    DemoExamDetailRepository,
)


class QuestionDisplayNormalizationTests(
    SimpleTestCase
):
    def test_demo_question_scores_are_not_abnormally_large(self):
        repository = DemoExamDetailRepository()

        questions = repository.list_questions(
            "5743",
            "1658",
        )

        self.assertTrue(questions)

        for question in questions:
            self.assertLessEqual(
                question.max_score,
                2,
            )

    def test_answer_summary_fields_are_available(self):
        repository = DemoExamDetailRepository()

        question = repository.list_questions(
            "5743",
            "1658",
        )[0]

        self.assertEqual(
            question.selected_answer,
            "B",
        )
        self.assertEqual(
            question.correct_answer,
            "B",
        )
