from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User

from apps.communications.models import Notice, NoticeAttachment, NoticeInlineImage
from apps.communications.tests.audience_helpers import audience_flags, audience_post


class NoticeAuthoringAndFilesTests(TestCase):
    def setUp(self):
        self.temp_media = TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=Path(self.temp_media.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.temp_media.cleanup)

        self.admin = User.objects.create_user(
            username="notice_file_admin", password="1234", role=User.Role.ADMIN
        )
        self.teacher = User.objects.create_user(
            username="notice_file_teacher", password="1234", role=User.Role.TEACHER
        )
        self.other_teacher = User.objects.create_user(
            username="notice_file_other", password="1234", role=User.Role.TEACHER
        )
        self.student = User.objects.create_user(
            username="notice_file_student", password="1234", role=User.Role.STUDENT
        )

    def test_teacher_can_create_notice_with_file_and_inline_image(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("communications:notice-create"),
            {
                "title": "첨부 공지",
                "content": "안내문입니다.\n[[image:1]]",
                "audiences": audience_post("STUDENT"),
                "is_published": "on",
                "attachments": SimpleUploadedFile(
                    "guide.pdf", b"%PDF-test", content_type="application/pdf"
                ),
                "inline_images": SimpleUploadedFile(
                    "photo.png", b"fake-png", content_type="image/png"
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        notice = Notice.objects.get(title="첨부 공지")
        self.assertEqual(notice.created_by, self.teacher)
        self.assertEqual(NoticeAttachment.objects.filter(notice=notice).count(), 1)
        self.assertEqual(NoticeInlineImage.objects.filter(notice=notice).count(), 1)

        self.client.force_login(self.student)
        detail = self.client.get(
            reverse("communications:notice-detail", kwargs={"notice_id": notice.pk})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "notice-inline-figure")
        self.assertContains(detail, "photo.png")
        self.assertNotContains(detail, "[[image:1]]")
        self.assertContains(detail, "guide.pdf")

    def test_teacher_can_edit_own_notice_but_not_other_teachers_notice(self):
        own = Notice.objects.create(
            title="내 공지",
            content="내용",
            **audience_flags("ALL"),
            is_published=True,
            created_by=self.teacher,
        )
        other = Notice.objects.create(
            title="다른 강사 공지",
            content="내용",
            **audience_flags("ALL"),
            is_published=True,
            created_by=self.other_teacher,
        )
        self.client.force_login(self.teacher)
        own_response = self.client.post(
            reverse("communications:notice-update", kwargs={"notice_id": own.pk}),
            {
                "title": "수정된 내 공지",
                "content": "수정 내용",
                "audiences": ["TEACHER", "STUDENT", "PARENT"],  # 강사는 '관리자' 대상을 고를 수 없음
                "is_published": "on",
            },
        )
        self.assertEqual(own_response.status_code, 302)
        own.refresh_from_db()
        self.assertEqual(own.title, "수정된 내 공지")
        self.assertTrue(own.for_admin)  # 원래 체크된 '관리자' 대상은 강사가 고쳐도 그대로

        denied = self.client.get(
            reverse("communications:notice-update", kwargs={"notice_id": other.pk})
        )
        self.assertEqual(denied.status_code, 403)

    def test_admin_can_edit_teacher_notice(self):
        notice = Notice.objects.create(
            title="강사 공지",
            content="내용",
            **audience_flags("ALL"),
            is_published=True,
            created_by=self.teacher,
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("communications:notice-update", kwargs={"notice_id": notice.pk}),
            {
                "title": "관리자 수정",
                "content": "관리자 수정 내용",
                "audiences": audience_post("ALL"),
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        notice.refresh_from_db()
        self.assertEqual(notice.title, "관리자 수정")

    def test_teacher_cannot_choose_admin_only_audience(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("communications:notice-create"),
            {
                "title": "잘못된 대상",
                "content": "내용",
                "audiences": audience_post("ADMIN"),
                "is_published": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Notice.objects.filter(title="잘못된 대상").exists())
