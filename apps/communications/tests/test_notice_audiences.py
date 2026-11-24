"""공지 대상 여러 개 체크: 관리자·강사·학생·학부모 중 여러 그룹을 고른다(강사는 강사·학생·학부모만)."""
import importlib

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User
from apps.communications.forms import NoticeForm
from apps.communications.models import Notice
from apps.communications.services import can_view_notice, users_for_notice, visible_notices_for_user


@override_settings(STUDENT_DATA_SOURCE="demo")
class NoticeAudienceCheckboxTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("aud_admin", password="x-Aud!2026", role=User.Role.ADMIN)
        self.teacher = User.objects.create_user("aud_teacher", password="x-Aud!2026", role=User.Role.TEACHER)
        self.student = User.objects.create_user("aud_student", password="x-Aud!2026", role=User.Role.STUDENT)
        self.parent = User.objects.create_user("aud_parent", password="x-Aud!2026", role=User.Role.PARENT)
        StudentAccountLink.objects.create(user=self.student, student_no="6333", relationship="SELF", is_primary=True, is_active=True)
        StudentAccountLink.objects.create(user=self.parent, student_no="6333", relationship="PARENT", is_primary=True, is_active=True)

    def test_audience_is_a_set_of_checkboxes_limited_by_role(self):
        admin_form, teacher_form = NoticeForm(user=self.admin), NoticeForm(user=self.teacher)
        self.assertEqual([v for v, _ in admin_form.fields["audiences"].choices], ["ADMIN", "TEACHER", "STUDENT", "PARENT"])
        self.assertEqual([v for v, _ in teacher_form.fields["audiences"].choices], ["TEACHER", "STUDENT", "PARENT"])
        self.assertIn('type="checkbox" name="audiences"', str(admin_form["audiences"]))

    def test_admin_sends_one_notice_to_teachers_and_parents(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("communications:notice-create"), {
            "title": "강사·학부모 공지", "content": "본문", "category": "ACADEMY", "audiences": ["TEACHER", "PARENT"]})
        self.assertEqual(response.status_code, 302)
        notice = Notice.objects.get(title="강사·학부모 공지")
        self.assertEqual((notice.for_admin, notice.for_teacher, notice.for_student, notice.for_parent), (False, True, False, True))
        self.assertEqual(notice.audience_display, "강사 · 학부모")
        self.assertTrue(can_view_notice(self.teacher, notice))
        self.assertTrue(can_view_notice(self.parent, notice))
        self.assertFalse(can_view_notice(self.student, notice))
        self.assertEqual(set(users_for_notice(notice)), {self.teacher, self.parent})

    def test_teacher_cannot_address_admins(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("communications:notice-create"), {
            "title": "관리자 대상 시도", "content": "본문", "category": "ACADEMY", "audiences": ["ADMIN"]})
        self.assertFalse(Notice.objects.filter(title="관리자 대상 시도").exists())

    def test_at_least_one_audience_is_required(self):
        form = NoticeForm({"title": "대상 없음", "content": "본문", "category": "ACADEMY"}, user=self.admin)
        self.assertFalse(form.is_valid())
        self.assertIn("audiences", form.errors)

    def test_all_four_reads_as_everyone_and_reaches_every_role(self):
        notice = Notice.objects.create(title="전체 공지", content="본문", created_by=self.admin, is_published=True,
                                       for_admin=True, for_teacher=True, for_student=True, for_parent=True)
        self.assertEqual(notice.audience_display, "전체")
        for user in (self.admin, self.teacher, self.student, self.parent):
            self.assertIn("전체 공지", visible_notices_for_user(user).values_list("title", flat=True))

    def test_editing_keeps_the_checked_groups(self):
        notice = Notice.objects.create(title="수정용", content="본문", created_by=self.admin, is_published=True,
                                       for_student=True, for_parent=True)
        self.assertEqual(sorted(NoticeForm(instance=notice, user=self.admin)["audiences"].initial), ["PARENT", "STUDENT"])

    def test_old_single_audience_values_become_checked_groups(self):
        migration = importlib.import_module("apps.communications.migrations.0004_notice_audience_groups")
        self.assertEqual(migration.FLAGS_FOR_OLD_AUDIENCE["ALL"], ("for_admin", "for_teacher", "for_student", "for_parent"))
        self.assertEqual(migration.FLAGS_FOR_OLD_AUDIENCE["STAFF"], ("for_admin", "for_teacher"))
        self.assertEqual(migration.FLAGS_FOR_OLD_AUDIENCE["LEARNER"], ("for_student", "for_parent"))
        self.assertEqual(migration.FLAGS_FOR_OLD_AUDIENCE["PARENT"], ("for_parent",))
