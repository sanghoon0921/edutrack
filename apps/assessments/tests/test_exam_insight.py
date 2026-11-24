from django.test import SimpleTestCase

from apps.assessments.detail_repositories import (
    DemoExamDetailRepository,
)
from apps.assessments.insight_services import (
    ExamInsightService,
)


class ExamInsightServiceTests(
    SimpleTestCase
):
    def setUp(self):
        repository = (
            DemoExamDetailRepository()
        )

        self.questions = (
            repository.list_questions(
                "5743",
                "1658",
            )
        )

        self.insight = (
            ExamInsightService().build(
                self.questions
            )
        )

    def test_exam_insight_counts(self):
        self.assertEqual(
            self.insight.status,
            "ok",
        )
        self.assertEqual(
            self.insight.total_count,
            4,
        )
        self.assertEqual(
            self.insight.correct_count,
            1,
        )
        self.assertEqual(
            self.insight.review_count,
            3,
        )
        self.assertEqual(
            self.insight.wrong_count,
            1,
        )
        self.assertEqual(
            self.insight.partial_count,
            1,
        )
        self.assertEqual(
            self.insight.unanswered_count,
            1,
        )

    def test_area_insights_are_created(self):
        self.assertTrue(
            self.insight.area_insights
        )
        self.assertIsNotNone(
            self.insight.strongest_area
        )
        self.assertIsNotNone(
            self.insight.priority_area
        )
        self.assertIsNotNone(
            self.insight.slowest_area
        )

    def test_slow_question_is_identified(self):
        self.assertGreaterEqual(
            self.insight.slow_count,
            1,
        )
        self.assertTrue(
            self.insight.slow_question_ids
        )

    def test_empty_questions(self):
        insight = (
            ExamInsightService().build(
                []
            )
        )

        self.assertEqual(
            insight.status,
            "empty",
        )
