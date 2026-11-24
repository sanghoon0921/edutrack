from unittest.mock import patch

from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse

from apps.accounts.models import User
from apps.operations.models import TeacherStudentAccess
from apps.assessments.detail_repositories import (
    DemoExamDetailRepository,
)
from apps.assessments.detail_services import (
    ExamDetailService,
)
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import StudentService


@override_settings(
    STUDENT_DATA_SOURCE="demo",
    ASSESSMENT_DATA_SOURCE="demo",
    STUDENT_TEST_STUDENT_ID="6333",
)
class ExamAttemptDetailTests(TestCase):
    def setUp(self):
        student_service = StudentService(
            repository=(
                DemoStudentRepository()
            )
        )

        detail_service = ExamDetailService(
            repository=(
                DemoExamDetailRepository()
            )
        )

        patchers = [
            patch(
                (
                    "apps.assessments.views."
                    "get_student_service"
                ),
                return_value=student_service,
            ),
            patch(
                (
                    "apps.assessments.views."
                    "get_exam_detail_service"
                ),
                return_value=detail_service,
            ),
        ]

        for patcher in patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

        self.admin = User.objects.create_user(
            username="exam_detail_admin",
            password="Admin!2026",
            role=User.Role.ADMIN,
        )

        self.student = User.objects.create_user(
            username="student_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="exam_detail_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )

    def test_admin_can_open_exam_detail(self):
        self.client.force_login(
            self.admin
        )

        response = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={
                    "student_id": "6333",
                    "attempt_id": "919696",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "25WT2-TEST06",
        )
        self.assertContains(
            response,
            "문항 결과",
        )
        self.assertContains(
            response,
            "부분점수",
        )

    def test_student_can_open_own_exam(self):
        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={
                    "student_id": "6333",
                    "attempt_id": "919696",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_student_cannot_open_other_student_exam(self):
        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={
                    "student_id": "7102",
                    "attempt_id": "919696",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_teacher_can_open_assigned_student_exam_only(self):
        self.client.force_login(self.teacher)
        assigned = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={"student_id": "6333", "attempt_id": "919696"},
            )
        )
        unassigned = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={"student_id": "7102", "attempt_id": "919696"},
            )
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(unassigned.status_code, 403)

    def test_unknown_attempt_returns_404(self):
        self.client.force_login(
            self.admin
        )

        response = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={
                    "student_id": "6333",
                    "attempt_id": "missing",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_question_selection(self):
        self.client.force_login(
            self.admin
        )

        response = self.client.get(
            reverse(
                "assessments:attempt-detail",
                kwargs={
                    "student_id": "6333",
                    "attempt_id": "919696",
                },
            ),
            {
                "question": "101",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "첫 번째 모의 문항",
        )
