"""TOEFL 리포트카드(운영팀 요청 10.29): 정규·특강 폼, 표 이름·열 이름 고치기, 표 빼기·다시 넣기."""
from django.urls import reverse

from apps.reports import services
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class ToeflFixture(ReportFixture):
    def toefl(self, course_type='정규'):
        self.create(form='TOEFL', period_start='2026-09-14', period_end='2026-09-18', week_base='2026-09-14', course_type=course_type)
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])
        self.print_url = reverse('reports:card-print', args=[self.batch.pk, self.card.pk])

    def printed(self):
        return self.client.get(self.print_url).content.decode()


class CourseTypeFormTests(ToeflFixture):
    def test_regular_toefl_leaves_out_skill_mastery_but_can_put_it_back(self):
        self.toefl('정규')
        self.assertEqual(self.batch.shared['hidden'], ['skill'])
        self.assertNotIn('Skill Mastery</span></h3>', self.printed())
        self.assertIn('수업 시간에', self.batch.shared['intro'])
        edit = self.client.get(self.url).content.decode()
        self.assertIn(reverse('reports:section-toggle', args=[self.batch.pk, 'skill']), edit)
        self.client.post(reverse('reports:section-toggle', args=[self.batch.pk, 'skill']), {'card': self.card.pk})
        self.assertIn('Skill Mastery</span></h3>', self.printed())

    def test_special_toefl_keeps_skill_mastery(self):
        self.toefl('특강')
        self.assertEqual(self.batch.shared['hidden'], [])
        self.assertIn('Skill Mastery</span></h3>', self.printed())
        self.assertIn('Skill Mastery 시간에', self.batch.shared['intro'])


class TableEditTests(ToeflFixture):
    def setUp(self):
        super().setUp()
        self.toefl('특강')

    def test_a_table_can_be_left_out_and_put_back(self):
        toggle = reverse('reports:section-toggle', args=[self.batch.pk, 'vocab'])
        self.client.post(toggle, {'card': self.card.pk})
        self.assertNotIn('Vocabulary Test', self.printed())
        self.client.post(toggle, {'card': self.card.pk})
        self.assertIn('Vocabulary Test', self.printed())

    def test_table_titles_and_vocab_column_names_are_editable_for_the_class(self):
        self.client.post(self.url, {'s.titles.attitude': '수업 참여도', 's.vocab_heads.3': '단어 수', 'save': '1'})
        html = self.printed()
        self.assertIn('수업 참여도', html)
        self.assertIn('단어 수', html)
        other = self.batch.cards.get(student_no='7102')
        self.assertIn('단어 수', self.client.get(reverse('reports:card-print', args=[self.batch.pk, other.pk])).content.decode())

    def test_unknown_table_is_404(self):
        self.assertEqual(self.client.post(reverse('reports:section-toggle', args=[self.batch.pk, 'nope'])).status_code, 404)

    def test_cards_made_before_this_change_get_the_default_layout(self):
        for key in ('hidden', 'titles', 'vocab_heads'):
            self.batch.shared.pop(key)
        self.batch.save()
        self.assertTrue(services.ensure_weekly_layout(self.batch))
        self.assertEqual(self.batch.shared['titles']['vocab'], 'Vocabulary Test')
        self.assertEqual(self.client.get(self.url).status_code, 200)


class SatTableScopeTests(ReportFixture):
    def test_teacher_on_a_sat_card_cannot_remove_tables(self):
        self.create(form='SAT', period_start='2026-09-14', period_end='2026-09-18', week_base='2026-09-14')
        batch = ReportBatch.objects.get()
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse('reports:section-toggle', args=[batch.pk, 'vocab'])).status_code, 404)
