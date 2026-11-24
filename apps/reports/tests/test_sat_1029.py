"""SAT 리포트카드(운영팀 요청 10.29): 정규·특강, DSG 모의고사 고르기, 과제·Skill Mastery 자동(이월·환불·수업미지정일), 강사·TA 권한."""
from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase
from django.urls import reverse

from apps.reports import sources
from apps.reports.models import ReportBatch
from apps.reports.sources import Task
from apps.reports.tests.test_views import ReportFixture
from apps.students.attendance_repositories import DemoAttendanceRepository, _attendance_label
from apps.students.contracts import AttendanceRecord

MONDAY = date(2026, 11, 2)


def rec(day, kind, label=''):
    return AttendanceRecord(lesson_date=day, status_kind=kind, attendance_label=label)


class AttendanceCodeTests(SimpleTestCase):
    def test_carry_over_and_refund_codes_are_named(self):
        # 인트라넷 code 표 attend_status: CO 이월, RF 환불 (전에는 '미처리'로 보였음)
        self.assertEqual(_attendance_label(attendance_code='CO', lesson_date=MONDAY, is_student_cancelled=False, is_class_cancelled=False), ('carried', '이월'))
        self.assertEqual(_attendance_label(attendance_code='RF', lesson_date=MONDAY, is_student_cancelled=False, is_class_cancelled=False), ('refunded', '환불'))


class DayRowTests(SimpleTestCase):
    def test_skill_mastery_follows_attendance(self):
        records = [rec(MONDAY, 'present'), rec(MONDAY + timedelta(1), 'absent'), rec(MONDAY + timedelta(2), 'carried'),
                   rec(MONDAY + timedelta(3), 'refunded')]
        self.assertEqual(sources.day_attendance(records, MONDAY), ['PASS', 'FAIL', '이월', '환불', '수업미지정일'])

    def test_late_and_recording_still_count_and_future_lessons_stay_blank(self):
        records = [rec(MONDAY, 'late'), rec(MONDAY + timedelta(1), 'recorded'), rec(MONDAY + timedelta(2), 'upcoming'),
                   rec(MONDAY + timedelta(3), 'holiday'), rec(MONDAY + timedelta(4), 'cancelled')]
        self.assertEqual(sources.day_attendance(records, MONDAY), ['PASS', '녹화', '', '학원휴강', '개별취소'])

    def test_task_marks_show_carry_over_refund_and_no_lesson_days(self):
        hw = [Task('HW', '월 숙제', MONDAY, True, None, Decimal('1')), Task('HW', '화 숙제', MONDAY + timedelta(1), False, None, Decimal('1')),
              Task('HW', '수 숙제', MONDAY + timedelta(2), True, None, Decimal('1'))]
        skill = ['PASS', 'FAIL', '이월', '환불', '수업미지정일']
        self.assertEqual(sources.day_marks(hw, MONDAY, attendance=skill), ['PASS', 'FAIL', '이월', '환불', '수업미지정일'])
        self.assertEqual(sources.day_marks(hw, MONDAY), ['PASS', 'FAIL', 'PASS', '', ''])


class SatFormTests(ReportFixture):
    def sat(self, **extra):
        return self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20', **extra)

    def test_special_course_takes_two_chosen_mock_exams(self):
        self.sat(course_type='특강', mock_exams=['1655', '1658'])
        batch = ReportBatch.objects.get()
        self.assertEqual(batch.shared['course_type'], '특강')
        this = batch.cards.get(student_no='6333').data['mock']['this']
        self.assertEqual([(s['date'], s['rw']) for s in this], [('05-08', '570'), ('07-20', '640'), ('', '')])

    def test_regular_course_allows_only_one_mock_exam(self):
        response = self.sat(course_type='정규', mock_exams=['1655', '1658'])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '정규 수업은 모의고사를 1개')
        self.assertFalse(ReportBatch.objects.exists())

    def test_new_page_lists_dsg_mock_exams_of_the_class(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse('reports:new'), {'group': self.group.pk})
        self.assertContains(page, '25WT2-TEST06')
        self.assertContains(page, 'name="course_type"')

    def test_without_chosen_exams_the_week_window_is_used(self):
        self.sat()
        this = ReportBatch.objects.get().cards.get(student_no='6333').data['mock']['this']
        self.assertEqual(this[0]['date'], '07-20')

    def test_with_a_course_skill_mastery_and_tasks_come_from_attendance(self):
        records = DemoAttendanceRepository().list_by_student_and_assign('6333', '10001')
        day = min(r.lesson_date for r in records if r.lesson_date)
        monday = day - timedelta(days=day.weekday())
        self.create(form='SAT', course='201', period_start=monday.isoformat(), period_end=(monday + timedelta(4)).isoformat(),
                    week_base=monday.isoformat())
        card = ReportBatch.objects.get().cards.get(student_no='6333')
        self.assertEqual(card.data['skill'], sources.day_attendance(records, monday))


class SatPermissionTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20')
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])
        self.post = {'d.personal': 'TA 코멘트', 'd.attitude.0.a': '5', 's.notice': '바뀐 공지', 'save': '1'}

    def saved(self):
        self.card.refresh_from_db(); self.batch.refresh_from_db()
        return self.card.data['personal'], self.card.data['attitude'][0]['a'], self.batch.shared['notice']

    def test_ta_writes_every_field(self):
        # 11/19 TA 권한 결정: 리포트카드 제작·작성(발송 불가). 강사·TA 모두 카드의 모든 칸과 반 공통 글을 씁니다.
        self.client.force_login(self.ta)
        page = self.client.get(self.url).content.decode()
        self.assertIn('name="d.personal"', page)
        self.assertIn('name="d.attitude.0.a"', page)
        self.client.post(self.url, self.post)
        self.assertEqual(self.saved(), ('TA 코멘트', '5', '바뀐 공지'))

    def test_teacher_writes_every_field(self):
        self.client.force_login(self.teacher)
        page = self.client.get(self.url).content.decode()
        self.assertIn('name="d.attitude.0.a"', page)
        self.client.post(self.url, self.post)
        self.assertEqual(self.saved(), ('TA 코멘트', '5', '바뀐 공지'))

    def test_admin_writes_everything(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post)
        self.assertEqual(self.saved(), ('TA 코멘트', '5', '바뀐 공지'))

    def test_other_forms_are_not_restricted(self):
        self.create(form='AP')
        ap = ReportBatch.objects.get(form='AP')
        card = ap.cards.get(student_no='6333')
        self.client.force_login(self.ta)
        self.client.post(reverse('reports:card', args=[ap.pk, card.pk]), {'d.comment': 'TA가 쓴 AP 코멘트', 'save': '1'})
        card.refresh_from_db()
        self.assertEqual(card.data['comment'], 'TA가 쓴 AP 코멘트')
