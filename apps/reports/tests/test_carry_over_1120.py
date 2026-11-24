"""리포트카드 Skill Mastery 의 '이월'(11/20 실제 자료 점검).

인트라넷에서 이월 처리된 수업(이월 표시, 출결 CO)은 출결 화면 계산에서는 빼지만,
리포트카드는 운영팀 규칙(10/29: 이월인 날은 '이월')대로 보여야 합니다. 전에는 같은 쿼리를 써서 '수업미지정일'로 나왔습니다.
"""
from datetime import date
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.reports import sources
from apps.students.attendance_repositories import DemoAttendanceRepository, IntranetAttendanceRepository
from apps.students.contracts import AttendanceRecord


class RepositoryOptionTests(SimpleTestCase):
    def test_demo_repository_hides_carry_over_unless_asked(self):
        repo = DemoAttendanceRepository()
        plain = {r.lesson_id for r in repo.list_by_student_and_assign('6333', '10001')}
        withco = {r.lesson_id for r in repo.list_by_student_and_assign('6333', '10001', include_carry_over=True)}
        self.assertNotIn('50006', plain)
        self.assertIn('50006', withco)


@override_settings(STUDENT_DATA_SOURCE='demo')
class ReportReadsCarryOverTests(SimpleTestCase):
    def test_course_lessons_asks_for_carry_over_rows(self):
        repo = mock.MagicMock()
        repo.list_by_student_and_assign.return_value = []
        course = mock.Mock(class_id='841', assign_id='13140')
        with mock.patch.object(sources, 'student_courses', return_value=[course]), \
                mock.patch('apps.students.attendance_repositories.get_attendance_repository', return_value=repo):
            sources.course_lessons('3258', '841')
        repo.list_by_student_and_assign.assert_called_once_with('3258', '13140', include_carry_over=True)

    def test_carried_days_show_as_carry_over_and_are_not_lesson_dates(self):
        carried = AttendanceRecord(lesson_date=date(2026, 11, 19), status_kind='carried', attendance_label='이월')
        present = AttendanceRecord(lesson_date=date(2026, 11, 18), status_kind='present', attendance_label='출석')
        spans = sources.daily_spans(date(2026, 11, 16))
        self.assertEqual(sources.span_attendance([present, carried], spans), ['수업미지정일', '수업미지정일', 'PASS', '이월', '수업미지정일'])
        self.assertEqual(sources.lesson_dates([present, carried]), [date(2026, 11, 18)])


class PaymentCarryOverTests(SimpleTestCase):
    def test_carry_over_payment_counts_even_without_attendance_code(self):
        upcoming = AttendanceRecord(lesson_date=date(2026, 11, 20), status_kind='upcoming', payment_code='CARRY_OVER')
        spans = sources.daily_spans(date(2026, 11, 16))
        self.assertEqual(sources.span_attendance([upcoming], spans)[4], '이월')
        self.assertEqual(sources.lesson_dates([upcoming]), [])
