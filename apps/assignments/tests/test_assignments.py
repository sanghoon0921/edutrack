from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import (
    TestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess
from apps.students.repositories import (
    DemoStudentRepository,
)
from apps.students.services import (
    StudentService,
)

from apps.assignments.models import (
    Assignment,
    AssignmentRecipient,
    Submission,
)
from apps.assignments.services import AssignmentService


class AssignmentWorkflowTests(TestCase):
    def setUp(self):
        self.media_directory = (
            TemporaryDirectory()
        )
        self.override = override_settings(
            MEDIA_ROOT=Path(
                self.media_directory.name
            ),
            STUDENT_DATA_SOURCE="demo",
            STUDENT_TEST_STUDENT_ID="6333",
        )
        self.override.enable()
        self.addCleanup(
            self.override.disable
        )
        self.addCleanup(
            self.media_directory.cleanup
        )

        self.admin = User.objects.create_user(
            username="assignment_admin",
            password="Admin!2026",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="assignment_teacher",
            password="Teacher!2026",
            role=User.Role.TEACHER,
        )
        self.other_teacher = (
            User.objects.create_user(
                username="other_teacher",
                password="Teacher!2026",
                role=User.Role.TEACHER,
            )
        )
        self.student = User.objects.create_user(
            username="student_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )
        self.other_student = (
            User.objects.create_user(
                username="7102",
                password="Student!2026",
                role=User.Role.STUDENT,
            )
        )

        # 강사는 관리자에게 배정된 학생에게만 과제를 제공할 수 있습니다.
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="7102",
            student_name="박서연",
            assigned_by=self.admin,
        )

        student_service = StudentService(
            repository=DemoStudentRepository()
        )
        assignment_service = AssignmentService(
            student_service=student_service
        )

        patchers = [
            patch(
                (
                    "apps.assignments.views."
                    "get_student_service"
                ),
                return_value=student_service,
            ),
            patch(
                (
                    "apps.assignments.views."
                    "get_assignment_service"
                ),
                return_value=assignment_service,
            ),
        ]

        for patcher in patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

    def create_assignment(
        self,
        *,
        creator=None,
    ) -> Assignment:
        creator = (
            creator or self.teacher
        )

        assignment = (
            Assignment.objects.create(
                title="Digital SAT 오답 정리",
                description=(
                    "오답 근거를 정리하세요."
                ),
                due_at=(
                    timezone.now()
                    + timedelta(days=7)
                ),
                created_by=creator,
                is_published=True,
            )
        )

        AssignmentRecipient.objects.create(
            assignment=assignment,
            student_id="6333",
            student_name="김지훈",
        )

        return assignment

    def test_teacher_can_create_assignment(self):
        self.client.force_login(
            self.teacher
        )

        response = self.client.post(
            reverse(
                "assignments:create"
            ),
            {
                "title": "주간 과제",
                "description": "문제를 풉니다.",
                "due_at": (
                    timezone.localtime(
                        timezone.now()
                        + timedelta(days=3)
                    ).strftime(
                        "%Y-%m-%dT%H:%M"
                    )
                ),
                "student_ids": (
                    "6333\n7102"
                ),
                "points": "10",
                "is_published": "on",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )
        self.assertEqual(
            Assignment.objects.count(),
            1,
        )
        self.assertEqual(
            AssignmentRecipient.objects.count(),
            2,
        )

    def test_student_sees_only_own_assignment(self):
        assignment = (
            self.create_assignment()
        )

        AssignmentRecipient.objects.create(
            assignment=assignment,
            student_id="7102",
            student_name="이서연",
        )

        self.client.force_login(
            self.student
        )

        response = self.client.get(
            reverse(
                "assignments:my"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "Digital SAT 오답 정리",
        )

    def test_student_can_submit_text(self):
        assignment = (
            self.create_assignment()
        )

        recipient = (
            assignment.recipients.get(
                student_id="6333"
            )
        )

        self.client.force_login(
            self.student
        )

        response = self.client.post(
            reverse(
                "assignments:my-detail",
                kwargs={
                    "recipient_id": (
                        recipient.pk
                    ),
                },
            ),
            {
                "text_answer": (
                    "오답 근거를 정리했습니다."
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        submission = (
            Submission.objects.get(
                recipient=recipient
            )
        )

        self.assertIsNotNone(
            submission.submitted_at
        )
        self.assertEqual(
            recipient.status_code,
            "SUBMITTED",
        )

    def test_other_student_cannot_open_assignment(self):
        assignment = (
            self.create_assignment()
        )

        recipient = (
            assignment.recipients.get(
                student_id="6333"
            )
        )

        self.client.force_login(
            self.other_student
        )

        response = self.client.get(
            reverse(
                "assignments:my-detail",
                kwargs={
                    "recipient_id": (
                        recipient.pk
                    ),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_teacher_can_write_feedback(self):
        assignment = (
            self.create_assignment()
        )

        recipient = (
            assignment.recipients.get(
                student_id="6333"
            )
        )

        submission = (
            Submission.objects.create(
                recipient=recipient,
                text_answer="학생 답안",
                submitted_at=timezone.now(),
            )
        )

        self.client.force_login(
            self.teacher
        )

        response = self.client.post(
            reverse(
                "assignments:review",
                kwargs={
                    "submission_id": (
                        submission.pk
                    ),
                },
            ),
            {
                "feedback": (
                    "근거가 명확합니다."
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        submission.refresh_from_db()

        self.assertEqual(
            submission.feedback,
            "근거가 명확합니다.",
        )
        self.assertIsNotNone(
            submission.feedback_at
        )
        self.assertEqual(
            recipient.status_code,
            "FEEDBACK_COMPLETE",
        )

    def test_teacher_cannot_manage_other_teacher_assignment(
        self,
    ):
        assignment = (
            self.create_assignment(
                creator=self.other_teacher
            )
        )

        self.client.force_login(
            self.teacher
        )

        response = self.client.get(
            reverse(
                "assignments:update",
                kwargs={
                    "assignment_id": (
                        assignment.pk
                    ),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )



class ParentAssignmentWorkflowTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.override = override_settings(
            MEDIA_ROOT=Path(
                self.media_directory.name
            ),
            STUDENT_DATA_SOURCE="demo",
            STUDENT_TEST_STUDENT_ID="6333",
        )
        self.override.enable()
        self.addCleanup(
            self.override.disable
        )
        self.addCleanup(
            self.media_directory.cleanup
        )

        self.teacher = User.objects.create_user(
            username="parent_assignment_teacher",
            password="Teacher!2026",
            role=User.Role.TEACHER,
        )
        self.parent = User.objects.create_user(
            username="parent_assignment_user",
            password="Parent!2026",
            role=User.Role.PARENT,
        )

        from apps.accounts.models import StudentAccountLink

        StudentAccountLink.objects.create(
            user=self.parent,
            student_no="6333",
            relationship=(
                StudentAccountLink
                .Relationship.PARENT
            ),
            is_primary=True,
            is_active=True,
        )

        student_service = StudentService(
            repository=DemoStudentRepository()
        )
        assignment_service = AssignmentService(
            student_service=student_service
        )

        patchers = [
            patch(
                "apps.assignments.views.get_student_service",
                return_value=student_service,
            ),
            patch(
                "apps.assignments.views.get_assignment_service",
                return_value=assignment_service,
            ),
        ]

        for patcher in patchers:
            patcher.start()
            self.addCleanup(
                patcher.stop
            )

        self.assignment = Assignment.objects.create(
            title="학부모 확인 과제",
            description="자녀 과제를 확인합니다.",
            due_at=(
                timezone.now()
                + timedelta(days=5)
            ),
            created_by=self.teacher,
            is_published=True,
        )
        self.recipient = (
            AssignmentRecipient.objects.create(
                assignment=self.assignment,
                student_id="6333",
                student_name="김지훈",
            )
        )

    def test_parent_can_view_child_assignment(self):
        self.client.force_login(
            self.parent
        )

        response = self.client.get(
            reverse("assignments:my")
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertContains(
            response,
            "학부모 확인 과제",
        )

    def test_parent_can_submit_child_assignment(self):
        self.client.force_login(
            self.parent
        )

        response = self.client.post(
            reverse(
                "assignments:my-detail",
                kwargs={
                    "recipient_id": (
                        self.recipient.pk
                    ),
                },
            ),
            {
                "text_answer": (
                    "학부모 계정에서 제출했습니다."
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        submission = Submission.objects.get(
            recipient=self.recipient
        )
        self.assertIsNotNone(
            submission.submitted_at
        )
