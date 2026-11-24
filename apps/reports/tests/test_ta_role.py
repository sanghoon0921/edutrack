"""11/10 요청: TA 계정을 새로 만들 수 있게. 강사보다 낮은 권한으로, 지금은 맡은 반 리포트카드의 코멘트만 씁니다.
(나중에 권한을 더 줄 수 있게 역할을 따로 둡니다.)"""
import re

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.lms.forms import RosterForm
from apps.lms.models import GroupStaff
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class TaRoleTests(ReportFixture):
    def setUp(self):
        super().setUp()
        U = get_user_model()
        self.ta_user = U.objects.create_user('ta_only', password='x', role='TA', display_name='박조교')
        GroupStaff.objects.create(group=self.group, user=self.ta_user, duty='TA')
        self.outsider = U.objects.create_user('ta_out', password='x', role='TA')
        self.create(user=self.admin)  # AP 리포트카드
        self.batch = ReportBatch.objects.get(group=self.group)
        self.card = self.batch.cards.get(student_no='6333')
        self.edit = reverse('reports:card', args=[self.batch.pk, self.card.pk])

    def test_admin_can_create_a_ta_account(self):
        self.client.force_login(self.admin)
        self.assertRegex(self.client.get(reverse('operations:user-create')).content.decode(), r'<option value="TA"')

    def test_roster_can_pick_ta_accounts(self):
        form = RosterForm()
        self.assertIn(self.ta_user, form.fields['staff'].queryset)

    def test_ta_menu_has_home_learning_space_report_cards_and_notices(self):
        # 11/19: TA 메뉴 = 홈·담당 학생·성적 분석·반별 학습·리포트카드·메시지·공지사항
        self.client.force_login(self.ta_user)
        html = self.client.get(reverse('dashboard')).content.decode()
        nav = html.split('<nav class="intranet-side-navigation"', 1)[1].split('</nav>', 1)[0]
        for name in ('reports:list', 'lms:rooms', 'lms:inbox', 'students:list', 'teacher_grades'):
            self.assertIn(f'href="{reverse(name)}"', nav, name)

    def test_ta_home_lists_their_report_cards(self):
        self.client.force_login(self.ta_user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('reports:batch', args=[self.batch.pk]))

    def test_ta_sees_only_assigned_classes(self):
        self.client.force_login(self.ta_user)
        self.assertContains(self.client.get(reverse('reports:list')), self.group.title)
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse('reports:list')), self.group.title)
        self.assertEqual(self.client.get(self.edit).status_code, 404)

    def test_ta_edits_every_field_but_not_structure(self):
        self.client.force_login(self.ta_user)
        html = self.client.get(self.edit).content.decode()
        names = set(re.findall(r'name="([ds]\.[^"]+)"', html))
        self.assertIn('d.comment', names)
        self.assertGreater(len(names), 1)
        self.assertNotIn('rc-block-add', html)
        self.client.post(self.edit, {'save': '1', 'd.comment': 'TA 코멘트', 'd.weeks.0.status': '미제출', 's.content': '바꿈'})
        self.card.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(self.card.data['comment'], 'TA 코멘트')
        self.assertEqual(self.card.data['weeks'][0]['status'], '미제출')
        self.assertEqual(self.batch.shared.get('content'), '바꿈')

    def test_ta_creates_and_refreshes_but_cannot_publish_or_delete(self):
        self.client.force_login(self.ta_user)
        self.assertEqual(self.client.get(reverse('reports:new')).status_code, 200)
        self.assertEqual(self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk}).status_code, 302)
        for name in ('reports:publish', 'reports:unpublish', 'reports:delete'):
            self.assertEqual(self.client.post(reverse(name, args=[self.batch.pk]), {'card': self.card.pk}).status_code, 404, name)
        self.batch.refresh_from_db()
        self.assertIsNone(self.batch.published_at)

    def test_ta_learning_space_is_limited_to_assigned_classes(self):
        self.client.force_login(self.ta_user)
        self.assertEqual(self.client.get(reverse('lms:room', args=[self.group.pk])).status_code, 200)
        self.client.force_login(self.outsider)
        self.assertIn(self.client.get(reverse('lms:room', args=[self.group.pk])).status_code, (403, 404))
