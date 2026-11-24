from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink, User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.communications.models import Notice
from apps.learning.models import Discussion, DiscussionRecipient
from apps.operations.models import TeacherStudentAccess

from apps.content_editor.models import PastedImage
from apps.content_editor.services import render_pasted_content, sync_pasted_images
from apps.communications.tests.audience_helpers import audience_flags, audience_post


class PastedImageWorkflowTests(TestCase):
    def setUp(self):
        self.media_dir = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=Path(self.media_dir.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_dir.cleanup)

        self.admin = User.objects.create_user(
            username="paste_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="paste_teacher", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="paste_student", password="1234", role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username="paste_other", password="1234", role=User.Role.STUDENT
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
            is_active=True,
        )

    @staticmethod
    def png(name="capture.png"):
        return SimpleUploadedFile(
            name,
            b"\x89PNG\r\n\x1a\n" + b"stage14-image",
            content_type="image/png",
        )

    def upload(self, user=None):
        self.client.force_login(user or self.teacher)
        return self.client.post(
            reverse("content-editor:upload"),
            {"image": self.png()},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_teacher_can_upload_pasted_image_and_student_cannot(self):
        response = self.upload()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PastedImage.objects.count(), 1)
        self.assertIn("[[paste-image:", response.json()["token"])

        self.client.force_login(self.student)
        denied = self.client.post(
            reverse("content-editor:upload"), {"image": self.png("student.png")}
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(PastedImage.objects.count(), 1)

    def test_assignment_recipient_can_view_bound_image_but_other_student_cannot(self):
        response = self.upload()
        image = PastedImage.objects.get()
        assignment = Assignment.objects.create(
            title="이미지 과제",
            description=response.json()["token"],
            due_at=timezone.now() + timedelta(days=3),
            created_by=self.teacher,
            is_published=True,
        )
        AssignmentRecipient.objects.create(
            assignment=assignment, student_id="6333", student_name="김지훈"
        )
        sync_pasted_images(
            text=assignment.description,
            owner=self.teacher,
            target_type=PastedImage.TargetType.ASSIGNMENT,
            target_id=assignment.pk,
        )
        image.refresh_from_db()
        url = reverse("content-editor:image", kwargs={"token": image.token})

        self.client.force_login(self.student)
        allowed = self.client.get(url)
        # The image endpoint returns FileResponse. Explicit cleanup is required
        # on Windows because an open handle prevents TemporaryDirectory removal.
        self.addCleanup(allowed.close)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed["Content-Type"], "image/png")

        self.client.force_login(self.other_student)
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 403)

    def test_rendered_content_escapes_html_and_replaces_only_image_token(self):
        image = PastedImage.objects.create(
            owner=self.teacher,
            image=self.png(),
            original_name="capture.png",
            content_type="image/png",
            size=20,
        )
        rendered = str(
            render_pasted_content(
                f"<script>alert(1)</script>\n{image.token_markup}"
            )
        )
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn(reverse("content-editor:image", kwargs={"token": image.token}), rendered)

    def test_sync_removes_images_deleted_from_the_body(self):
        first = PastedImage.objects.create(
            owner=self.teacher,
            image=self.png("first.png"),
            original_name="first.png",
            content_type="image/png",
            size=20,
        )
        second = PastedImage.objects.create(
            owner=self.teacher,
            image=self.png("second.png"),
            original_name="second.png",
            content_type="image/png",
            size=20,
        )
        assignment = Assignment.objects.create(
            title="정리 테스트",
            description=f"{first.token_markup}\n{second.token_markup}",
            due_at=timezone.now() + timedelta(days=3),
            created_by=self.teacher,
        )
        sync_pasted_images(
            text=assignment.description,
            owner=self.teacher,
            target_type=PastedImage.TargetType.ASSIGNMENT,
            target_id=assignment.pk,
        )
        sync_pasted_images(
            text=first.token_markup,
            owner=self.teacher,
            target_type=PastedImage.TargetType.ASSIGNMENT,
            target_id=assignment.pk,
        )
        self.assertTrue(PastedImage.objects.filter(pk=first.pk).exists())
        self.assertFalse(PastedImage.objects.filter(pk=second.pk).exists())


    @override_settings(STUDENT_DATA_SOURCE="demo")
    def test_assignment_form_binds_pasted_image_and_student_renders_it(self):
        upload_response = self.upload()
        token = upload_response.json()["token"]
        self.client.force_login(self.teacher)
        now = timezone.localtime(timezone.now())
        response = self.client.post(
            reverse("assignments:create"),
            {
                "title": "붙여넣기 과제",
                "description": f"안내\n{token}",
                "available_from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "due_at": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "points": "10",
                "is_published": "on",
                "student_ids": "6333",
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment = Assignment.objects.get(title="붙여넣기 과제")
        image = PastedImage.objects.get()
        self.assertEqual(image.target_type, PastedImage.TargetType.ASSIGNMENT)
        self.assertEqual(image.target_id, assignment.pk)

        recipient = assignment.recipients.get(student_id="6333")
        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("assignments:my-detail", kwargs={"recipient_id": recipient.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(
            detail,
            reverse("content-editor:image", kwargs={"token": image.token}),
        )

    @override_settings(STUDENT_DATA_SOURCE="demo")
    def test_discussion_form_binds_pasted_image_and_student_renders_it(self):
        upload_response = self.upload()
        token = upload_response.json()["token"]
        self.client.force_login(self.teacher)
        now = timezone.localtime(timezone.now())
        response = self.client.post(
            reverse("learning:discussion-create"),
            {
                "title": "붙여넣기 토론",
                "content": f"토론 안내\n{token}",
                "available_from": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "due_at": (now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                "is_published": "on",
                "student_ids": "6333",
            },
        )
        self.assertEqual(response.status_code, 302)
        discussion = Discussion.objects.get(title="붙여넣기 토론")
        image = PastedImage.objects.get()
        self.assertEqual(image.target_type, PastedImage.TargetType.DISCUSSION)
        self.assertEqual(image.target_id, discussion.pk)

        recipient = discussion.recipients.get(student_id="6333")
        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("learning:my-discussion-detail", kwargs={"recipient_id": recipient.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(
            detail,
            reverse("content-editor:image", kwargs={"token": image.token}),
        )

    def test_notice_form_binds_pasted_image_and_learner_renders_it(self):
        upload_response = self.upload()
        token = upload_response.json()["token"]
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("communications:notice-create"),
            {
                "title": "붙여넣기 공지",
                "content": f"공지 본문\n{token}",
                "audiences": audience_post("STUDENT"),  # 강사는 '전체' 대상을 고를 수 없음
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        notice = Notice.objects.get(title="붙여넣기 공지")
        image = PastedImage.objects.get()
        self.assertEqual(image.target_type, PastedImage.TargetType.NOTICE)
        self.assertEqual(image.target_id, notice.pk)

        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("communications:notice-detail", kwargs={"notice_id": notice.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(
            detail,
            reverse("content-editor:image", kwargs={"token": image.token}),
        )

    def test_authorized_admin_removes_stale_image_uploaded_by_original_teacher(self):
        first = PastedImage.objects.create(
            owner=self.teacher,
            image=self.png("teacher-old.png"),
            original_name="teacher-old.png",
            content_type="image/png",
            size=20,
        )
        notice = Notice.objects.create(
            title="관리자 수정 공지",
            content=first.token_markup,
            **audience_flags("ALL"),
            is_published=True,
            created_by=self.teacher,
        )
        sync_pasted_images(
            text=notice.content,
            owner=self.teacher,
            target_type=PastedImage.TargetType.NOTICE,
            target_id=notice.pk,
        )
        sync_pasted_images(
            text="이미지를 제거한 본문",
            owner=self.admin,
            target_type=PastedImage.TargetType.NOTICE,
            target_id=notice.pk,
        )
        self.assertFalse(PastedImage.objects.filter(pk=first.pk).exists())
