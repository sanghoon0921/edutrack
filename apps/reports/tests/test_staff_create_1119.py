"""11/19 TA 권한 결정: 리포트카드 '제작 및 코멘트 작성(발송 불가)'. 강사도 함께 엽니다(자기 반).
만들기·내용 작성·데이터 다시 불러오기 = 관리자·강사·TA. 발송(공개)·발송 취소·삭제·표 바꾸기(행·구역) = 관리자만."""
import re

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture
from apps.reports.views import edit_scope

User = get_user_model()


class StaffCreateTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.ta.role = User.Role.TA
        self.ta.save(update_fields=['role'])
        self.other_group = LearningGroup.objects.create(title='다른 반 SAT', created_by=self.other_teacher)

    def test_teacher_and_ta_can_open_new_form_with_own_groups_only(self):
        for user in (self.teacher, self.ta):
            self.client.force_login(user)
            response = self.client.get(reverse('reports:new'))
            self.assertEqual(response.status_code, 200, user.username)
            groups = set(response.context['form'].fields['group'].queryset)
            self.assertIn(self.group, groups)
            self.assertNotIn(self.other_group, groups)
            self.assertIn(f'href="{reverse("reports:new")}"', self.client.get(reverse('reports:list')).content.decode())

    def test_ta_creates_batch_for_own_group(self):
        response = self.create(user=self.ta)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ReportBatch.objects.filter(group=self.group).exists())

    def test_ta_cannot_create_for_other_group(self):
        self.create(user=self.ta, group=self.other_group.pk)
        self.assertFalse(ReportBatch.objects.filter(group=self.other_group).exists())

    def test_staff_write_every_field_but_not_structure(self):
        self.create()
        batch = ReportBatch.objects.get()
        card = batch.cards.get(student_no='6333')
        for user in (self.teacher, self.ta):
            scope = edit_scope(user, batch)
            self.assertIsNotNone(scope)
            self.client.force_login(user)
            html = self.client.get(reverse('reports:card', args=[batch.pk, card.pk])).content.decode()
            names = set(re.findall(r'name="([ds]\.[^"]+)"', html))
            self.assertIn('d.comment', names)
            self.assertGreater(len(names), 1, user.username)
            self.assertNotIn('rc-block-add', html)
        self.assertIsNone(edit_scope(self.admin, batch))

    def test_staff_can_refresh(self):
        self.create()
        batch = ReportBatch.objects.get()
        self.client.force_login(self.ta)
        self.assertEqual(self.client.post(reverse('reports:refresh', args=[batch.pk])).status_code, 302)

    def test_staff_cannot_publish_or_delete(self):
        self.create()
        batch = ReportBatch.objects.get()
        for user in (self.teacher, self.ta):
            self.client.force_login(user)
            for name in ('reports:publish', 'reports:unpublish', 'reports:delete'):
                self.assertEqual(self.client.post(reverse(name, args=[batch.pk])).status_code, 404, (user.username, name))
        batch.refresh_from_db()
        self.assertIsNone(batch.published_at)
        self.assertTrue(ReportBatch.objects.filter(pk=batch.pk).exists())
