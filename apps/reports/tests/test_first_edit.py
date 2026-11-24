"""11/10 2차 요청: 처음 만든 리포트카드(아직 한 번도 저장 안 함)는 '열기'가 바로 수정 화면. 저장한 뒤부터는 '열기'가 보기 화면."""
from django.urls import reverse

from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class FirstEditTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get(group=self.group)
        self.card = self.batch.cards.order_by('student_name').first()
        self.client.force_login(self.teacher)
        self.list_url = reverse('reports:batch', args=[self.batch.pk])
        self.edit = reverse('reports:card', args=[self.batch.pk, self.card.pk])
        self.view = reverse('reports:card-view', args=[self.batch.pk, self.card.pk])

    def row(self):
        html = self.client.get(self.list_url).content.decode().split('<tbody>', 1)[1]
        return html.split(self.card.student_name, 1)[1].split('</tr>', 1)[0]

    def test_new_card_opens_straight_into_the_editor(self):
        row = self.row()
        self.assertRegex(row, rf'href="{self.edit}"[^>]*>\s*열기')
        self.assertIn('작성 전', row)

    def test_creating_lands_on_the_first_card_editor(self):
        response = self.create(title='26FW')  # 두 번째 묶음
        batch = ReportBatch.objects.filter(group=self.group).order_by('-pk').first()
        self.assertRedirects(response, reverse('reports:card', args=[batch.pk, batch.cards.first().pk]), fetch_redirect_response=False)

    def test_after_saving_open_shows_the_finished_view_and_edit_sits_beside_it(self):
        self.client.post(self.edit, {'save': '1', 'd.comment': '완성'})
        self.card.refresh_from_db()
        self.assertIsNotNone(self.card.saved_at)
        row = self.row()
        self.assertRegex(row, rf'href="{self.view}"[^>]*>\s*열기')
        self.assertRegex(row, rf'href="{self.edit}"[^>]*>\s*수정')
        self.assertNotIn('작성 전', row)

    def test_published_cards_count_as_finished_even_without_an_editor_save(self):
        from django.utils import timezone
        self.batch.published_at = timezone.now()
        self.batch.save(update_fields=['published_at'])
        row = self.row()
        self.assertRegex(row, rf'href="{self.view}"[^>]*>\s*열기')
        self.assertNotIn('작성 전', row)
