"""seed_showcase: 가짜(데모) 자료 DB에 기능 체험용 반·과제·첨삭·퀴즈·토론·공지·메신저·리포트카드를 한 번에 넣습니다."""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.accounts.models import StudentAccountLink
from apps.assignments.models import Assignment, Submission
from apps.communications.models import Notice
from apps.learning.models import Discussion, LearningGroup, Quiz, QuizAttempt
from apps.lms.models import ClassPost, Conversation, ReviewDocument
from apps.reports.models import ReportBatch


class SeedShowcaseTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix='showcase-test-')
        self.addCleanup(lambda: shutil.rmtree(self.media, ignore_errors=True))
        U = get_user_model()
        for name, role in [('admin_test', 'ADMIN'), ('teacher_test', 'TEACHER'), ('student_test', 'STUDENT'), ('parent_test', 'PARENT')]:
            U.objects.create_user(name, password='x-Seed!2026', role=role)
        StudentAccountLink.objects.create(user=U.objects.get(username='student_test'), student_no='6333', relationship='SELF', is_active=True)
        StudentAccountLink.objects.create(user=U.objects.get(username='parent_test'), student_no='6333', relationship='PARENT', is_active=True)

    def run_seed(self, *args):
        with override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', MEDIA_ROOT=self.media):
            call_command('seed_showcase', *args, verbosity=0)

    def test_refuses_a_database_with_real_students(self):
        with override_settings(STUDENT_DATA_SOURCE='intranet'):
            with self.assertRaises(CommandError):
                call_command('seed_showcase', verbosity=0)
        self.assertFalse(LearningGroup.objects.exists())

    def test_fills_every_feature(self):
        self.run_seed()
        group = LearningGroup.objects.get(title__startswith='[체험]')
        self.assertEqual(sorted(group.lms_members.values_list('student_no', flat=True)), ['6333', '7102', '8201'])
        self.assertEqual(group.term, '26FW')  # 반 목록 Term 필터를 체험할 수 있게(운영팀 요청 10.29)
        self.assertEqual(Assignment.objects.filter(title__startswith='[체험]').count(), 3)
        self.assertGreaterEqual(Submission.objects.filter(recipient__assignment__group=group, submitted_at__isnull=False).count(), 5)
        doc = ReviewDocument.objects.get(submission__recipient__assignment__group=group, submission__recipient__student_id='7102')
        self.assertTrue(any(mark.get('text') for mark in doc.annotations))
        quiz = Quiz.objects.get(title__startswith='[체험] Canvas')
        self.assertEqual(sorted(set(quiz.questions.values_list('question_type', flat=True))),
                         sorted(['MCQ', 'MULTI', 'TF', 'ORDER', 'MATCH', 'FILL', 'CATEGORY']))
        attempt = QuizAttempt.objects.get(recipient__quiz=quiz, recipient__student_id='6333')
        self.assertGreater(attempt.score, 0)
        self.assertEqual(attempt.answers.count(), 7)
        self.assertGreaterEqual(Discussion.objects.get(group=group).comments.count(), 3)
        self.assertEqual(sorted(ClassPost.objects.filter(group=group).values_list('kind', flat=True)), ['FILE', 'NOTICE', 'PAGE'])
        self.assertEqual(Notice.objects.filter(title__startswith='[체험]').count(), 2)
        kinds = set(Conversation.objects.filter(messages__isnull=False).values_list('kind', flat=True))
        self.assertTrue({'CLASS', 'GROUP', 'DIRECT'} <= kinds)
        forms = sorted(ReportBatch.objects.filter(group=group).values_list('form', flat=True))
        self.assertEqual(forms, ['AP', 'GPA_ESSAY', 'JUNIOR', 'SAT', 'TOEFL'])
        for batch in ReportBatch.objects.filter(group=group):
            self.assertEqual(batch.cards.count(), 3)
        sat = ReportBatch.objects.get(group=group, form='SAT').cards.get(student_no='6333')
        self.assertTrue(sat.data['personal'])
        self.assertTrue(sat.data['mock']['this'][0]['rw'])

    def test_second_run_does_not_duplicate_and_reset_rebuilds(self):
        self.run_seed()
        self.run_seed()
        self.assertEqual(LearningGroup.objects.filter(title__startswith='[체험]').count(), 1)
        self.assertEqual(Assignment.objects.filter(title__startswith='[체험]').count(), 3)
        self.run_seed('--reset')
        self.assertEqual(LearningGroup.objects.filter(title__startswith='[체험]').count(), 1)
        self.assertEqual(Assignment.objects.filter(title__startswith='[체험]').count(), 3)
        self.assertEqual(Notice.objects.filter(title__startswith='[체험]').count(), 2)

    def test_review_screen_finds_the_seeded_marks(self):
        """첨삭 화면은 DB에서 다시 읽은 제출로 문서를 찾습니다. 체험 첨삭 표시가 그 문서에 있어야 화면에 보입니다."""
        from apps.lms.documents import version_token
        self.run_seed()
        sub = Submission.objects.get(recipient__assignment__title__startswith='[체험] Essay', recipient__student_id='7102')
        doc = sub.review_documents.get(source_token=version_token(sub))
        self.assertEqual(sum(1 for mark in doc.annotations if mark.get('text')), 4)
