from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.operations.models import TeacherStudentAccess
from apps.students.repositories import DemoStudentRepository
from apps.students.services import StudentService

from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.assignments.services import AssignmentService


@override_settings(STUDENT_DATA_SOURCE="demo", STUDENT_TEST_STUDENT_ID="6333")
class RefinedAssignmentPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="refined_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="refined_teacher", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="student_test", password="1234", role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username="other_refined_student", password="1234", role=User.Role.STUDENT
        )
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.other_student,
            student_no="7102",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        TeacherStudentAccess.objects.create(
            teacher=self.teacher,
            student_no="6333",
            student_name="김지훈",
            assigned_by=self.admin,
        )
        service = StudentService(repository=DemoStudentRepository())
        assignment_service = AssignmentService(student_service=service)
        self.patchers = [
            patch("apps.assignments.views.get_student_service", return_value=service),
            patch("apps.assignments.views.get_assignment_service", return_value=assignment_service),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def assignment(self, *, due_delta=timedelta(days=2), available_delta=timedelta(days=-1)):
        assignment = Assignment.objects.create(
            title="권한 검증 과제",
            description="검증용",
            available_from=timezone.now() + available_delta,
            due_at=timezone.now() + due_delta,
            points=10,
            created_by=self.teacher,
            is_published=True,
        )
        recipient = AssignmentRecipient.objects.create(
            assignment=assignment,
            student_id="6333",
            student_name="김지훈",
        )
        return assignment, recipient

    def test_student_post_after_due_is_forbidden(self):
        _, recipient = self.assignment(due_delta=timedelta(minutes=-1))
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("assignments:my-detail", kwargs={"recipient_id": recipient.pk}),
            {"text_answer": "늦은 답안"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Submission.objects.filter(recipient=recipient).exists())

    def test_student_get_after_due_is_read_only(self):
        _, recipient = self.assignment(due_delta=timedelta(minutes=-1))
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("assignments:my-detail", kwargs={"recipient_id": recipient.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_submit"])
        self.assertContains(response, "마감")

    def test_teacher_cannot_edit_after_due_but_admin_can(self):
        assignment, _ = self.assignment(due_delta=timedelta(minutes=-1))
        url = reverse("assignments:update", kwargs={"assignment_id": assignment.pk})
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_future_assignment_is_not_visible_to_student(self):
        assignment, recipient = self.assignment(available_delta=timedelta(days=1))
        self.client.force_login(self.student)
        listing = self.client.get(reverse("assignments:my"))
        detail = self.client.get(
            reverse("assignments:my-detail", kwargs={"recipient_id": recipient.pk})
        )
        self.assertNotContains(listing, assignment.title)
        self.assertEqual(detail.status_code, 404)

    def test_other_student_assignment_is_hidden_and_post_is_404(self):
        _, recipient = self.assignment()
        self.client.force_login(self.other_student)
        listing = self.client.get(reverse("assignments:my"))
        detail_url = reverse("assignments:my-detail", kwargs={"recipient_id": recipient.pk})
        self.assertNotContains(listing, "권한 검증 과제")
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(
            self.client.post(detail_url, {"text_answer": "다른 학생 답안"}).status_code,
            404,
        )

    def test_teacher_cannot_assign_unallocated_student(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("assignments:create"),
            {
                "title": "담당 외 과제",
                "description": "검증",
                "available_from": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "due_at": timezone.localtime(timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "points": "10",
                "student_ids": "7102",
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Assignment.objects.filter(title="담당 외 과제").exists())
