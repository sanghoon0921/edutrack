from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.models import Assignment, AssignmentRecipient
from config.cache_utils import reset_cache_circuit_for_tests, safe_cache_get

from apps.communications.context_processors import communication_summary
from apps.communications.models import Notification
from apps.communications.services import visible_unread_notification_count


@override_settings(
    COMMUNICATION_HEADER_CACHE_SECONDS=60,
    COMMUNICATION_HEADER_SCAN_LIMIT=100,
)
class Stage13NotificationHeaderTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        reset_cache_circuit_for_tests()
        self.student = User.objects.create_user(
            username="stage13_notice_student",
            password="1234",
            role=User.Role.STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="stage13_notice_teacher",
            password="1234",
            role=User.Role.TEACHER,
        )
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )

    def tearDown(self) -> None:
        cache.clear()
        reset_cache_circuit_for_tests()

    def test_notification_create_and_mark_all_invalidate_header_count(self):
        self.client.force_login(self.student)
        self.assertEqual(visible_unread_notification_count(self.student), 0)

        Notification.objects.create(
            user=self.student,
            kind=Notification.Kind.SYSTEM,
            title="새 시스템 알림",
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["unread_notification_count"], 1)

        self.client.post(reverse("communications:notification-read-all"))
        refreshed = self.client.get(reverse("dashboard"))
        self.assertEqual(refreshed.context["unread_notification_count"], 0)

    def test_non_dashboard_context_does_not_query_notice_preview(self):
        request = RequestFactory().get("/students/")
        request.user = self.student
        request.resolver_match = SimpleNamespace(view_name="students:list")

        with patch(
            "apps.communications.context_processors.visible_notices_for_user"
        ) as visible_notices:
            result = communication_summary(request)

        visible_notices.assert_not_called()
        self.assertEqual(result["latest_notice_preview"], [])


    def test_student_link_change_invalidates_scoped_header_count(self):
        assignment = Assignment.objects.create(
            title="연결 학생 확인 과제",
            description="대상 학생 전용",
            due_at=timezone.now() + timedelta(days=1),
            created_by=self.teacher,
            is_published=True,
        )
        recipient = AssignmentRecipient.objects.create(
            assignment=assignment,
            student_id="6333",
            student_name="기존 학생",
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                target_url=reverse(
                    "assignments:my-detail",
                    kwargs={"recipient_id": recipient.pk},
                ),
            ).exists()
        )
        self.assertEqual(visible_unread_notification_count(self.student), 1)

        StudentAccountLink.objects.filter(
            user=self.student,
            is_active=True,
        ).update(is_active=False, is_primary=False)
        StudentAccountLink.objects.create(
            user=self.student,
            student_no="7102",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )

        self.assertEqual(visible_unread_notification_count(self.student), 0)

    def test_cache_failure_falls_back_without_raising(self):
        with patch("config.cache_utils.cache.get", side_effect=RuntimeError("down")):
            result = safe_cache_get("stage13:test", "fallback")

        self.assertEqual(result, "fallback")
