"""11/10 요청: 시즌마다 제목이 바뀌는지(26FW, 2627WT 등). 비워 두면 회사 시즌 코드로 정하고, 언제든 고칠 수 있습니다."""
from datetime import date

from django.test import SimpleTestCase
from django.urls import reverse

from apps.reports.formats import season_title, title_from_exam
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class SeasonCodeTests(SimpleTestCase):
    def test_company_season_codes_by_month(self):
        self.assertEqual(season_title(date(2026, 4, 1)), '26SP')
        self.assertEqual(season_title(date(2026, 7, 20)), '26SM')
        self.assertEqual(season_title(date(2026, 10, 5)), '26FW')
        self.assertEqual(season_title(date(2026, 12, 21)), '2627WT')
        self.assertEqual(season_title(date(2027, 1, 11)), '2627WT')

    def test_dsg_exam_name_gives_the_season(self):
        self.assertEqual(title_from_exam('26FW-TEST02 · 11-05'), '26FW')
        self.assertEqual(title_from_exam('2627WT-TEST01'), '2627WT')
        self.assertEqual(title_from_exam('25WT2-TEST06 · 07-20'), '25WT2')
        self.assertEqual(title_from_exam('[RW]25FA-TEST03 · 04-02'), '25FA')
        self.assertEqual(title_from_exam('Practice Test'), '')


class BlankTitleTests(ReportFixture):
    def test_blank_title_uses_the_period_season_code(self):
        self.create(title='')
        self.assertEqual(ReportBatch.objects.get(group=self.group).title, '26FW')

    def test_title_can_still_be_changed_on_the_card(self):
        self.create(title='')
        batch = ReportBatch.objects.get(group=self.group)
        card = batch.cards.first()
        self.client.post(reverse('reports:card', args=[batch.pk, card.pk]), {'save': '1', 'batch_title': '2627WT'})
        batch.refresh_from_db()
        self.assertEqual(batch.title, '2627WT')

    def test_new_form_takes_the_term_instead_of_a_title(self):
        # 11/17: 제목(시즌)을 따로 쓰지 않고 Term 을 고릅니다.
        self.client.force_login(self.admin)
        page = self.client.get(reverse('reports:new'))
        self.assertContains(page, 'name="term"')
        self.assertNotContains(page, 'name="title"')
