from dataclasses import replace
from datetime import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.contracts import (
    ExamAttemptSummary,
    StudentExamOverview,
)
from apps.assessments.cumulative_services import (
    StudentLearningInsightService,
)
from apps.assessments.detail_contracts import (
    ExamAttemptDetail,
    ExamAttemptHeader,
)
from apps.assessments.detail_repositories import (
    DemoExamDetailRepository,
)
from apps.assessments.detail_services import (
    ExamDetailService,
)
from apps.assessments.insight_services import (
    ExamInsightService,
)
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import StudentService


class FakeAssessmentService:
    def get_student_overview(
        self,
        student_id: str,
    ) -> StudentExamOverview:
        attempts = (
            ExamAttemptSummary(
                attempt_id="A1",
                exam_id="E1",
                exam_name="TEST 01",
                exam_date=datetime(
                    2026,
                    5,
                    1,
                ),
                rw_sat_score=560,
                math_sat_score=620,
                total_sat_score=1180,
                total_questions=4,
                correct_answers=2,
                wrong_answers=2,
                accuracy_rate=50.0,
                rw_attempted=True,
                math_attempted=True,
                score_type="FULL",
                score_type_label="전체 SAT",
                display_score=1180,
                max_score=1600,
            ),
            ExamAttemptSummary(
                attempt_id="A2",
                exam_id="E2",
                exam_name="TEST 02",
                exam_date=datetime(
                    2026,
                    6,
                    1,
                ),
                rw_sat_score=600,
                math_sat_score=650,
                total_sat_score=1250,
                total_questions=4,
                correct_answers=3,
                wrong_answers=1,
                accuracy_rate=75.0,
                rw_attempted=True,
                math_attempted=True,
                score_type="FULL",
                score_type_label="전체 SAT",
                display_score=1250,
                max_score=1600,
            ),
            ExamAttemptSummary(
                attempt_id="A3",
                exam_id="E3",
                exam_name="TEST 03",
                exam_date=datetime(
                    2026,
                    7,
                    1,
                ),
                rw_sat_score=640,
                math_sat_score=690,
                total_sat_score=1330,
                total_questions=4,
                correct_answers=3,
                wrong_answers=1,
                accuracy_rate=75.0,
                rw_attempted=True,
                math_attempted=True,
                score_type="FULL",
                score_type_label="전체 SAT",
                display_score=1330,
                max_score=1600,
            ),
        )

        # 실제 서비스와 동일하게 최근 시험이 앞에 오도록 반환합니다.
        return StudentExamOverview(
            status="ok",
            dsg_student_id="5743",
            dsg_student_name="김지훈",
            exam_count=3,
            full_sat_count=3,
            latest_total_score=1330,
            latest_rw_score=640,
            latest_math_score=690,
            first_delta=150,
            previous_delta=80,
            recent_attempts=tuple(
                reversed(attempts)
            ),
        )


class FakeDetailService:
    def __init__(self) -> None:
        repository = (
            DemoExamDetailRepository()
        )

        base_questions = (
            repository.list_questions(
                "5743",
                "1658",
            )
        )

        self.details = {}

        for index, attempt_id in enumerate(
            ("A1", "A2", "A3"),
            start=1,
        ):
            questions = list(
                base_questions
            )

            if attempt_id == "A2":
                questions[0] = replace(
                    questions[0],
                    topic="Reading & Writing",
                    result_code="CORRECT",
                    result_label="정답",
                    result_class="correct",
                    earned_score=1,
                )

            if attempt_id == "A3":
                questions[1] = replace(
                    questions[1],
                    topic="Reading & Writing",
                    result_code="CORRECT",
                    result_label="정답",
                    result_class="correct",
                    earned_score=1,
                    selected_answer="B",
                )

            self.details[
                attempt_id
            ] = ExamAttemptDetail(
                status="ok",
                student_id="6333",
                student_name="김지훈",
                dsg_student_id="5743",
                attempt=ExamAttemptHeader(
                    attempt_id=attempt_id,
                    exam_id=f"E{index}",
                    exam_name=f"TEST 0{index}",
                    exam_date=datetime(
                        2026,
                        4 + index,
                        1,
                    ),
                    rw_sat_score=(
                        520
                        + index * 40
                    ),
                    math_sat_score=(
                        590
                        + index * 30
                    ),
                    total_sat_score=(
                        1110
                        + index * 70
                    ),
                    total_questions=4,
                    correct_answers=2,
                    wrong_answers=2,
                    accuracy_rate=50.0,
                    total_duration_seconds=275,
                    total_duration_label="4분 35초",
                ),
                questions=tuple(
                    questions
                ),
            )

    def get_attempt_detail(
        self,
        student_id: str,
        attempt_id: str,
    ) -> ExamAttemptDetail:
        return self.details[
            attempt_id
        ]


@override_settings(
    STUDENT_INSIGHT_CACHE_SECONDS=1800,
    STUDENT_INSIGHT_MAX_ATTEMPTS=5,
    STUDENT_DATA_SOURCE="demo",
    ASSESSMENT_DATA_SOURCE="demo",
    STUDENT_TEST_STUDENT_ID="6333",
)
class StudentLearningInsightTests(
    TestCase
):
    def setUp(self):
        cache.clear()

        self.service = (
            StudentLearningInsightService(
                assessment_service=(
                    FakeAssessmentService()
                ),
                detail_service=(
                    FakeDetailService()
                ),
                exam_insight_service=(
                    ExamInsightService()
                ),
            )
        )

        student_service = StudentService(
            repository=(
                DemoStudentRepository()
            )
        )

        patchers = [
            patch(
                "apps.assessments.views.get_student_service",
                return_value=student_service,
            ),
            patch(
                (
                    "apps.assessments.views."
                    "get_student_learning_insight_service"
                ),
                return_value=self.service,
            ),
        ]

        for patcher in patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

        self.admin = User.objects.create_user(
            username="learning_admin",
            password="Admin!2026",
            role=User.Role.ADMIN,
        )

        self.student = User.objects.create_user(
            username="student_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )

    def test_cumulative_insight_is_created(self):
        insight = (
            self.service
            .get_student_insight(
                "6333"
            )
        )

        self.assertEqual(
            insight.status,
            "ok",
        )
        self.assertEqual(
            insight.analyzed_exam_count,
            3,
        )
        self.assertEqual(
            insight.total_question_count,
            12,
        )
        self.assertTrue(
            insight.area_insights
        )
        self.assertTrue(
            insight.recommendations
        )
        self.assertTrue(
            insight.review_queue
        )

    def test_cumulative_insight_uses_cache(self):
        first = (
            self.service
            .get_student_insight(
                "6333"
            )
        )

        second = (
            self.service
            .get_student_insight(
                "6333"
            )
        )

        self.assertEqual(
            first,
            second,
        )

    def test_admin_can_open_learning_insight(self):
        self.client.force_login(
            self.admin
        )

        response = self.client.get(
            reverse(
                "assessments:student-insight",
                kwargs={
                    "student_id": "6333",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "누적 학습 인사이트",
        )
        self.assertContains(
            response,
            "복습 문항 큐",
        )

    def test_student_can_open_own_learning_insight(self):
        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse(
                "assessments:student-insight",
                kwargs={
                    "student_id": "6333",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_student_cannot_open_other_insight(self):
        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse(
                "assessments:student-insight",
                kwargs={
                    "student_id": "7102",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )
