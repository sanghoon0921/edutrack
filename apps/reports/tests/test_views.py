from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentAccountLink
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.learning.models import LearningGroup, Quiz, QuizAttempt, QuizRecipient
from apps.lms.models import GroupMember, GroupStaff
from apps.reports.models import ReportBatch, ReportCard
from apps.students.attendance_repositories import DemoAttendanceRepository


def at(day, hour=18):
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


@override_settings(STUDENT_DATA_SOURCE='demo', ASSESSMENT_DATA_SOURCE='demo', ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class ReportFixture(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_user('rc_admin', password='x', role='ADMIN')
        self.teacher = U.objects.create_user('rc_teacher', password='x', role='TEACHER', display_name='김강사T')
        self.ta = U.objects.create_user('rc_ta', password='x', role='TEACHER', display_name='데모 TA')
        self.other_teacher = U.objects.create_user('rc_other', password='x', role='TEACHER')
        self.student = U.objects.create_user('rc_student', password='x', role='STUDENT')
        StudentAccountLink.objects.create(user=self.student, student_no='6333', relationship='SELF', is_active=True)
        self.group = LearningGroup.objects.create(title='AP Psychology (일)', created_by=self.teacher)
        GroupStaff.objects.create(group=self.group, user=self.ta, duty='TA')
        for no, name in [('6333', '김지훈'), ('7102', '이서연')]:
            GroupMember.objects.create(group=self.group, student_no=no, student_name=name)
        # 1주차 = 8/23(일). W4 과제는 김지훈만 제출·채점, W5 퀴즈는 김지훈 응시.
        self.hw = Assignment.objects.create(title='Unit 1 HW', description='-', group=self.group, created_by=self.teacher, due_at=at(date(2026, 9, 15)), points=15)
        r1 = AssignmentRecipient.objects.create(assignment=self.hw, student_id='6333', student_name='김지훈')
        AssignmentRecipient.objects.create(assignment=self.hw, student_id='7102', student_name='이서연')
        Submission.objects.create(recipient=r1, text_answer='답', submitted_at=at(date(2026, 9, 14)), score=Decimal('13'))
        self.quiz = Quiz.objects.create(title='Vocab 1', group=self.group, created_by=self.teacher, due_at=at(date(2026, 9, 22)))
        qr = QuizRecipient.objects.create(quiz=self.quiz, student_id='6333', student_name='김지훈')
        QuizAttempt.objects.create(recipient=qr, user=self.student, attempt_no=1, submitted_at=at(date(2026, 9, 21)), score=Decimal('28'), max_score=Decimal('30'))

    def create(self, user=None, **extra):
        self.client.force_login(user or self.admin)
        payload = {'group': self.group.pk, 'form': 'AP', 'period_start': '2026-09-13',
                   'period_end': '2026-10-11', 'week_base': '2026-08-23', **extra}
        return self.client.post(reverse('reports:new'), payload)


class AccessTests(ReportFixture):
    def test_students_cannot_open_report_cards(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('reports:list')).status_code, 404)
        self.assertEqual(self.client.get(reverse('reports:new')).status_code, 404)

    def test_teacher_sees_menu_and_list(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('reports:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '리포트카드')
        self.assertContains(response, reverse('reports:list'))

    def test_other_teacher_cannot_use_someone_elses_class(self):
        response = self.create(self.other_teacher)
        self.assertNotEqual(response.status_code, 302)  # 11/19: 강사도 만들지만 남의 반은 선택지에 없어 만들어지지 않음
        self.assertFalse(ReportBatch.objects.exists())
        self.create()
        batch = ReportBatch.objects.get()
        card = batch.cards.first()
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('reports:card', args=[batch.pk, card.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('reports:refresh', args=[batch.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('reports:print', args=[batch.pk])).status_code, 404)

    def test_ta_of_the_class_can_edit(self):
        self.create()
        batch = ReportBatch.objects.get()
        self.client.force_login(self.ta)
        self.assertEqual(self.client.get(reverse('reports:card', args=[batch.pk, batch.cards.first().pk])).status_code, 200)


class CreateTests(ReportFixture):
    def test_creates_one_card_per_member_with_loaded_data(self):
        response = self.create()
        batch = ReportBatch.objects.get()
        first = batch.cards.order_by('student_name').first()
        self.assertRedirects(response, reverse('reports:card', args=[batch.pk, first.pk]), fetch_redirect_response=False)
        self.assertEqual(batch.cards.count(), 2)
        kim = batch.cards.get(student_no='6333')
        self.assertEqual(kim.data['info'], {'name': '김지훈', 'region': '태국 방콕 Ekamai International School', 'grade': '10학년'})
        self.assertEqual(kim.data['weeks'][3], {'label': 'WEEK4', 'status': '제출완료'})
        self.assertEqual(kim.data['weeks'][4]['status'], '제출완료')  # 퀴즈 응시
        self.assertEqual(kim.data['weeks'][0]['status'], '해당없음')
        self.assertEqual(kim.data['weeks'][8]['status'], '')  # 기간 뒤
        self.assertEqual(kim.data['scores'], 'W4 Unit 1 HW 13/15\nW5 Vocab 1 28/30')
        lee = batch.cards.get(student_no='7102')
        self.assertEqual(lee.data['weeks'][3]['status'], '미제출')
        self.assertEqual(batch.shared['class_name'], 'AP Psychology (일)')
        self.assertEqual(batch.shared['teacher'], '김강사T, 데모 TA')
        self.assertEqual(batch.shared['weeks_label'], 'WEEK4-8')
        self.assertEqual(batch.shared['period'], '9/13 ~ 10/11')

    def test_external_reads_finish_before_anything_is_written(self):
        """인트라넷·DSG를 기다리는 동안 SQLite 쓰기 잠금을 쥐면 다른 사람 저장·로그아웃이 'database is locked'로 실패합니다."""
        from unittest import mock

        from apps.reports import sources
        written_during_read = []
        real_info = sources.student_info

        def watching_info(numbers, **kwargs):
            written_during_read.append(ReportBatch.objects.exists())
            return real_info(numbers, **kwargs)

        with mock.patch.object(sources, 'student_info', side_effect=watching_info):
            self.create()
        self.assertEqual(written_during_read, [False])
        self.assertEqual(ReportBatch.objects.get().cards.count(), 2)

    def test_card_page_shows_report_layout(self):
        self.create()
        batch = ReportBatch.objects.get()
        response = self.client.get(reverse('reports:card', args=[batch.pk, batch.cards.get(student_no='6333').pk]))
        self.assertContains(response, 'AP REPORT CARD')
        self.assertContains(response, '26FW')  # 제목(시즌) 칸이 없어져 기간으로 정한 시즌 코드(11/17)
        self.assertContains(response, 'name="d.comment"')
        self.assertContains(response, 'name="s.content"')
        self.assertContains(response, 'W4 Unit 1 HW 13/15')
        self.assertContains(response, '이서연')  # 학생 이동 목록

    def test_new_page_offers_intranet_courses_of_members(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports:new'), {'group': self.group.pk})
        self.assertContains(response, '2026 여름특강 SAT Advanced')

    def test_junior_rows_use_course_lesson_dates(self):
        lessons = [r.lesson_date for r in DemoAttendanceRepository().list_by_student_and_assign('6333', '10001')]
        first = min(lessons)
        self.create(form='JUNIOR', course='201', week_base=first.isoformat(), period_start=first.isoformat(), period_end=max(lessons).isoformat())
        batch = ReportBatch.objects.get()
        self.assertEqual(batch.course_class_id, '201')
        row = batch.cards.get(student_no='6333').data['rows'][0]
        self.assertEqual(row['label'], 'WEEK1')
        self.assertEqual(row['date'], f'{first.month}/{first.day}')
        self.assertIn('WEEK1', batch.shared['contents'])

    def test_sat_weekly_loads_dsg_mock_scores(self):
        self.create(form='SAT', period_start='2026-07-20', period_end='2026-07-24', week_base='2026-07-20')
        card = ReportBatch.objects.get().cards.get(student_no='6333')
        this = card.data['mock']['this'][0]
        self.assertEqual(this['date'], '07-20')
        self.assertTrue(this['rw'] and this['rw_avg'])
        self.assertEqual(len(card.data['task']), 5)


class EditTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])

    def test_save_updates_known_cells_and_shared_text_only(self):
        response = self.client.post(self.url, {'d.comment': '안녕하세요 어머니', 'd.weeks.6.status': '해당없음',
                                               's.content': 'Unit 1 신경계', 'd.hacked': 'x', 'save': '1'})
        # 저장하면 완성된 카드 보기 화면으로 갑니다(11/10).
        self.assertRedirects(response, reverse('reports:list'), fetch_redirect_response=False)  # 11/19: 저장하면 목록으로
        self.card.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(self.card.data['comment'], '안녕하세요 어머니')
        self.assertEqual(self.card.data['weeks'][6]['status'], '해당없음')
        self.assertNotIn('hacked', self.card.data)
        self.assertEqual(self.batch.shared['content'], 'Unit 1 신경계')
        other = self.batch.cards.get(student_no='7102')
        self.assertContains(self.client.get(reverse('reports:card', args=[self.batch.pk, other.pk])), 'Unit 1 신경계')

    def test_save_and_next_moves_to_next_student(self):
        nxt = self.batch.cards.get(student_no='7102')
        response = self.client.post(self.url, {'d.comment': 'x', 'next': '1'})
        self.assertRedirects(response, reverse('reports:card', args=[self.batch.pk, nxt.pk]), fetch_redirect_response=False)

    def test_refresh_reloads_auto_cells_but_keeps_teacher_edits(self):
        self.client.post(self.url, {'d.comment': '코멘트', 'd.scores': '직접 고친 점수'})
        # 새 과제(W6)를 내고 김지훈이 제출
        hw = Assignment.objects.create(title='Unit 2 HW', description='-', group=self.group, created_by=self.teacher, due_at=at(date(2026, 9, 29)), points=15)
        r = AssignmentRecipient.objects.create(assignment=hw, student_id='6333', student_name='김지훈')
        Submission.objects.create(recipient=r, text_answer='답', submitted_at=at(date(2026, 9, 28)))
        GroupMember.objects.create(group=self.group, student_no='8201', student_name='박민준')
        response = self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.card.refresh_from_db()
        self.assertEqual(self.card.data['comment'], '코멘트')
        self.assertEqual(self.card.data['scores'], '직접 고친 점수')
        self.assertEqual(self.card.data['weeks'][5]['status'], '제출완료')
        self.assertTrue(self.batch.cards.filter(student_no='8201').exists())

    def test_refresh_reads_intranet_outside_the_write_transaction(self):
        """WAL 모드에서 거래 안에서 오래 기다린 뒤 쓰면, 그사이 다른 저장이 있었을 때 바로 'database is locked'가 납니다."""
        from unittest import mock

        from django.db import connection

        from apps.reports import sources
        depth_outside = len(connection.atomic_blocks)
        depths = []
        real_info = sources.student_info

        def watching_info(numbers, **kwargs):
            depths.append(len(connection.atomic_blocks))
            return real_info(numbers, **kwargs)

        with mock.patch.object(sources, 'student_info', side_effect=watching_info):
            self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk})
        self.assertEqual(depths, [depth_outside])

    def test_print_pages(self):
        self.client.post(self.url, {'s.intro': '', 'd.comment': '유나 학생 칭찬'})
        response = self.client.get(reverse('reports:print', args=[self.batch.pk]))
        self.assertContains(response, 'AP REPORT CARD', count=2)
        self.assertContains(response, '유나 학생 칭찬')
        self.assertNotContains(response, 'name="d.comment"')
        one = self.client.get(reverse('reports:card-print', args=[self.batch.pk, self.card.pk]))
        self.assertContains(one, 'AP REPORT CARD', count=1)

    def test_delete_batch(self):
        response = self.client.post(reverse('reports:delete', args=[self.batch.pk]))
        self.assertRedirects(response, reverse('reports:list'), fetch_redirect_response=False)
        self.assertFalse(ReportCard.objects.exists())


class WeeklyRenderTests(ReportFixture):
    def test_weekly_cards_personalize_intro_when_printing(self):
        self.create(form='TOEFL', period_start='2026-09-14', period_end='2026-09-18', week_base='2026-09-14')
        batch = ReportBatch.objects.get()
        card = batch.cards.get(student_no='6333')
        edit = self.client.get(reverse('reports:card', args=[batch.pk, card.pk]))
        self.assertContains(edit, '{이름}')
        printed = self.client.get(reverse('reports:card-print', args=[batch.pk, card.pk]))
        self.assertContains(printed, 'AP Psychology (일) 김지훈 학생을 담당하고 있는 김강사T, 데모 TA입니다.')
        self.assertNotContains(printed, '<svg')  # TOEFL 점수는 손으로 넣기 전엔 그래프 대신 안내
        self.client.post(reverse('reports:card', args=[batch.pk, card.pk]),
                         {'d.mock.this.r': '22', 'd.mock.this.l': '27', 'd.mock.last.r': '25'})
        printed = self.client.get(reverse('reports:card-print', args=[batch.pk, card.pk]))
        self.assertContains(printed, '<svg')


class WeeklyBlockEditTests(ReportFixture):
    """주간 개별 코멘트 칸(과제별 코멘트)을 퀴즈 문항처럼 더하고·지우고·이름을 바꿉니다. 칸 목록은 반 공통, 코멘트는 학생별."""

    def setUp(self):
        super().setUp()
        self.create(form='SAT', period_start='2026-09-14', period_end='2026-09-18', week_base='2026-09-14')
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')
        self.url = reverse('reports:card', args=[self.batch.pk, self.card.pk])
        # SAT 카드의 칸 구성은 관리자가 합니다(10/29: 강사는 수업 태도, TA는 코멘트만).
        self.client.force_login(self.admin)

    def test_add_rename_comment_and_delete_a_block(self):
        self.assertEqual([b['title'] for b in self.batch.shared['block_list']][:2], ['Laser Focus', 'Poetry'])
        response = self.client.post(reverse('reports:block-add', args=[self.batch.pk]), {'card': self.card.pk, 'd.personal': '먼저 쓴 코멘트'})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.batch.refresh_from_db(); self.card.refresh_from_db()
        new = self.batch.shared['block_list'][-1]
        self.assertEqual(len(self.batch.shared['block_list']), 6)
        self.assertEqual(self.card.data['personal'], '먼저 쓴 코멘트')  # 누르기 전 입력도 저장
        for card in self.batch.cards.all():
            self.assertEqual(card.data['blocks'][new['key']], '')
        self.client.post(self.url, {'s.block_list.5.title': 'Vocabulary Review', 's.block_list.5.desc': '단어 복습 과제',
                                    f'd.blocks.{new["key"]}': '단어를 꾸준히 외웠습니다.'})
        page = self.client.get(reverse('reports:card-print', args=[self.batch.pk, self.card.pk]))
        self.assertContains(page, 'Vocabulary Review')
        self.assertContains(page, '단어를 꾸준히 외웠습니다.')
        edit = self.client.get(self.url)
        self.assertContains(edit, reverse('reports:block-delete', args=[self.batch.pk, new['key']]))
        self.client.post(reverse('reports:block-delete', args=[self.batch.pk, 'poetry']), {'card': self.card.pk})
        self.batch.refresh_from_db()
        self.assertNotIn('poetry', [b['key'] for b in self.batch.shared['block_list']])
        for card in self.batch.cards.all():
            self.assertNotIn('poetry', card.data['blocks'])
        self.assertNotContains(self.client.get(reverse('reports:card-print', args=[self.batch.pk, self.card.pk])), 'Poetry')

    def test_unknown_block_delete_is_404_and_other_teacher_cannot_add(self):
        self.assertEqual(self.client.post(reverse('reports:block-delete', args=[self.batch.pk, 'nope'])).status_code, 404)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.post(reverse('reports:block-add', args=[self.batch.pk])).status_code, 404)

    def test_cards_made_before_block_list_still_open(self):
        shared = self.batch.shared
        shared.pop('block_list')
        shared['blocks'] = {'laser': '옛 설명', 'poetry': '', 'guided': '', 'correction': '', 'reflection': ''}
        self.batch.save()
        response = self.client.get(self.url)
        self.assertContains(response, '옛 설명')
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.shared['block_list'][0], {'key': 'laser', 'title': 'Laser Focus', 'desc': '옛 설명'})

    def test_new_member_card_gets_added_blocks(self):
        self.client.post(reverse('reports:block-add', args=[self.batch.pk]), {'card': self.card.pk})
        key = ReportBatch.objects.get().shared['block_list'][-1]['key']
        GroupMember.objects.create(group=self.group, student_no='8201', student_name='박민준')
        self.client.post(reverse('reports:refresh', args=[self.batch.pk]), {'card': self.card.pk})
        self.assertIn(key, self.batch.cards.get(student_no='8201').data['blocks'])
