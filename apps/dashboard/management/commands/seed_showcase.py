"""가짜(데모) 자료 DB에 기능 체험용 자료를 한 번에 넣습니다.

  python manage.py seed_showcase --settings=config.settings.share          넣기(이미 있으면 그대로 둠)
  python manage.py seed_showcase --settings=config.settings.share --reset  지우고 다시 넣기

- 학생 정보가 가짜(demo)인 설정에서만 돕니다. 실제 인트라넷 자료(office)에는 넣지 않습니다.
- 넣는 것: 체험용 반(김지훈·이서연·박민준), 과제 3개(제출·채점·첨삭 포함), 7가지 유형 퀴즈와 응시,
  단어 퀴즈, 토론과 댓글, 반 공지·단어장·수업 자료, 학원·반 공지, 반 단체방·그룹 대화·1:1 대화, 리포트카드 5가지 양식.
- 만든 것은 제목 앞에 [체험]을 붙여 운영팀이 만든 자료와 구별합니다.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StudentAccountLink
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.communications.models import Notice
from apps.learning import quiz_types
from apps.learning.models import Discussion, DiscussionComment, DiscussionRecipient, LearningGroup, Quiz, QuizAnswer, QuizAttempt, QuizRecipient
from apps.learning.services import sync_quiz_questions
from apps.lms import rooms
from apps.lms.documents import clean_annotations, create_preview
from apps.lms.models import ClassPost, Conversation, ConversationMember, GroupMember, GroupStaff, Message, PostFile
from apps.operations.models import TeacherStudentAccess
from apps.reports import services as report_services
from apps.reports.models import ReportBatch

MARK = '[체험]'
FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures' / 'showcase'
STUDENTS = (('6333', '김지훈'), ('7102', '이서연'), ('8201', '박민준'))
TOKEN_SPACE = uuid5(NAMESPACE_URL, 'edutrack-showcase')

CANVAS_QUESTIONS = [
    {'type': 'MCQ', 'prompt': '‘happy’와 뜻이 가장 가까운 단어는?', 'points': 2, 'config': {},
     'choices': [('glad', True), ('angry', False), ('tired', False), ('late', False)]},
    {'type': 'MULTI', 'prompt': '명사를 모두 고르세요.', 'points': 2, 'config': {},
     'choices': [('apple', True), ('run', False), ('school', True), ('quickly', False)]},
    {'type': 'TF', 'prompt': 'The sun rises in the east.', 'points': 2, 'config': {}, 'choices': [('참', True), ('거짓', False)]},
    {'type': 'ORDER', 'prompt': '문장이 되도록 순서대로 놓으세요.', 'points': 2, 'choices': [],
     'config': {'items': [{'id': 'o1', 'text': 'I'}, {'id': 'o2', 'text': 'like'}, {'id': 'o3', 'text': 'reading'}, {'id': 'o4', 'text': 'books'}]}},
    {'type': 'MATCH', 'prompt': '단어와 뜻을 연결하세요.', 'points': 3, 'choices': [],
     'config': {'pairs': [{'id': 'm1', 'left': 'brave', 'right': '용감한'}, {'id': 'm2', 'left': 'quiet', 'right': '조용한'},
                          {'id': 'm3', 'left': 'honest', 'right': '정직한'}], 'distractors': ['게으른']}},
    {'type': 'FILL', 'prompt': 'Yesterday I `went` to the `library|Library` and borrowed two `books`.', 'points': 3, 'choices': [],
     'config': {'blanks': [{'mode': 'dropdown', 'answers': ['went'], 'options': ['go', 'goes']},
                           {'mode': 'text', 'answers': ['library', 'Library'], 'options': []},
                           {'mode': 'bank', 'answers': ['books'], 'options': []}], 'bank': ['pens']}},
    {'type': 'CATEGORY', 'prompt': '단어를 품사별로 나누세요.', 'points': 4, 'choices': [],
     'config': {'categories': [{'id': 'c1', 'name': '명사'}, {'id': 'c2', 'name': '동사'}],
                'items': [{'id': 'k1', 'text': 'apple', 'category': 'c1'}, {'id': 'k2', 'text': 'teacher', 'category': 'c1'},
                          {'id': 'k3', 'text': 'swim', 'category': 'c2'}, {'id': 'k4', 'text': 'write', 'category': 'c2'},
                          {'id': 'k5', 'text': 'happily', 'category': ''}]}},
]
VOCAB_QUESTIONS = [
    {'type': 'MCQ', 'prompt': '‘abundant’의 뜻은?', 'points': 1, 'config': {}, 'choices': [('풍부한', True), ('부족한', False), ('위험한', False)]},
    {'type': 'MCQ', 'prompt': '‘reluctant’의 뜻은?', 'points': 1, 'config': {}, 'choices': [('꺼리는', True), ('열정적인', False), ('조용한', False)]},
    {'type': 'MCQ', 'prompt': '‘brief’의 뜻은?', 'points': 1, 'config': {}, 'choices': [('짧은', True), ('밝은', False), ('넓은', False)]},
]


def at(day, hour=18, minute=0):
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


class Command(BaseCommand):
    help = '가짜(데모) 자료 DB에 기능 체험용 반·과제·첨삭·퀴즈·토론·공지·메신저·리포트카드를 넣습니다.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='전에 넣은 [체험] 자료를 지우고 다시 넣습니다.')

    def handle(self, *args, reset=False, **options):
        if str(getattr(settings, 'STUDENT_DATA_SOURCE', '')).lower() != 'demo':
            raise CommandError('학생 정보가 가짜(demo)인 설정에서만 실행합니다. 실제 자료 DB(office)에는 넣지 않습니다.')
        U = get_user_model()
        missing = [name for name in ('admin_test', 'teacher_test', 'student_test', 'parent_test') if not U.objects.filter(username=name).exists()]
        if missing:
            raise CommandError(f'데모 계정이 없습니다: {", ".join(missing)}')
        with transaction.atomic():
            if reset:
                self.clear()
            elif LearningGroup.objects.filter(title__startswith=MARK).exists():
                self.stdout.write('이미 체험 자료가 있습니다. 다시 넣으려면 --reset')
                return
            self.seed(U)
        self.stdout.write(self.style.SUCCESS('체험 자료를 넣었습니다: [체험] SAT 정규반'))

    # ── 지우기 ──────────────────────────────────────────────────────────
    def clear(self):
        Assignment.objects.filter(title__startswith=MARK).delete()
        Quiz.objects.filter(title__startswith=MARK).delete()
        Discussion.objects.filter(title__startswith=MARK).delete()
        Notice.objects.filter(title__startswith=MARK).delete()
        Conversation.objects.filter(kind=Conversation.Kind.GROUP, title__startswith=MARK).delete()
        Message.objects.filter(client_token__in=[self.token(i) for i in range(200)]).delete()
        groups = LearningGroup.objects.filter(title__startswith=MARK)
        # 반 명단을 먼저 비우고(단체방 참여자 맞추기 신호가 여기서 끝남) 단체방을 지운 뒤 반을 지웁니다.
        GroupMember.objects.filter(group__in=groups).delete()
        GroupStaff.objects.filter(group__in=groups).delete()
        Conversation.objects.filter(group__in=groups).delete()
        groups.delete()

    @staticmethod
    def token(i):
        return uuid5(TOKEN_SPACE, f'message-{i}')

    # ── 넣기 ────────────────────────────────────────────────────────────
    def seed(self, U):
        self.now, today = timezone.now(), timezone.localdate()
        self.last_monday = today - timedelta(days=today.weekday() + 7)
        self.admin, self.teacher = U.objects.get(username='admin_test'), U.objects.get(username='teacher_test')
        self.student, self.parent = U.objects.get(username='student_test'), U.objects.get(username='parent_test')
        self.learners = {'6333': self.learner(U, '6333', '김지훈', self.student),
                         '7102': self.learner(U, '7102', '이서연'), '8201': self.learner(U, '8201', '박민준')}
        self.ta = self.extra_user(U, 'demo_ta', '데모 TA', 'TEACHER')
        for no, name in STUDENTS:
            TeacherStudentAccess.objects.get_or_create(teacher=self.teacher, student_no=no, defaults={'student_name': name, 'assigned_by': self.admin})
        self.group = LearningGroup.objects.create(title=f'{MARK} SAT 정규반', description='기능 체험용 가짜 반입니다.', term='26FW',
                                                  created_by=self.teacher)
        for no, name in STUDENTS:
            GroupMember.objects.create(group=self.group, student_no=no, student_name=name)
        GroupStaff.objects.create(group=self.group, user=self.ta, duty='TA')
        self.messages_made = 0
        self.assignments()
        self.quizzes()
        self.discussion()
        self.posts_and_notices()
        self.messenger()
        self.report_cards()

    def learner(self, U, no, name, user=None):
        link = StudentAccountLink.objects.filter(student_no=no, relationship='SELF', is_active=True).select_related('user').first()
        if link:
            return link.user
        user = user or self.extra_user(U, f'demo_student_{no}', name, 'STUDENT')
        StudentAccountLink.objects.get_or_create(user=user, student_no=no, relationship='SELF', defaults={'is_active': True})
        return user

    @staticmethod
    def extra_user(U, username, display, role):
        user, made = U.objects.get_or_create(username=username, defaults={'role': role, 'display_name': display})
        if made:
            user.set_unusable_password()  # 대화 상대·명단용. 로그인하지 않는 계정
            user.save(update_fields=['password'])
        return user

    def pdf(self, name):
        return ContentFile((FIXTURES / name).read_bytes(), name=name)

    def assign(self, title, description, due, points=10):
        a = Assignment.objects.create(group=self.group, title=f'{MARK} {title}', description=description, due_at=due, points=points,
                                      created_by=self.teacher, is_published=True)
        return a, {no: AssignmentRecipient.objects.create(assignment=a, student_id=no, student_name=name) for no, name in STUDENTS}

    def submit(self, recipient, *, when, text='', pdf=None, score=None, feedback=''):
        sub = Submission(recipient=recipient, text_answer=text, submitted_at=when)
        if pdf:
            sub.attachment.save(pdf, self.pdf(pdf), save=False)
            sub.attachment_name = pdf
        if score is not None:
            sub.score, sub.feedback, sub.feedback_by, sub.feedback_at = Decimal(score), feedback, self.teacher, when + timedelta(days=1)
        sub.save()
        return sub

    def assignments(self):
        essay_due = at(self.last_monday - timedelta(days=4))
        essay, r = self.assign('Essay: A Lesson I Learned', '배운 교훈에 대한 에세이를 PDF로 제출하세요. 주제문·근거·결론이 드러나게 쓰세요.', essay_due)
        self.submit(r['6333'], when=essay_due - timedelta(hours=5), text='The most important lesson I learned this year is patience...',
                    score='9', feedback='주제문이 분명하고 예시가 좋습니다. 결론을 한 문장 더 다듬어 보세요.')
        graded = self.submit(r['7102'], when=essay_due - timedelta(hours=3), pdf='essay_lesson.pdf', score='8.5',
                             feedback='구조가 안정적입니다. 첨삭 표시를 확인하고 시제를 다시 점검해 주세요.')
        self.submit(r['8201'], when=essay_due - timedelta(hours=1), pdf='summer_essay.pdf')  # 채점 전: 직접 첨삭해 보기
        # 문서 확인값(version_token)은 제출 시각 글자로 만듭니다. 화면은 DB에서 다시 읽은(UTC) 값으로 찾으므로
        # 여기서도 다시 읽어야 같은 문서가 됩니다. 한국 시간 그대로 쓰면 화면이 빈 문서를 새로 만듭니다.
        graded.refresh_from_db()
        doc = create_preview(user=self.teacher, submission=graded)
        marks = [
            {'id': str(uuid4()), 'type': 'area', 'page': 1, 'color': '#2563eb', 'size': 20, 'width': 4, 'text': '첫 문장이 주제를 잘 보여 줍니다.',
             'x': 0.075, 'y': 0.157, 'w': 0.757, 'h': 0.075, 'points': []},
            {'id': str(uuid4()), 'type': 'highlight', 'page': 1, 'color': '#eab308', 'size': 20, 'width': 4, 'text': 'many peoples → many people',
             'x': 0.085, 'y': 0.355, 'w': 0.565, 'h': 0.012, 'points': []},
            {'id': str(uuid4()), 'type': 'strikeout', 'page': 1, 'color': '#dc2626', 'size': 20, 'width': 4, 'text': 'thinked → thought',
             'x': 0.317, 'y': 0.273, 'w': 0.133, 'h': 0.017, 'points': []},
            {'id': str(uuid4()), 'type': 'point', 'page': 1, 'color': '#7c3aed', 'size': 20, 'width': 4, 'text': '여기서 문단을 나누면 더 읽기 쉬워요.',
             'x': 0.62, 'y': 0.48, 'w': 0, 'h': 0, 'points': []},
        ]
        doc.annotations, doc.revision, doc.updated_by = clean_annotations(marks, doc.page_count), 1, self.teacher
        doc.save(update_fields=['annotations', 'revision', 'updated_by', 'updated_at'])

        vocab_due = at(self.last_monday + timedelta(days=1))
        _, r = self.assign('Vocabulary Worksheet', '단어 20개의 뜻과 예문을 쓰세요.', vocab_due)
        self.submit(r['6333'], when=vocab_due - timedelta(hours=2), text='1. abundant - 풍부한 ...', score='10', feedback='완벽합니다!')
        self.submit(r['7102'], when=vocab_due - timedelta(hours=1), text='1. abundant - 풍부한 ...', score='7', feedback='예문 3개가 빠졌어요.')
        self.assign('Unit 3 Reading HW', '교재 Unit 3 지문을 읽고 질문 5개에 답하세요.', self.now + timedelta(days=4))  # 마감 전: 진행중

    def make_quiz(self, title, description, due, questions, max_attempts=1):
        quiz = Quiz.objects.create(group=self.group, title=f'{MARK} {title}', description=description, due_at=due,
                                   time_limit_minutes=30, max_attempts=max_attempts, created_by=self.teacher, is_published=True)
        sync_quiz_questions(quiz, [{'id': None, 'type': q['type'], 'prompt': q['prompt'], 'points': q['points'], 'correct_text': '',
                                    'config': q['config'], 'choices': [{'text': t, 'is_correct': c} for t, c in q['choices']]} for q in questions])
        return quiz, {no: QuizRecipient.objects.create(quiz=quiz, student_id=no, student_name=name) for no, name in STUDENTS}

    def take(self, recipient, user, responses, when, feedback=''):
        attempt = QuizAttempt.objects.create(recipient=recipient, user=user, attempt_no=1, started_at=when - timedelta(minutes=18), submitted_at=when)
        total = earned = Decimal('0')
        for question, response in zip(recipient.quiz.questions.order_by('order'), responses):
            points = quiz_types.grade(question, response)
            QuizAnswer.objects.create(attempt=attempt, question=question, response=response, earned_points=points,
                                      selected_choice_id=response.get('choice'))
            total += question.points
            earned += points
        attempt.score, attempt.max_score = earned, total
        if feedback:
            attempt.feedback, attempt.feedback_at, attempt.feedback_by = feedback, when + timedelta(hours=3), self.teacher
        attempt.save()

    @staticmethod
    def choice(question, text):
        return question.choices.get(text=text).pk

    def quizzes(self):
        quiz, r = self.make_quiz('Canvas 7가지 유형 퀴즈', '객관식·복수 선택·참거짓·순서·짝 맞추기·빈칸·분류 7가지 문항을 모두 담았습니다.',
                                 self.now + timedelta(days=7), CANVAS_QUESTIONS, max_attempts=3)
        q = list(quiz.questions.order_by('order'))
        responses = [
            {'choice': self.choice(q[0], 'glad')},
            {'choices': sorted([self.choice(q[1], 'apple'), self.choice(q[1], 'run')])},  # 하나 틀림 → 부분 점수
            {'choice': self.choice(q[2], '참')},
            {'order': ['o1', 'o2', 'o3', 'o4']},
            {'pairs': {'m1': '용감한', 'm2': '정직한', 'm3': '조용한'}},  # 두 개 바뀜
            {'blanks': ['went', 'library', 'books']},
            {'placed': {'k1': 'c1', 'k2': 'c1', 'k3': 'c2', 'k4': 'c2'}},
        ]
        self.take(r['6333'], self.learners['6333'], responses, self.now - timedelta(days=1), feedback='순서·빈칸 문제는 완벽해요. 짝 맞추기를 다시 보세요.')

        vocab, r = self.make_quiz('Vocab Quiz Day 2', '단어 3문항 확인 퀴즈', at(self.last_monday + timedelta(days=2)), VOCAB_QUESTIONS)
        v = list(vocab.questions.order_by('order'))
        when = at(self.last_monday + timedelta(days=2), 17)
        self.take(r['6333'], self.learners['6333'], [{'choice': self.choice(v[0], '풍부한')}, {'choice': self.choice(v[1], '꺼리는')}, {'choice': self.choice(v[2], '짧은')}], when)
        self.take(r['7102'], self.learners['7102'], [{'choice': self.choice(v[0], '풍부한')}, {'choice': self.choice(v[1], '열정적인')}, {'choice': self.choice(v[2], '짧은')}], when)

    def discussion(self):
        d = Discussion.objects.create(group=self.group, title=f'{MARK} 토론: SNS는 청소년에게 도움이 될까?',
                                      content='찬성·반대 중 하나를 골라 근거 두 가지와 함께 의견을 남기고, 친구 의견에 한 번 이상 답글을 다세요.',
                                      due_at=self.now + timedelta(days=5), created_by=self.teacher, is_published=True)
        for no, name in STUDENTS:
            DiscussionRecipient.objects.create(discussion=d, student_id=no, student_name=name)
        for user, no, text in [
            (self.learners['6333'], '6333', '도움이 된다고 생각합니다. 공부 모임을 쉽게 만들 수 있고, 외국 친구와 영어로 대화할 기회가 생깁니다.'),
            (self.learners['7102'], '7102', '반대합니다. 알림 때문에 집중이 자주 끊기고, 비교하는 마음이 생겨 자존감이 떨어질 수 있어요.'),
            (self.teacher, '', '두 의견 모두 근거가 분명해요. 상대 근거에 반박하는 문장을 하나씩 더 써 보세요.'),
        ]:
            DiscussionComment.objects.create(discussion=d, author=user, student_id=no, content=text)

    def posts_and_notices(self):
        ClassPost.objects.create(group=self.group, kind='NOTICE', title=f'{MARK} 이번 주 수업 안내', pinned=True, created_by=self.teacher,
                                 body='이번 주는 Reading 추론 문제와 Writing 문장 연결을 집중해서 다룹니다. 단어 퀴즈는 수요일입니다.')
        ClassPost.objects.create(group=self.group, kind='PAGE', title=f'{MARK} Week 8 단어장', created_by=self.teacher,
                                 body='abundant 풍부한\nreluctant 꺼리는\nbrief 짧은\nconsistent 일관된\nnotable 주목할 만한')
        post = ClassPost.objects.create(group=self.group, kind='FILE', title=f'{MARK} 수업 자료: Reading Passage', created_by=self.teacher,
                                        body='수업에서 읽을 지문입니다. 미리 한 번 읽어 오세요.')
        data = (FIXTURES / 'summer_essay.pdf').read_bytes()
        attached = PostFile(post=post, original_name='reading_passage.pdf', size=len(data))
        attached.file.save('reading_passage.pdf', ContentFile(data), save=False)
        attached.save()
        Notice.objects.create(title=f'{MARK} 학원 공지: 11월 휴원 안내', content='11월 셋째 주 월요일은 휴원입니다. 보강 일정은 반별로 안내드립니다.',
                              category=Notice.Category.ACADEMY, for_admin=True, for_teacher=True, for_student=True, for_parent=True,
                              is_pinned=True, is_published=True, published_at=self.now, created_by=self.admin)
        Notice.objects.create(title=f'{MARK} 반 공지: 모의고사 일정', content='다음 주 토요일 오전 10시에 SAT 모의고사를 봅니다. 계산기를 꼭 챙기세요.',
                              category=Notice.Category.CLASS, group=self.group, for_teacher=True, for_student=True, for_parent=True,
                              is_published=True, published_at=self.now, created_by=self.teacher)

    def say(self, conv, user, body):
        Message.objects.create(conversation=conv, sender=user, body=body, client_token=self.token(self.messages_made))
        self.messages_made += 1

    def messenger(self):
        room = rooms.sync_class_room(self.group)
        for user, body in [(self.teacher, '이번 주 단어 퀴즈는 수요일입니다. 다들 준비해 주세요!'),
                           (self.learners['6333'], '네, 범위가 Week 8 단어장 전체인가요?'),
                           (self.teacher, '맞아요. 반 공지에 올린 단어장 전체입니다.'),
                           (self.learners['7102'], '감사합니다 😊')]:
            self.say(room, user, body)
        group_chat = Conversation.objects.create(title=f'{MARK} 에세이 스터디', kind=Conversation.Kind.GROUP, created_by=self.teacher)
        for user in (self.teacher, self.learners['6333'], self.learners['7102']):
            ConversationMember.objects.create(conversation=group_chat, user=user)
        for user, body in [(self.teacher, '에세이 첨삭 결과 올렸어요. 각자 확인해 보세요.'),
                           (self.learners['7102'], '시제 실수가 많았네요. 다음에는 꼭 다시 읽어 볼게요.'),
                           (self.learners['6333'], '결론 문장 고쳐서 다시 보내도 될까요?')]:
            self.say(group_chat, user, body)
        direct = rooms.direct_room(self.teacher, self.learners['6333'])
        for user, body in [(self.learners['6333'], '선생님, 퀴즈 짝 맞추기 문제를 다시 풀어 봐도 되나요?'),
                           (self.teacher, '네, 응시 기회가 3번이라 한 번 더 볼 수 있어요.')]:
            self.say(direct, user, body)

    def report_cards(self):
        week_start, week_end = self.last_monday, self.last_monday + timedelta(days=4)
        term_start, term_end = self.last_monday - timedelta(days=21), week_end
        make = lambda form, start, end, base, title: report_services.create_batch(
            group=self.group, form=form, title=title, period_start=start, period_end=end, week_base=base, user=self.teacher)
        season = f'{week_start.year} FW'
        sat = make('SAT', week_start, week_end, week_start, season)
        toefl = make('TOEFL', week_start, week_end, week_start, season)
        ap = make('AP', term_start, term_end, term_start - timedelta(days=21), season)
        gpa = make('GPA_ESSAY', term_start, term_end, term_start - timedelta(days=21), season)
        junior = make('JUNIOR', term_start, term_end, term_start, season)
        day = lambda n: (week_start + timedelta(days=n)).strftime('%m-%d')
        prev = lambda n: (week_start - timedelta(days=7 - n)).strftime('%m-%d')
        for card in sat.cards.all():
            d = card.data
            d['skill'] = ['PASS', 'PASS', 'FAIL', 'PASS', 'PASS']
            d['attitude'] = [{'a': '5', 'b': '5'} for _ in range(5)]
            d['mock']['this'][:2] = [{'date': day(1), 'rw': '620', 'rw_avg': '598', 'math': '670', 'math_avg': '642'},
                                     {'date': day(3), 'rw': '640', 'rw_avg': '605', 'math': '690', 'math_avg': '650'}]
            d['mock']['last'][:2] = [{'date': prev(1), 'rw': '590', 'rw_avg': '584', 'math': '650', 'math_avg': '631'},
                                     {'date': prev(3), 'rw': '600', 'rw_avg': '590', 'math': '660', 'math_avg': '636'}]
            d['blocks']['laser'] = f'{card.student_name} 학생은 지문 구조를 마인드맵으로 정리하는 힘이 좋아졌습니다. 결론을 스스로 다시 써 보는 연습을 이어가면 좋겠습니다.'
            d['blocks']['correction'] = '오답노트에 틀린 이유를 한 줄씩 적기 시작했습니다. 이 습관을 계속 이어가 주세요.'
            d['personal'] = f'{card.student_name} 학생은 과제를 성실하게 수행하고 있습니다. 추론 문제는 주말 추가 과제로 보완하겠습니다.'
            card.save()
        for card in toefl.cards.all():
            d = card.data
            d['skill'] = ['PASS', 'FAIL', 'PASS', 'PASS', 'PASS']
            d['attitude'] = [{'a': '5', 'b': '4'} for _ in range(5)]
            d['mock'] = {'this': {'r': '22', 'l': '27', 's': '20', 'w': '24', 'total': '93'}, 'last': {'r': '20', 'l': '25', 's': '19', 'w': '21', 'total': '85'}}
            d['mock_comment'] = {'rw': '이메일 쓰기의 목적이 분명했고 지난주보다 점수가 올랐습니다. 마지막 1–2분은 문법 점검에 쓰세요.',
                                 'ls': '답변 방향은 좋지만 구체적인 예시가 부족합니다. 문장 확장 연습을 이어가세요.'}
            d['blocks']['writing'] = '주제에 맞게 입장을 제시하고 이유를 연결하려는 시도가 좋았습니다.'
            d['personal'] = '매일 녹음 과제를 빠짐없이 냈습니다.'
            card.save()
        ap.shared['content'] = 'Unit 1 신경계와 신경전달물질을 공부했습니다. 숙제와 Mid-Term은 실제 시험보다 한 단계 어렵게 출제했습니다.'
        ap.save()
        for card in ap.cards.all():
            card.data['comment'] = f'안녕하세요, AP 수업을 맡고 있는 강사입니다. {card.student_name} 학생은 수업 참여가 적극적이고 숙제 점수가 꾸준히 오르고 있습니다.'
            card.save()
        gpa.shared['content'] = '단편소설을 읽고 인물·배경·주제를 근거로 분석하는 글쓰기를 연습했습니다.'
        gpa.save()
        for card in gpa.cards.all():
            card.data['comment'] = f'{card.student_name} 학생은 매주 글쓰기 과제를 성실히 제출하고, 피드백을 반영해 글을 고쳐 나가고 있습니다.'
            card.save()
        junior.shared['focus'] = 'Topic Sentence → Evidence → Explanation 의 연결을 의식하며 문단을 쓰는 연습에 집중했습니다.'
        junior.shared['next_plan'] = '다음 달에는 문법 정확성과 학술 어휘를 넓히는 데 집중합니다.'
        for label in junior.shared.get('contents', {}):
            junior.shared['contents'][label] = 'Body Paragraph 의 근거와 설명을 연결하는 법을 배웠습니다.'
        junior.save()
        for card in junior.cards.all():
            for row in card.data['rows']:
                row['attitude'], row['comment'] = '5', '수업 태도가 바르고 질문에 적극적으로 답했습니다.'
            card.data['achievement'] = '중심 주장을 분명히 제시하고 근거로 뒷받침하는 힘이 좋아졌습니다.'
            card.data['overall'] = f'{card.student_name} 학생은 꾸준히 성장하고 있습니다. 문장을 간결하게 다듬는 연습을 이어가면 좋겠습니다.'
            card.save()
