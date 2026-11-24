"""학부모 출결: '녹화' 회차를 누르면 녹화본 발송 일시(인트라넷의 녹화본 발송 완료 기록)를 보여 줍니다(운영팀 요청 10.29)."""
from dataclasses import replace
from datetime import date, datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink
from apps.students import attendance_repositories as repos
from apps.students.contracts import AttendanceRecord


class RowMappingTests(TestCase):
    def test_sent_time_is_read_from_the_row(self):
        sent = datetime(2026, 11, 3, 14, 20)
        record = repos._row_to_attendance_record({'assign_id': '1', 'lesson_id': '2', 'lesson_date': date(2026, 11, 3),
                                                  'attendance_code': 'RC', 'recording_sent_at': sent})
        # 인트라넷의 발송 시각은 한국 시간입니다.
        from zoneinfo import ZoneInfo
        self.assertEqual((record.status_kind, record.recording_sent_at), ('recorded', timezone.make_aware(sent, ZoneInfo('Asia/Seoul'))))


@override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', CLASS_CATALOG_DATA_SOURCE='demo')
class ParentPageTests(TestCase):
    def setUp(self):
        cache.clear()  # 출결은 60초 캐시됩니다. 다른 테스트가 넣어 둔 값이 패치를 가리지 않게.
        self.parent = get_user_model().objects.create_user('rec_parent', password='x', role='PARENT')
        StudentAccountLink.objects.create(user=self.parent, student_no='6333', relationship='PARENT', is_active=True)
        self.client.force_login(self.parent)
        self.url = reverse('students:attendance', kwargs={'student_id': '6333', 'assign_id': '10001'})
        real = repos.DemoAttendanceRepository.list_by_student_and_assign
        past = timezone.localdate() - timedelta(days=9)
        self.sent = timezone.make_aware(datetime.combine(past + timedelta(days=1), datetime.min.time()).replace(hour=14, minute=20))

        def with_recordings(repo, student_id, assign_id):
            records = list(real(repo, student_id, assign_id))
            extra = [AttendanceRecord(assign_id=assign_id, lesson_id='9001', lesson_date=past, attendance_code='RC',
                                      attendance_label='녹화', status_kind='recorded', recording_sent_at=self.sent),
                     AttendanceRecord(assign_id=assign_id, lesson_id='9002', lesson_date=past - timedelta(days=7), attendance_code='RC',
                                      attendance_label='녹화', status_kind='recorded')]
            return records + extra

        patcher = mock.patch.object(repos.DemoAttendanceRepository, 'list_by_student_and_assign', with_recordings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_recorded_card_opens_the_list_of_recording_send_times(self):
        html = self.client.get(self.url).content.decode()
        card = html.split('data-recorded-sends', 1)[1].split('</details>', 1)[0]
        local = timezone.localtime(self.sent)
        self.assertIn(local.strftime('%Y.%m.%d %H:%M'), card)
        self.assertIn('발송 전', card)

    def test_each_recorded_lesson_shows_its_send_time(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('녹화본 발송 ' + timezone.localtime(self.sent).strftime('%m.%d %H:%M'), html)


class DemoDataTests(TestCase):
    """테스트 서버(가짜 데이터)에서도 학부모가 '녹화' 카드를 눌러 볼 수 있게, 데모 출결에 녹화 회차가 있습니다."""

    def setUp(self):
        cache.clear()

    def test_demo_course_has_a_sent_and_an_unsent_recording(self):
        records = repos.DemoAttendanceRepository().list_by_student_and_assign('6333', '10001')
        recorded = [r for r in records if r.status_kind == 'recorded']
        self.assertEqual(len(recorded), 2)
        self.assertEqual(sorted(r.recording_sent_at is not None for r in recorded), [False, True])
        sent = next(r for r in recorded if r.recording_sent_at)
        self.assertTrue(timezone.is_aware(sent.recording_sent_at))
        self.assertGreater(timezone.localdate(sent.recording_sent_at), sent.lesson_date)

    @override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', CLASS_CATALOG_DATA_SOURCE='demo')
    def test_demo_parent_sees_the_send_time_without_any_patching(self):
        parent = get_user_model().objects.create_user('rec_parent2', password='x', role='PARENT')
        StudentAccountLink.objects.create(user=parent, student_no='6333', relationship='PARENT', is_active=True)
        self.client.force_login(parent)
        html = self.client.get(reverse('students:attendance', kwargs={'student_id': '6333', 'assign_id': '10001'})).content.decode()
        card = html.split('data-recorded-sends', 1)[1].split('</details>', 1)[0]
        self.assertIn('발송 전', card)
        self.assertIn('녹화본 발송 ', html)
