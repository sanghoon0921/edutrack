from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.learning.models import Discussion, DiscussionRecipient

from apps.communications.models import Notice, NoticeRead, Notification
from apps.communications.tests.audience_helpers import audience_flags, audience_post


@override_settings(STUDENT_TEST_STUDENT_ID="6333")
class CommunicationsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="notice_admin",
            password="Admin!2026",
            role=User.Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="notice_teacher",
            password="Teacher!2026",
            role=User.Role.TEACHER,
        )
        self.student = User.objects.create_user(
            username="student_test",
            password="Student!2026",
            role=User.Role.STUDENT,
        )
        self.parent = User.objects.create_user(
            username="notice_parent",
            password="Parent!2026",
            role=User.Role.PARENT,
        )
        self.other_student = User.objects.create_user(
            username="7102",
            password="Student!2026",
            role=User.Role.STUDENT,
        )

        StudentAccountLink.objects.create(
            user=self.student,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.SELF,
            is_primary=True,
            is_active=True,
        )
        StudentAccountLink.objects.create(
            user=self.parent,
            student_no="6333",
            relationship=StudentAccountLink.Relationship.PARENT,
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

    def create_notice(
        self,
        *,
        audience="ALL",
        published=True,
        title="가을학기 운영 안내",
    ) -> Notice:
        return Notice.objects.create(
            title=title,
            content="수업 일정과 학습 운영에 대한 안내입니다.",
            **audience_flags(audience),
            is_pinned=True,
            is_published=published,
            created_by=self.admin,
        )

    def test_unauthenticated_notice_list_redirects_to_login(self):
        response = self.client.get(reverse("communications:notice-list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_all_notice_is_visible_to_every_role(self):
        notice = self.create_notice()

        for user in (self.admin, self.teacher, self.student, self.parent):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("communications:notice-list"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, notice.title)
                self.client.logout()

    def test_student_notice_is_hidden_from_parent_and_teacher(self):
        notice = self.create_notice(audience="STUDENT")

        self.client.force_login(self.student)
        self.assertContains(
            self.client.get(reverse("communications:notice-list")),
            notice.title,
        )
        self.client.logout()

        for user in (self.parent, self.teacher):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("communications:notice-list"))
                self.assertNotContains(response, notice.title)
                detail = self.client.get(
                    reverse(
                        "communications:notice-detail",
                        kwargs={"notice_id": notice.pk},
                    )
                )
                self.assertEqual(detail.status_code, 403)
                self.client.logout()

    def test_learner_notice_is_visible_to_student_and_parent_only(self):
        notice = self.create_notice(audience="LEARNER")

        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("communications:notice-list"))
                self.assertContains(response, notice.title)
                self.client.logout()

        self.client.force_login(self.teacher)
        self.assertNotContains(
            self.client.get(reverse("communications:notice-list")),
            notice.title,
        )

    def test_admin_can_create_notice_and_targeted_notifications(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("communications:notice-create"),
            {
                "title": "학생 전용 공지",
                "content": "학생에게만 전달합니다.",
                "audiences": audience_post("STUDENT"),
                "is_pinned": "on",
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        notice = Notice.objects.get(title="학생 전용 공지")
        self.assertIsNotNone(notice.published_at)
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                kind=Notification.Kind.NOTICE,
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                user=self.parent,
                kind=Notification.Kind.NOTICE,
            ).exists()
        )

    def test_manage_titles_open_the_notice(self):
        """공지 관리에서 제목을 누르면 바로 공지로 들어갑니다(비공개는 수정 화면)."""
        published = self.create_notice(title="공개 공지 제목")
        draft = self.create_notice(title="비공개 공지 제목", published=False)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("communications:notice-manage"))
        self.assertContains(response, f'href="{reverse("communications:notice-detail", args=[published.pk])}" class="compact-title"')
        self.assertContains(response, f'href="{reverse("communications:notice-update", args=[draft.pk])}" class="compact-title"')

    def test_non_admin_cannot_manage_notices(self):
        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.get(reverse("communications:notice-manage"))
                self.assertEqual(response.status_code, 403)
                self.client.logout()

    def test_opening_notice_records_read_and_clears_notice_notification(self):
        notice = self.create_notice(audience="STUDENT")
        notification = Notification.objects.get(
            user=self.student,
            event_key=f"notice:{notice.pk}:published",
        )
        self.assertFalse(notification.is_read)

        self.client.force_login(self.student)
        response = self.client.get(
            reverse(
                "communications:notice-detail",
                kwargs={"notice_id": notice.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            NoticeRead.objects.filter(notice=notice, user=self.student).exists()
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_notification_inbox_shows_only_current_users_items(self):
        own = Notification.objects.create(
            user=self.student,
            kind=Notification.Kind.SYSTEM,
            title="학생 알림",
        )
        Notification.objects.create(
            user=self.parent,
            kind=Notification.Kind.SYSTEM,
            title="학부모 알림",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("communications:notification-list"))

        self.assertContains(response, own.title)
        self.assertNotContains(response, "학부모 알림")

    def test_open_notification_marks_it_read(self):
        notification = Notification.objects.create(
            user=self.student,
            kind=Notification.Kind.SYSTEM,
            title="확인할 알림",
            target_url=reverse("communications:notice-list"),
        )
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "communications:notification-open",
                kwargs={"notification_id": notification.pk},
            )
        )

        self.assertRedirects(response, reverse("communications:notice-list"))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_all_notifications_read(self):
        for index in range(3):
            Notification.objects.create(
                user=self.parent,
                kind=Notification.Kind.SYSTEM,
                title=f"알림 {index}",
            )

        self.client.force_login(self.parent)
        response = self.client.post(
            reverse("communications:notification-read-all")
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Notification.objects.filter(user=self.parent, is_read=False).exists()
        )

    def test_header_displays_unread_notification_badge(self):
        Notification.objects.create(
            user=self.student,
            kind=Notification.Kind.SYSTEM,
            title="새 알림",
        )
        self.client.force_login(self.student)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "premium-notification-count")
        self.assertEqual(response.context["unread_notification_count"], 1)

    def test_dashboard_shows_latest_notice_panel(self):
        notice = self.create_notice(audience="LEARNER")
        self.client.force_login(self.parent)

        response = self.client.get(reverse("dashboard"))

        # 11/10: 학부모 홈도 학생 홈과 같은 '공지사항' 카드에 최근 공지를 보여 줍니다.
        self.assertContains(response, 'id="portal-notices-title"')
        self.assertContains(response, notice.title)

    def create_assignment_and_recipient(self):
        assignment = Assignment.objects.create(
            title="주간 오답 정리",
            description="오답 근거를 작성합니다.",
            due_at=timezone.now() + timedelta(days=5),
            created_by=self.teacher,
            is_published=True,
        )
        recipient = AssignmentRecipient.objects.create(
            assignment=assignment,
            student_id="6333",
            student_name="김지훈",
        )
        return assignment, recipient

    def test_new_assignment_notifies_linked_student_and_parent(self):
        assignment, recipient = self.create_assignment_and_recipient()
        event_key = f"assignment:{assignment.pk}:recipient:{recipient.pk}"

        self.assertTrue(
            Notification.objects.filter(user=self.student, event_key=event_key).exists()
        )
        self.assertTrue(
            Notification.objects.filter(user=self.parent, event_key=event_key).exists()
        )
        self.assertFalse(
            Notification.objects.filter(user=self.other_student, event_key=event_key).exists()
        )

    def test_submission_notifies_assignment_creator(self):
        assignment, recipient = self.create_assignment_and_recipient()
        submitted_at = timezone.now()
        Submission.objects.create(
            recipient=recipient,
            text_answer="학생 답안",
            submitted_at=submitted_at,
        )

        notification = Notification.objects.filter(
            user=self.teacher,
            kind=Notification.Kind.SUBMISSION,
        ).latest("created_at")
        self.assertIn(recipient.student_name, notification.title)
        self.assertIn("학생 또는 학부모", notification.message)

    def test_feedback_notifies_linked_student_and_parent(self):
        assignment, recipient = self.create_assignment_and_recipient()
        submission = Submission.objects.create(
            recipient=recipient,
            text_answer="학생 답안",
            submitted_at=timezone.now(),
        )
        submission.feedback = "근거가 명확합니다."
        submission.feedback_by = self.teacher
        submission.feedback_at = timezone.now()
        submission.save()

        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                self.assertTrue(
                    Notification.objects.filter(
                        user=user,
                        kind=Notification.Kind.FEEDBACK,
                    ).exists()
                )

    def _switch_student_link(self, user, student_no: str) -> None:
        StudentAccountLink.objects.filter(
            user=user,
            is_active=True,
        ).update(is_active=False, is_primary=False)
        StudentAccountLink.objects.update_or_create(
            user=user,
            student_no=student_no,
            defaults={
                "relationship": (
                    StudentAccountLink.Relationship.PARENT
                    if user.role == User.Role.PARENT
                    else StudentAccountLink.Relationship.SELF
                ),
                "is_primary": True,
                "is_active": True,
            },
        )

    def test_feedback_notification_is_visible_to_currently_linked_learners(self):
        _, recipient = self.create_assignment_and_recipient()
        submission = Submission.objects.create(
            recipient=recipient,
            text_answer="학생 답안",
            submitted_at=timezone.now(),
            feedback="근거가 명확합니다.",
            feedback_by=self.teacher,
            feedback_at=timezone.now(),
        )

        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                notification = Notification.objects.get(
                    user=user,
                    event_key__startswith=f"feedback:{submission.pk}:",
                )
                self.client.force_login(user)
                response = self.client.get(
                    reverse("communications:notification-list")
                )
                self.assertContains(response, notification.title)
                self.client.logout()

    def test_feedback_notification_is_hidden_after_student_link_changes(self):
        _, recipient = self.create_assignment_and_recipient()
        submission = Submission.objects.create(
            recipient=recipient,
            text_answer="학생 답안",
            submitted_at=timezone.now(),
            feedback="근거가 명확합니다.",
            feedback_by=self.teacher,
            feedback_at=timezone.now(),
        )

        for user in (self.student, self.parent):
            with self.subTest(role=user.role):
                notification = Notification.objects.get(
                    user=user,
                    event_key__startswith=f"feedback:{submission.pk}:",
                )
                self._switch_student_link(user, "7102")
                self.client.force_login(user)
                response = self.client.get(
                    reverse("communications:notification-list")
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, notification.title)
                self.assertEqual(response.context["unread_count"], 0)
                self.client.logout()

    def test_opening_stale_feedback_notification_redirects_instead_of_404(self):
        _, recipient = self.create_assignment_and_recipient()
        submission = Submission.objects.create(
            recipient=recipient,
            text_answer="학생 답안",
            submitted_at=timezone.now(),
            feedback="피드백",
            feedback_by=self.teacher,
            feedback_at=timezone.now(),
        )
        notification = Notification.objects.get(
            user=self.student,
            event_key__startswith=f"feedback:{submission.pk}:",
        )
        self._switch_student_link(self.student, "7102")
        self.client.force_login(self.student)

        response = self.client.post(
            reverse(
                "communications:notification-open",
                kwargs={"notification_id": notification.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse("communications:notification-list"),
        )
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_header_badge_excludes_recipient_notification_for_other_student(self):
        _, recipient = self.create_assignment_and_recipient()
        self._switch_student_link(self.student, "7102")
        self.client.force_login(self.student)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["unread_notification_count"], 0)
        self.assertNotContains(response, "premium-notification-count")
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                target_url=reverse(
                    "assignments:my-detail",
                    kwargs={"recipient_id": recipient.pk},
                ),
            ).exists()
        )

    def test_discussion_target_notification_is_visible_only_to_assigned_student(self):
        discussion = Discussion.objects.create(
            title="배정 토론",
            content="의견을 작성하세요.",
            due_at=timezone.now() + timedelta(days=2),
            created_by=self.teacher,
            is_published=True,
        )
        recipient = DiscussionRecipient.objects.create(
            discussion=discussion,
            student_id="6333",
            student_name="김지훈",
        )
        notification = Notification.objects.create(
            user=self.other_student,
            kind=Notification.Kind.SYSTEM,
            title="새 토론: 배정 토론",
            target_url=reverse(
                "learning:my-discussion-detail",
                kwargs={"recipient_id": recipient.pk},
            ),
            event_key=f"discussion:{discussion.pk}:recipient:{recipient.pk}",
        )
        self.client.force_login(self.other_student)

        response = self.client.get(reverse("communications:notification-list"))

        self.assertNotContains(response, notification.title)

    def test_notice_delete_requires_admin_and_post(self):
        notice = self.create_notice(published=False)
        self.client.force_login(self.admin)

        get_response = self.client.get(
            reverse(
                "communications:notice-delete",
                kwargs={"notice_id": notice.pk},
            )
        )
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            reverse(
                "communications:notice-delete",
                kwargs={"notice_id": notice.pk},
            )
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertFalse(Notice.objects.filter(pk=notice.pk).exists())
