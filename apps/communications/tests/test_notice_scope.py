"""공지 대상(관리자·강사별)과 학원 공지 / 반 공지 구분."""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import StudentAccountLink, User
from apps.communications.forms import NoticeForm
from apps.communications.models import Notice
from apps.communications.services import can_view_notice, users_for_notice, visible_notices_for_user
from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember
from apps.communications.tests.audience_helpers import audience_flags, audience_post


def link(user, student_no, relationship="SELF"):
    StudentAccountLink.objects.create(user=user, student_no=student_no, relationship=relationship, is_primary=True, is_active=True)


@override_settings(STUDENT_DATA_SOURCE="demo")
class NoticeAudienceByRoleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("scope_admin", password="x-Scope!2026", role=User.Role.ADMIN)
        self.teacher = User.objects.create_user("scope_teacher", password="x-Scope!2026", role=User.Role.TEACHER)

    def test_teacher_can_address_only_teachers_students_and_parents(self):
        values = [value for value, _ in NoticeForm(user=self.teacher).fields["audiences"].choices]
        self.assertEqual(values, ["TEACHER", "STUDENT", "PARENT"])

    def test_admin_can_address_everyone(self):
        values = {value for value, _ in NoticeForm(user=self.admin).fields["audiences"].choices}
        self.assertEqual(values, {"ADMIN", "TEACHER", "STUDENT", "PARENT"})

    def test_teacher_cannot_post_a_notice_to_everyone(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("communications:notice-create"), {
            "title": "전체 공지 시도", "content": "본문", "audiences": audience_post("ALL"), "category": "ACADEMY", "is_published": "on"})
        self.assertFalse(Notice.objects.filter(title="전체 공지 시도").exists())


@override_settings(STUDENT_DATA_SOURCE="demo")
class AcademyAndClassNoticeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("kind_admin", password="x-Kind!2026", role=User.Role.ADMIN)
        self.teacher = User.objects.create_user("kind_teacher", password="x-Kind!2026", role=User.Role.TEACHER)
        self.other_teacher = User.objects.create_user("kind_teacher2", password="x-Kind!2026", role=User.Role.TEACHER)
        self.in_class = User.objects.create_user("kind_student", password="x-Kind!2026", role=User.Role.STUDENT)
        self.parent = User.objects.create_user("kind_parent", password="x-Kind!2026", role=User.Role.PARENT)
        self.outside = User.objects.create_user("kind_other", password="x-Kind!2026", role=User.Role.STUDENT)
        link(self.in_class, "6333")
        link(self.parent, "6333", "PARENT")
        link(self.outside, "7102")
        self.group = LearningGroup.objects.create(title="SAT A반", created_by=self.teacher)
        self.other_group = LearningGroup.objects.create(title="TOEFL B반", created_by=self.other_teacher)
        GroupMember.objects.create(group=self.group, student_no="6333", student_name="김지훈")
        GroupMember.objects.create(group=self.other_group, student_no="7102", student_name="이서연")
        self.academy = Notice.objects.create(title="학원 휴원 안내", content="본문", **audience_flags("ALL"), created_by=self.admin, is_published=True)
        self.class_notice = Notice.objects.create(title="A반 숙제 안내", content="본문", **audience_flags("ALL"), category="CLASS",
                                                  group=self.group, created_by=self.teacher, is_published=True)

    def visible(self, user):
        return set(visible_notices_for_user(user).values_list("title", flat=True))

    def test_class_notice_reaches_only_that_class(self):
        self.assertEqual(self.visible(self.in_class), {"학원 휴원 안내", "A반 숙제 안내"})
        self.assertEqual(self.visible(self.parent), {"학원 휴원 안내", "A반 숙제 안내"})
        self.assertEqual(self.visible(self.outside), {"학원 휴원 안내"})
        self.assertEqual(self.visible(self.other_teacher), {"학원 휴원 안내"})
        self.assertEqual(self.visible(self.teacher), {"학원 휴원 안내", "A반 숙제 안내"})
        self.assertTrue(can_view_notice(self.admin, self.class_notice))
        self.assertFalse(can_view_notice(self.outside, self.class_notice))

    def test_class_notice_notifies_only_that_class(self):
        recipients = set(users_for_notice(self.class_notice))
        self.assertIn(self.in_class, recipients)
        self.assertIn(self.teacher, recipients)
        self.assertNotIn(self.outside, recipients)
        self.assertNotIn(self.other_teacher, recipients)

    def test_list_marks_each_kind_with_its_own_colour_and_can_filter(self):
        self.client.force_login(self.in_class)
        page = self.client.get(reverse("communications:notice-list"))
        self.assertContains(page, '<span class="notice-kind is-academy">학원 공지</span>', html=False)
        self.assertContains(page, '<span class="notice-kind is-class">반 공지 · SAT A반</span>', html=False)
        only_class = self.client.get(reverse("communications:notice-list"), {"kind": "class"})
        self.assertContains(only_class, "A반 숙제 안내")
        self.assertNotContains(only_class, "학원 휴원 안내")

    def test_teacher_picks_a_class_from_own_classes_only(self):
        form = NoticeForm(user=self.teacher)
        self.assertEqual(list(form.fields["group"].queryset), [self.group])
        bad = NoticeForm({"title": "반 공지", "content": "본문", "audiences": audience_post("STUDENT"), "category": "CLASS"}, user=self.teacher)
        self.assertFalse(bad.is_valid())
        self.assertIn("group", bad.errors)

    def test_academy_notice_drops_a_chosen_class(self):
        form = NoticeForm({"title": "학원 공지", "content": "본문", "audiences": audience_post("STUDENT"), "category": "ACADEMY",
                           "group": self.group.pk}, user=self.teacher)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["group"])
