"""11/10 요청: 학생·학부모 홈에 최근 본 시험, 평균 점수·출석률·과제 제출률 도넛, 최근 리포트카드.
바깥 DB(DSG·인트라넷)를 읽으므로 홈은 먼저 뜨고, 이 영역만 /home/insights/ 에서 뒤이어 채웁니다.
강사 홈은 피드백 대기·진행 중인 리포트카드·반 현황처럼 할 일을 먼저 보여 줍니다."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.learning.models import LearningGroup
from apps.reports.models import ReportBatch, ReportCard


@override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', CLASS_CATALOG_DATA_SOURCE='demo',
                   ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class LearnerInsightTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        U = get_user_model()
        self.student = U.objects.create_user('hi_student', password='x', role='STUDENT', display_name='김지훈')
        self.parent = U.objects.create_user('hi_parent', password='x', role='PARENT', display_name='김지훈 학부모')
        StudentAccountLink.objects.create(user=self.student, student_no='6333', relationship='SELF', is_active=True)
        StudentAccountLink.objects.create(user=self.parent, student_no='6333', relationship='PARENT', is_active=True)
        self.teacher = U.objects.create_user('hi_teacher', password='x', role='TEACHER', display_name='김지연 강사')
        self.group = LearningGroup.objects.create(title='SAT 정규반', created_by=self.teacher)
        past = timezone.now() - timedelta(days=3)
        for i, done in enumerate([True, True, False]):
            a = Assignment.objects.create(title=f'HW {i}', description='-', group=self.group, created_by=self.teacher,
                                          due_at=past + timedelta(hours=i), points=10, is_published=True)
            r = AssignmentRecipient.objects.create(assignment=a, student_id='6333', student_name='김지훈')
            if done:
                Submission.objects.create(recipient=r, text_answer='답', submitted_at=past - timedelta(hours=1), score=Decimal('9'))
        batch = ReportBatch.objects.create(group=self.group, form='SAT', title='26FW', period_start=past.date(), period_end=past.date(),
                                           week_base=past.date(), created_by=self.teacher, shared={}, published_at=timezone.now())
        self.card = ReportCard.objects.create(batch=batch, student_no='6333', student_name='김지훈', data={}, auto={})

    def test_student_home_shell_loads_insights_later(self):
        self.client.force_login(self.student)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('data-home-insights', html)
        self.assertIn(reverse('home-insights'), html)

    def test_parent_home_uses_the_same_learner_home(self):
        self.client.force_login(self.parent)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('data-home-insights', html)
        self.assertNotIn('premium-kpi-icon', html)  # 예전 01~04 고정 문구 카드는 없앰
        self.assertIn(reverse('billing:my-history'), html)

    def test_insights_show_exam_donuts_and_report_card(self):
        for user in (self.student, self.parent):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse('home-insights'))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertIn('data-donut', html)
                self.assertIn('최근 본 시험', html)
                self.assertIn('1330', html)  # 데모 DSG 최근 전체 SAT
                self.assertIn('과제 제출률', html)
                self.assertIn('data-value="67"', html)  # 마감 지난 과제 3개 중 2개 제출
                self.assertIn('출석률', html)
                self.assertIn(reverse('reports:my-card', args=[self.card.pk]), html)

    def test_staff_get_no_insights(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('home-insights')).status_code, 404)


@override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class TeacherHomeTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.teacher = U.objects.create_user('th_teacher', password='x', role='TEACHER', display_name='김지연 강사')
        self.group = LearningGroup.objects.create(title='SAT 정규반', created_by=self.teacher)
        a = Assignment.objects.create(title='Essay', description='-', group=self.group, created_by=self.teacher,
                                      due_at=timezone.now() - timedelta(days=1), points=10, is_published=True)
        r = AssignmentRecipient.objects.create(assignment=a, student_id='6333', student_name='김지훈')
        Submission.objects.create(recipient=r, text_answer='답', submitted_at=timezone.now() - timedelta(days=2))
        ReportBatch.objects.create(group=self.group, form='AP', title='26FW', period_start=timezone.localdate(), period_end=timezone.localdate(),
                                   week_base=timezone.localdate(), created_by=self.teacher, shared={})

    def test_teacher_home_shows_todo_by_class(self):
        self.client.force_login(self.teacher)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('data-teacher-todo', html)
        self.assertIn('피드백 대기', html)
        self.assertIn('SAT 정규반', html)
        self.assertIn('작성 중인 리포트카드', html)
