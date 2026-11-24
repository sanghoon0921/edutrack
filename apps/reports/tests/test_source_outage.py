"""인트라넷·DSG가 끊겼을 때(예: DB 연결이 응답 없이 15초씩 걸려 실패).

- 데이터 다시 불러오기: 카드 값을 빈칸으로 덮어쓰지 않고 그대로 둔 채 멈추고, 이유를 알려 줍니다.
- 만들기: 빈 카드를 만들지 않고 이유를 알려 줍니다.
- 첫 실패 뒤에는 학생마다 다시 기다리지 않습니다(한 번 15초면 끝).
"""
from unittest import mock

from django.db.utils import OperationalError
from django.urls import reverse

from apps.reports.models import ReportBatch

from .test_views import ReportFixture

LOST = OperationalError(2013, 'Lost connection to MySQL server during query (timed out)')
GET_STUDENTS = 'apps.students.services.StudentService.get_students'
GET_COURSES = 'apps.students.course_services.CourseService.get_student_courses'
GET_REPO = 'apps.assessments.repositories.get_assessment_repository'


class RefreshDuringOutageTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get()
        self.kim = self.batch.cards.get(student_no='6333')

    def refresh(self):
        return self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.kim.pk}, follow=True)

    def test_refresh_keeps_card_values_and_explains(self):
        before = dict(self.kim.data)
        with mock.patch(GET_STUDENTS, side_effect=LOST):
            response = self.refresh()
        self.kim.refresh_from_db()
        self.assertEqual(self.kim.data, before)
        self.assertEqual(self.kim.data['info']['region'], '태국 방콕 Ekamai International School')
        self.assertContains(response, '인트라넷')
        self.assertContains(response, '그대로')
        self.assertNotContains(response, '다시 불러왔습니다')

    def test_refresh_stops_reading_after_first_failure(self):
        self.batch.course_class_id = 'C-1'
        self.batch.save()
        with mock.patch(GET_STUDENTS, side_effect=LOST), mock.patch(GET_COURSES) as courses:
            self.refresh()
        courses.assert_not_called()

    def test_failure_partway_keeps_values(self):
        """학생 정보는 (캐시 등으로) 읽혔는데 수업·출결에서 끊겨도 카드는 그대로입니다."""
        self.batch.course_class_id = 'C-1'
        self.batch.save()
        before = dict(self.kim.data)
        with mock.patch(GET_COURSES, side_effect=LOST) as courses:
            response = self.refresh()
        self.kim.refresh_from_db()
        self.assertEqual(self.kim.data, before)
        self.assertEqual(courses.call_count, 1)
        self.assertContains(response, '그대로')


class CreateDuringOutageTests(ReportFixture):
    def test_create_makes_nothing_and_explains(self):
        with mock.patch(GET_STUDENTS, side_effect=LOST):
            response = self.create()
        self.assertFalse(ReportBatch.objects.exists())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '인트라넷')
        self.assertContains(response, '만들지 않았습니다')

    def test_new_form_tries_the_intranet_once_and_says_so(self):
        self.client.force_login(self.admin)
        with mock.patch(GET_COURSES, side_effect=LOST) as courses, mock.patch(GET_REPO) as repo:
            response = self.client.get(reverse('reports:new'), {'group': self.group.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(courses.call_count, 1)  # 반 학생 2명이어도 첫 실패에서 멈춤
        repo.assert_not_called()  # DSG 학생 찾기도 인트라넷을 거치므로 다시 기다리지 않음
        self.assertContains(response, '인트라넷')
        self.assertContains(response, '목록을 불러오지 못했습니다')
