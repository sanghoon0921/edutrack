from django.template import (
    Context,
    Template,
)
from django.test import (
    SimpleTestCase,
    override_settings,
)

from apps.assessments.repositories import (
    DemoAssessmentRepository,
)
from apps.assessments.services import (
    AssessmentService,
)


class AssessmentServiceTests(
    SimpleTestCase
):
    def setUp(self):
        self.service = AssessmentService(
            repository=(
                DemoAssessmentRepository()
            )
        )

    def test_score_overview_metrics(self):
        overview = (
            self.service
            .get_student_overview("6333")
        )

        self.assertEqual(
            overview.status,
            "ok",
        )
        self.assertEqual(
            overview.exam_count,
            5,
        )
        self.assertEqual(
            overview.full_sat_count,
            4,
        )
        self.assertEqual(
            overview.latest_total_score,
            1330,
        )
        self.assertEqual(
            overview.latest_rw_score,
            640,
        )
        self.assertEqual(
            overview.latest_math_score,
            690,
        )
        self.assertEqual(
            overview.highest_total_score,
            1330,
        )
        self.assertEqual(
            overview.first_delta,
            140,
        )
        self.assertEqual(
            overview.previous_delta,
            140,
        )

    def test_not_connected_student(self):
        overview = (
            self.service
            .get_student_overview("7102")
        )

        self.assertEqual(
            overview.status,
            "not_connected",
        )

    @override_settings(
        ASSESSMENT_DATA_SOURCE="demo"
    )
    def test_template_tag_renders_score_section(
        self,
    ):
        template = Template(
            """
            {% load assessment_tags %}
            {% student_score_overview "6333" %}
            """
        )

        html = template.render(
            Context({})
        )

        self.assertIn(
            "Digital SAT 성적",
            html,
        )
        self.assertIn(
            "최근 전체 SAT",
            html,
        )
        self.assertIn(
            "1330",
            html,
        )
