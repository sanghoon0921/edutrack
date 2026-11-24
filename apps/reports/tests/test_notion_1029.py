"""운영팀 요청 10.29: 꼬리표 글자, 제출여부 선택, 코멘트 링크, 제목(시즌) 수정, 로고, 수업일자, 주니어 주 추가·삭제."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture
from apps.students.attendance_repositories import DemoAttendanceRepository

CSS = Path(settings.BASE_DIR) / 'apps/reports/static/reports/css/report-card.css'


def select_html(html, name):
    found = re.search(r'<select name="%s".*?</select>' % re.escape(name), html, re.S)
    return found.group(0) if found else ''


class LabelColourTests(SimpleTestCase):
    def test_tabs_and_dark_headings_beat_the_intranet_heading_colour(self):
        # 인트라넷 테마 body.intranet-app-body h3 (0,1,2) 가 .rc-tab (0,1,0) 을 이겨 파란 칸에 남색 글자가 됐습니다.
        css = CSS.read_text(encoding='utf-8')
        self.assertRegex(css, r'\.rc-sheet \.rc-tab\s*\{[^}]*color:\s*#fff')
        self.assertRegex(css, r'\.rc-sheet \.rc-junior-head h2\s*\{[^}]*color:\s*#fff')


class StatusSelectTests(ReportFixture):
    def page(self, batch, student_no='6333'):
        card = batch.cards.get(student_no=student_no)
        return self.client.get(reverse('reports:card', args=[batch.pk, card.pk])).content.decode()

    def test_term_submit_cells_are_dropdowns_with_the_six_choices(self):
        self.create()
        html = self.page(ReportBatch.objects.get())
        week4 = select_html(html, 'd.weeks.3.status')
        for option in ['제출완료', '미제출', '일부제출', '수업미지정일', '환불', '이월']:
            self.assertIn(f'<option value="{option}"', week4)
        self.assertIn('<option value="제출완료" selected>', week4)

    def test_value_outside_the_list_is_kept(self):
        self.create()
        batch = ReportBatch.objects.get()
        card = batch.cards.get(student_no='6333')
        card.data['weeks'][0]['status'] = '보강 예정'
        card.save()
        self.assertIn('<option value="보강 예정" selected>', select_html(self.page(batch), 'd.weeks.0.status'))

    def test_junior_submitted_column_is_a_dropdown(self):
        self.create(form='JUNIOR')
        self.assertIn('<option value="수업미지정일"', select_html(self.page(ReportBatch.objects.get()), 'd.rows.0.submitted'))


class LinkAndTitleTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])

    def test_urls_in_comments_become_links_when_viewed(self):
        self.card.data['comment'] = '자료는 https://drive.google.com/file/d/abc?usp=sharing 에 있습니다 <b>굵게</b>'
        self.card.save()
        html = self.client.get(reverse('reports:card-print', args=[self.batch.pk, self.card.pk])).content.decode()
        self.assertIn('<a href="https://drive.google.com/file/d/abc?usp=sharing"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('&lt;b&gt;굵게&lt;/b&gt;', html)

    def test_title_can_be_changed_on_the_card_page(self):
        self.assertContains(self.client.get(self.url), 'name="batch_title"')
        self.client.post(self.url, {'batch_title': '2627WT', 'save': '1'})
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.title, '2627WT')
        self.client.post(self.url, {'batch_title': '   ', 'save': '1'})
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.title, '2627WT')

    def test_brand_uses_the_real_logo(self):
        self.assertContains(self.client.get(self.url), 'reports/img/logo-brown.png')


class LessonDateTests(ReportFixture):
    def test_term_weeks_follow_course_lesson_dates_when_a_course_is_chosen(self):
        lessons = sorted({r.lesson_date for r in DemoAttendanceRepository().list_by_student_and_assign('6333', '10001')
                          if r.lesson_date and not r.is_class_cancelled})
        first, last = lessons[0], lessons[-1]
        self.create(course='201', week_base=first.isoformat(), period_start=first.isoformat(), period_end=last.isoformat())
        weeks = ReportBatch.objects.get().cards.get(student_no='6333').data['weeks']
        self.assertEqual([w['label'] for w in weeks], [f'{d.month}/{d.day}' for d in lessons])

    def test_without_a_course_term_weeks_stay_week_numbers(self):
        self.create()
        weeks = ReportBatch.objects.get().cards.get(student_no='6333').data['weeks']
        self.assertEqual(weeks[0]['label'], 'WEEK1')
        self.assertEqual(len(weeks), 16)


class JuniorRowTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create(form='JUNIOR', period_start='2026-09-13', period_end='2026-09-19', week_base='2026-09-13')
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')

    def labels(self):
        return {c.student_no: [r['label'] for r in c.data['rows']] for c in self.batch.cards.all()}

    def test_week_rows_are_added_and_removed_for_the_whole_class(self):
        self.assertEqual(self.labels(), {'6333': ['WEEK1'], '7102': ['WEEK1']})
        response = self.client.post(reverse('reports:row-add', args=[self.batch.pk]), {'card': self.card.pk, 'd.rows.0.homework': '단어 50개'})
        self.assertRedirects(response, reverse('reports:card', args=[self.batch.pk, self.card.pk]), fetch_redirect_response=False)
        self.batch.refresh_from_db()
        self.assertEqual(self.labels(), {'6333': ['WEEK1', 'WEEK2'], '7102': ['WEEK1', 'WEEK2']})
        self.assertIn('WEEK2', self.batch.shared['contents'])
        self.assertEqual(self.batch.cards.get(student_no='6333').data['rows'][0]['homework'], '단어 50개')

        self.client.post(reverse('reports:row-delete', args=[self.batch.pk, 'WEEK2']), {'card': self.card.pk})
        self.batch.refresh_from_db()
        self.assertEqual(self.labels(), {'6333': ['WEEK1'], '7102': ['WEEK1']})
        self.assertNotIn('WEEK2', self.batch.shared['contents'])

    def test_new_member_gets_the_added_rows(self):
        from apps.lms.models import GroupMember
        self.client.post(reverse('reports:row-add', args=[self.batch.pk]), {'card': self.card.pk})
        GroupMember.objects.create(group=self.group, student_no='8201', student_name='박민준')
        self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk})
        self.assertEqual([r['label'] for r in self.batch.cards.get(student_no='8201').data['rows']], ['WEEK1', 'WEEK2'])

    def test_unknown_row_and_other_forms_are_404(self):
        self.assertEqual(self.client.post(reverse('reports:row-delete', args=[self.batch.pk, 'WEEK9'])).status_code, 404)
        self.create(form='AP')
        ap = ReportBatch.objects.get(form='AP')
        self.assertEqual(self.client.post(reverse('reports:row-add', args=[ap.pk])).status_code, 404)
