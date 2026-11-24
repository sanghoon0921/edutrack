"""11/19 저장·제출 뒤 처음 목록으로: 화면에 멈춰 있지 않고 그 기능의 첫 목록으로 돌아갑니다.

리포트카드 '저장' → 리포트카드 목록('저장 후 다음 학생'은 다음 학생), 과제 등록·수정 → 과제 목록, 토론 등록·수정 → 토론 목록,
퀴즈 수정 → 퀴즈 목록(새 퀴즈는 문항을 넣어야 해서 퀴즈 화면), 학생 과제 제출 → 내 과제, 첨삭 '의견 제출' → 그 과제의 제출 현황.
"""
from django.urls import reverse

from apps.assignments.models import Assignment
from apps.learning.models import Discussion
from apps.learning.tests.test_quiz_builder import QuizBuilderTests, question
from apps.lms.tests.test_lms import LmsFixture
from apps.lms.tests.test_usability import PublicationAndDateTests
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class AssignmentReturnTests(PublicationAndDateTests):
    def test_create_returns_to_assignment_list(self):
        self.login(self.teacher)
        response = self.client.post(reverse('assignments:create'), self.payload())
        self.assertRedirects(response, reverse('assignments:list'), fetch_redirect_response=False)
        self.assertTrue(Assignment.objects.filter(title='신규 과제').exists())

    def test_update_returns_to_assignment_list(self):
        self.login(self.teacher)
        response = self.client.post(reverse('assignments:update', args=[self.assignment.pk]), self.payload(title='고친 과제'))
        self.assertRedirects(response, reverse('assignments:list'), fetch_redirect_response=False)


class SubmissionReturnTests(LmsFixture):
    def test_student_submit_returns_to_my_assignments(self):
        self.login(self.student)
        response = self.client.post(reverse('assignments:my-detail', args=[self.recipient.pk]), {'text_answer': 'new answer'})
        self.assertRedirects(response, reverse('assignments:my'), fetch_redirect_response=False)

    def test_feedback_submit_returns_to_assignment_status(self):
        response = self.post_grade()
        self.assertRedirects(response, reverse('assignments:detail', args=[self.assignment.pk]), fetch_redirect_response=False)


class DiscussionReturnTests(LmsFixture):
    def payload(self, **more):
        from datetime import timedelta
        from django.utils import timezone
        due = (timezone.localtime() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        data = {'title': '새 토론', 'group': self.group.pk, 'content': '의견을 쓰세요', 'student_ids': '6333', 'due_at': due}
        data.update(more)
        return data

    def test_create_returns_to_discussion_list(self):
        self.login(self.teacher)
        response = self.client.post(reverse('learning:discussion-create'), self.payload())
        self.assertRedirects(response, reverse('learning:discussion-list'), fetch_redirect_response=False)
        self.assertTrue(Discussion.objects.filter(title='새 토론').exists())


class QuizReturnTests(QuizBuilderTests):
    def test_quiz_update_returns_to_quiz_list(self):
        response = self.post_quiz([question('SHORT', '첫 문항', correct_text='a')])
        quiz_url = response['Location']
        quiz_pk = int(quiz_url.rstrip('/').split('/')[-1])
        response = self.post_quiz(None, url=reverse('learning:quiz-update', args=[quiz_pk]), title='이름만 변경')
        self.assertRedirects(response, reverse('learning:quiz-list'), fetch_redirect_response=False)


class ReportCardReturnTests(ReportFixture):
    def test_plain_save_returns_to_report_list(self):
        self.create()
        batch = ReportBatch.objects.get()
        first = batch.cards.order_by('pk').first()
        self.client.force_login(self.admin)
        response = self.client.post(reverse('reports:card', args=[batch.pk, first.pk]), {'d.comment': '좋아요', 'save': '1'})
        self.assertRedirects(response, reverse('reports:list'), fetch_redirect_response=False)

    def test_save_and_next_still_goes_to_next_student(self):
        self.create()
        batch = ReportBatch.objects.get()
        cards = list(batch.cards.order_by('pk'))
        self.client.force_login(self.admin)
        response = self.client.post(reverse('reports:card', args=[batch.pk, cards[0].pk]), {'d.comment': '좋아요', 'next': '1'})
        self.assertRedirects(response, reverse('reports:card', args=[batch.pk, cards[1].pk]), fetch_redirect_response=False)
