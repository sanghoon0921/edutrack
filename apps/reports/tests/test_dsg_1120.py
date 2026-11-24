"""SAT 리포트 DSG 집계 기준 정리(11/20 사용자 '추천대로 + 시험 고를 수 있게, 날짜 등').

1. 재응시: 반 평균·자동 칸 모두 학생마다 그 시험의 마지막 기록 하나만(DSG 재응시 11,535쌍).
2. 지난주·지난달 칸: 한 주 카드는 바로 앞 7일, 월간 카드는 바로 앞 같은 길이.
3. 이번 칸 시험을 골랐으면 지난 칸은 그 시험보다 먼저 본 다른 시험 중 최근 것(고른 개수만큼).
4. 지난 칸 시험도 직접 고를 수 있고, 고르는 표에 종류·응시일·응시 학생 수가 보입니다.
5. 만든 뒤에도 '모의고사 고르기' 화면에서 바꾸고 바로 다시 불러옵니다.
"""
from datetime import date, datetime

from django.test import SimpleTestCase
from django.urls import reverse

from apps.reports import sources
from apps.reports.models import ReportBatch

from .test_sources import attempt
from .test_views import ReportFixture


class RetakeTests(SimpleTestCase):
    def test_class_average_uses_each_students_last_try(self):
        mine = [attempt('7', datetime(2026, 7, 1, 10), 500, 600), attempt('7', datetime(2026, 7, 3, 10), 600, 640)]
        other = [attempt('7', datetime(2026, 7, 2, 10), 700, 700)]
        self.assertEqual(sources.class_averages([mine, other])['7'], {'rw': 650, 'math': 670})

    def test_window_shows_a_retaken_exam_once_with_the_last_try(self):
        mine = [attempt('7', datetime(2026, 7, 14, 10), 540, 600), attempt('8', datetime(2026, 7, 15, 10), 550, 610),
                attempt('7', datetime(2026, 7, 16, 10), 600, 650)]
        slots = sources.dsg_slots(mine, date(2026, 7, 13), date(2026, 7, 17), {})
        self.assertEqual([(s['date'], s['rw']) for s in slots['this']], [('07-15', '550'), ('07-16', '600'), ('', '')])


class PreviousSpanTests(SimpleTestCase):
    def test_monthly_card_looks_back_the_same_length(self):
        self.assertEqual(sources.previous_span(date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 8, 31), date(2026, 9, 30)))

    def test_weekly_card_still_looks_back_seven_days(self):
        self.assertEqual(sources.previous_span(date(2026, 11, 9), date(2026, 11, 11)), (date(2026, 11, 2), date(2026, 11, 8)))

    def test_monthly_last_slots_include_earlier_september_exams(self):
        mine = [attempt('1', datetime(2026, 9, 3, 10), 500, 500), attempt('2', datetime(2026, 9, 28, 10), 520, 520),
                attempt('3', datetime(2026, 10, 15, 10), 560, 560)]
        slots = sources.dsg_slots(mine, date(2026, 10, 1), date(2026, 10, 31), {})
        self.assertEqual([s['date'] for s in slots['last']], ['09-03', '09-28', ''])
        self.assertEqual([s['date'] for s in slots['this']], ['10-15', '', ''])


class BeforeChosenTests(SimpleTestCase):
    MINE = [attempt('3', datetime(2026, 9, 1, 10), 500, 500), attempt('4', datetime(2026, 9, 10, 10), 520, 520),
            attempt('5', datetime(2026, 9, 24, 10), 560, 560), attempt('6', datetime(2026, 9, 26, 10), 580, 580)]

    def test_previous_exam_is_the_latest_one_before_the_chosen(self):
        slots = sources.before_chosen_slots(self.MINE, ['5'], date(2026, 11, 16), {}, 1)
        self.assertEqual([s['date'] for s in slots], ['09-10', '', ''])

    def test_special_course_compares_two_previous_exams(self):
        slots = sources.before_chosen_slots(self.MINE, ['5', '6'], date(2026, 11, 16), {}, 2)
        self.assertEqual([s['date'] for s in slots], ['09-01', '09-10', ''])

    def test_student_who_missed_the_chosen_exam_uses_period_start(self):
        slots = sources.before_chosen_slots(self.MINE[:2], ['5'], date(2026, 9, 5), {}, 1)
        self.assertEqual([s['date'] for s in slots], ['09-01', '', ''])


class PickerTests(ReportFixture):
    def sat(self, **extra):
        return self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20', **extra)

    def test_new_page_lists_exams_with_kind_dates_and_takers(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse('reports:new'), {'group': self.group.pk})
        self.assertContains(page, '응시 학생')
        self.assertContains(page, '[RW]25FA-TEST03')
        self.assertContains(page, 'R/W')
        self.assertContains(page, '04-02')
        self.assertContains(page, 'name="mock_prev"')

    def test_chosen_exam_compares_with_the_exam_before_it(self):
        self.sat(mock_exams=['1658'])
        card = ReportBatch.objects.get().cards.get(student_no='6333').data
        self.assertEqual((card['mock']['this'][0]['date'], card['mock']['this'][0]['rw']), ('07-20', '640'))
        self.assertEqual([(s['date'], s['rw']) for s in card['mock']['last']], [('06-12', '500'), ('', ''), ('', '')])

    def test_previous_exam_can_be_chosen_too(self):
        self.sat(mock_exams=['1658'], mock_prev=['1580'])
        batch = ReportBatch.objects.get()
        self.assertEqual(batch.shared['mock_prev'][0]['id'], '1580')
        last = batch.cards.get(student_no='6333').data['mock']['last']
        self.assertEqual((last[0]['date'], last[0]['rw']), ('03-10', '520'))

    def test_same_exam_cannot_be_both_this_and_previous(self):
        response = self.sat(mock_exams=['1658'], mock_prev=['1658'])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '같은 시험')
        self.assertFalse(ReportBatch.objects.exists())

    def test_regular_course_allows_one_previous_exam(self):
        response = self.sat(mock_exams=['1658'], mock_prev=['1580', '1655'])
        self.assertContains(response, '1개까지')
        self.assertFalse(ReportBatch.objects.exists())


class ChangeExamsTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20', mock_exams=['1658'])
        self.batch = ReportBatch.objects.get()
        self.url = reverse('reports:mocks', args=[self.batch.pk])

    def test_page_shows_current_choice(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="mock_exams" value="1658" checked')

    def test_changing_exams_reloads_the_cards(self):
        response = self.client.post(self.url, {'mock_exams': ['1655'], 'mock_prev': ['1580']})
        self.assertEqual(response.status_code, 302)
        self.batch.refresh_from_db()
        self.assertEqual([m['id'] for m in self.batch.shared['mock_exams']], ['1655'])
        mock = self.batch.cards.get(student_no='6333').data['mock']
        self.assertEqual((mock['this'][0]['date'], mock['this'][0]['rw']), ('05-08', '570'))
        self.assertEqual((mock['last'][0]['date'], mock['last'][0]['rw']), ('03-10', '520'))

    def test_changing_exams_keeps_comments_and_resets_locked_scores(self):
        # 11/20 자동 칸 잠금: DSG 점수 칸은 손으로 고친 값이 있어도 새 시험 값으로, 코멘트는 그대로.
        card = self.batch.cards.get(student_no='6333')
        card.data['mock']['this'][0]['rw'] = '777'
        card.data['personal'] = '코멘트'
        card.save()
        self.client.post(self.url, {'mock_exams': ['1655']})
        card.refresh_from_db()
        self.assertEqual(card.data['mock']['this'][0]['rw'], '570')
        self.assertEqual(card.data['personal'], '코멘트')

    def test_card_page_links_to_exam_picker(self):
        card = self.batch.cards.first()
        self.assertContains(self.client.get(reverse('reports:card', args=[self.batch.pk, card.pk])), self.url)

    def test_only_sat_reports_and_own_classes(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.admin)
        self.create()
        ap = ReportBatch.objects.exclude(pk=self.batch.pk).get()
        self.assertEqual(self.client.get(reverse('reports:mocks', args=[ap.pk])).status_code, 404)
