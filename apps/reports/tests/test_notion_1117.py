"""운영팀 요청 2026.11.17: 리포트카드 만들기 순서·Term·반 거르기, AP·GPA 수업일 5칸, 주니어 주차·기간,
목록 필터·발송 현황, 관리자만 공개·강사·TA는 코멘트, 저장 현황, SAT·TOEFL 새 디자인,
첨삭 번호 표기, 관리자 대화방 삭제, TA 반별 학습 권한, 학생 첫 로그인 설정."""
import json
import re
from datetime import date
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms import rooms
from apps.lms.models import Conversation, GroupMember, GroupStaff, Message
from apps.lms.tests.test_lms import LmsFixture
from apps.reports import sources
from apps.reports.formats import season_heading
from apps.reports.forms import group_forms
from apps.reports.models import ReportBatch
from apps.reports.templatetags.report_tags import vocab_status
from apps.reports.tests.test_views import ReportFixture


class AnnotationNumberLabelTests(SimpleTestCase):
    def test_comment_list_shows_numbers_not_tool_names(self):
        js = (Path(settings.BASE_DIR) / 'apps/lms/static/lms/js/annotation.js').read_text(encoding='utf-8')
        self.assertNotIn("kind.textContent=labels[m.type]", js)
        self.assertIn("num.title=labels[m.type]", js)


class RoomDeleteTests(LmsFixture):
    def test_admin_deletes_a_room_and_its_messages(self):
        conv = rooms.direct_room(self.teacher, self.student)
        Message.objects.create(conversation=conv, sender=self.teacher, body='지울 메시지', client_token=uuid4())
        self.login(self.admin)
        r = self.client.post(reverse('lms:conversation-delete', args=[conv.pk]))
        self.assertRedirects(r, reverse('lms:inbox'), fetch_redirect_response=False)
        self.assertFalse(Conversation.objects.filter(pk=conv.pk).exists())
        self.assertFalse(Message.objects.filter(body='지울 메시지').exists())

    def test_teachers_cannot_delete_and_see_no_button(self):
        conv = rooms.direct_room(self.teacher, self.student)
        self.login(self.teacher)
        self.assertNotContains(self.client.get(reverse('lms:conversation', args=[conv.pk])), reverse('lms:conversation-delete', args=[conv.pk]))
        self.assertEqual(self.client.post(reverse('lms:conversation-delete', args=[conv.pk])).status_code, 403)
        self.assertTrue(Conversation.objects.filter(pk=conv.pk).exists())


class ReportPermissionTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get()
        self.card = self.batch.cards.get(student_no='6333')

    def test_teacher_creates_and_refreshes_but_only_admin_sends(self):
        # 11/19: 만들기·다시 불러오기는 강사·TA도, 발송(공개)·발송 취소는 관리자만
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('reports:new')).status_code, 200)
        self.assertEqual(self.client.post(reverse('reports:refresh', args=[self.batch.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse('reports:unpublish', args=[self.batch.pk])).status_code, 404)
        list_html = self.client.get(reverse('reports:list')).content.decode()
        self.assertIn(f'href="{reverse("reports:new")}"', list_html)

    def test_teacher_writes_every_field_on_other_forms(self):
        self.client.force_login(self.teacher)
        html = self.client.get(reverse('reports:card', args=[self.batch.pk, self.card.pk])).content.decode()
        names = set(re.findall(r'name="([ds]\.[^"]+)"', html))
        self.assertIn('d.comment', names)
        self.assertGreater(len(names), 1)

    def test_admin_sees_live_save_status(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('reports:card', args=[self.batch.pk, self.card.pk]), {'d.comment': '좋아요', 'save': '1'})
        self.client.force_login(self.admin)
        page = self.client.get(reverse('reports:batch', args=[self.batch.pk])).content.decode()
        self.assertIn(f'data-rc-status="{reverse("reports:status", args=[self.batch.pk])}"', page)
        data = json.loads(self.client.get(reverse('reports:status', args=[self.batch.pk])).content)
        row = next(r for r in data['cards'] if r['id'] == self.card.pk)
        self.assertTrue(row['saved'])
        self.assertEqual(row['by'], '김강사T')


class ReportListFilterTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.group.term = '26FW'
        self.group.save()
        self.other = LearningGroup.objects.create(title='26SP AP Bio', term='26SP', created_by=self.teacher)
        GroupMember.objects.create(group=self.other, student_no='6333', student_name='학생')
        self.create()
        self.create(group=self.other.pk)
        self.first, self.second = ReportBatch.objects.order_by('pk')
        self.client.force_login(self.admin)
        self.client.post(reverse('reports:publish', args=[self.first.pk]))

    def rows(self, **params):
        html = self.client.get(reverse('reports:list'), params).content.decode()
        return html.split('<tbody>', 1)[1].split('</tbody>', 1)[0] if '<tbody>' in html else ''

    def test_term_class_and_send_filters(self):
        self.assertIn(self.group.title, self.rows(term='26FW'))
        self.assertNotIn(self.other.title, self.rows(term='26FW'))
        self.assertIn(self.other.title, self.rows(group=self.other.pk))
        self.assertNotIn(self.group.title, self.rows(group=self.other.pk))
        self.assertIn(self.group.title, self.rows(send='sent'))
        self.assertNotIn(self.other.title, self.rows(send='sent'))
        self.assertIn(self.other.title, self.rows(send='unsent'))

    def test_each_batch_shows_its_send_state(self):
        rows = self.rows()
        self.assertIn('발송 ·', rows)
        self.assertIn('미발송', rows)


class NewFormOrderTests(ReportFixture):
    def test_steps_run_form_term_class_and_no_title_box(self):
        self.group.term = '26FW'
        self.group.save()
        self.client.force_login(self.admin)
        html = self.client.get(reverse('reports:new')).content.decode()
        self.assertLess(html.index('name="form"'), html.index('name="term"'))
        self.assertLess(html.index('name="term"'), html.index('name="group"'))
        self.assertNotIn('name="title"', html)
        self.assertIn('data-term="26FW"', html)
        self.assertIn('data-forms="AP"', html)
        self.assertIn('data-rc-preview="SAT"', html)

    def test_title_comes_from_the_chosen_term(self):
        self.group.term = '26FW'
        self.group.save()
        self.create(term='26FW')
        self.assertEqual(ReportBatch.objects.get().title, '26FW')

    def test_class_subject_comes_from_its_name(self):
        make = lambda t: LearningGroup(title=t)
        self.assertEqual(group_forms(make('26FW SAT(RW)')), ['SAT'])
        self.assertEqual(group_forms(make('토플 정규반')), ['TOEFL'])
        self.assertEqual(group_forms(make('AP Psychology (일)')), ['AP'])
        self.assertEqual(group_forms(make('GPA Essay 반')), ['GPA_ESSAY'])
        self.assertEqual(group_forms(make('주니어 영어')), ['JUNIOR'])
        self.assertEqual(group_forms(make('Apple 반')), [])


class TermLessonRowsTests(ReportFixture):
    def test_submission_dates_come_five_to_a_row(self):
        self.create()
        batch = ReportBatch.objects.get()
        html = self.client.get(reverse('reports:card', args=[batch.pk, batch.cards.get(student_no='6333').pk])).content.decode()
        table = html.split('rc-weeks', 1)[1].split('</table>', 1)[0]
        heads = re.findall(r'<tr class="rc-grid-head">(.*?)</tr>', table, re.S)
        self.assertTrue(heads)
        self.assertTrue(all(h.count('<th') == 6 for h in heads))  # 머리 1칸 + 5칸


class JuniorLayoutTests(ReportFixture):
    def test_week_and_period_move_to_the_info_table(self):
        self.create(form='JUNIOR')
        batch = ReportBatch.objects.get()
        html = self.client.get(reverse('reports:card', args=[batch.pk, batch.cards.get(student_no='6333').pk])).content.decode()
        info = html.split('class="rc-info"', 1)[1].split('</table>', 1)[0]
        self.assertIn('<th>주차</th>', info)
        self.assertIn('<th>기간</th>', info)
        self.assertIn('<thead><tr><th>수업일</th>', html)


class WeeklyDesignTests(ReportFixture):
    def card_html(self, **dates):
        self.create(form='SAT', **dates)
        batch = ReportBatch.objects.get()
        return self.client.get(reverse('reports:card-view', args=[batch.pk, batch.cards.get(student_no='6333').pk])).content.decode()

    def test_a_month_long_card_is_the_monthly_design_with_weekly_dates(self):
        html = self.card_html(period_start='2026-09-26', period_end='2026-10-24', week_base='2026-09-26')
        self.assertIn('MONTHLY STUDENT REPORT', html)
        self.assertIn('2026 FALL / WINTER', html)
        for label in ('9/26', '10/3', '10/10', '10/17', '10/24'):
            self.assertIn(f'<th>{label}</th>', html)

    def test_a_one_week_card_keeps_weekday_columns(self):
        html = self.card_html(period_start='2026-09-14', period_end='2026-09-18', week_base='2026-09-14')
        self.assertIn('WEEKLY STUDENT REPORT', html)
        self.assertIn('9/14(월)', html)

    def test_season_headings(self):
        self.assertEqual(season_heading('26FW'), '2026 FALL / WINTER')
        self.assertEqual(season_heading('2627WT'), '2026–2027 WINTER')
        self.assertEqual(season_heading('특강'), '특강')

    def test_vocab_completion_labels(self):
        self.assertEqual(vocab_status({'score': '7', 'max': '7'}), 'PASS')
        self.assertEqual(vocab_status({'score': '3', 'max': '7'}), 'PARTIAL')
        self.assertEqual(vocab_status({'score': '0', 'max': '7'}), 'FAIL')
        self.assertEqual(vocab_status({'score': '미응시', 'max': '7'}), 'FAIL')
        self.assertEqual(vocab_status({'score': '', 'max': ''}), '')

    def test_monthly_spans_are_seven_days_and_stop_at_the_period_end(self):
        spans = sources.card_spans(date(2026, 9, 26), date(2026, 10, 10))
        self.assertEqual(spans[0], (date(2026, 9, 26), date(2026, 10, 3)))
        self.assertEqual(spans[2], (date(2026, 10, 10), date(2026, 10, 11)))
        self.assertEqual(spans[3], (None, None))


class TaLearningSpaceTests(ReportFixture):
    def setUp(self):
        super().setUp()
        U = get_user_model()
        self.ta_user = U.objects.create_user('ta_learn', password='x', role='TA')
        GroupStaff.objects.create(group=self.group, user=self.ta_user, duty='TA')
        self.elsewhere = LearningGroup.objects.create(title='다른 반', created_by=self.other_teacher)
        self.client.force_login(self.ta_user)

    def test_ta_opens_only_assigned_classes(self):
        self.assertEqual(self.client.get(reverse('lms:room', args=[self.group.pk])).status_code, 200)
        self.assertIn(self.client.get(reverse('lms:room', args=[self.elsewhere.pk])).status_code, (403, 404))

    def test_ta_menu_has_the_learning_space(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        nav = html.split('<nav class="intranet-side-navigation"', 1)[1].split('</nav>', 1)[0]
        self.assertIn(f'href="{reverse("lms:rooms")}"', nav)

    def test_ta_can_open_the_assignment_upload_form(self):
        response = self.client.get(reverse('assignments:create'))
        self.assertEqual(response.status_code, 200)
        groups = list(response.context['form'].fields['group'].queryset)
        self.assertEqual(groups, [self.group])


@override_settings(STUDENT_DATA_SOURCE='demo')
class FirstSetupTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_user('fs_admin', password='test-1234', role='ADMIN')
        self.client.force_login(self.admin)
        self.client.post(reverse('operations:user-create'), {
            'username': 'fs_student', 'display_name': '새학생', 'email': '', 'role': 'STUDENT', 'student_no': '6333',
            'password1': 'Temp-pass-9876', 'password2': 'Temp-pass-9876'})
        self.student = U.objects.get(username='fs_student')

    def test_admin_made_student_must_finish_setup_first(self):
        self.assertTrue(self.student.needs_first_setup)
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('first-setup'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('lms:inbox-feed'), HTTP_ACCEPT='application/json').status_code, 403)

    def test_setup_changes_password_and_saves_email_and_dsg_id(self):
        self.client.force_login(self.student)
        r = self.client.post(reverse('first-setup'), {'new_password1': 'My-own-pass-2468', 'new_password2': 'My-own-pass-2468',
                                                      'email': 'kid@example.com', 'dsg_login_id': 'dsg_kid'})
        self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)
        self.student.refresh_from_db()
        self.assertFalse(self.student.needs_first_setup)
        self.assertTrue(self.student.check_password('My-own-pass-2468'))
        self.assertEqual((self.student.email, self.student.dsg_login_id), ('kid@example.com', 'dsg_kid'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_email_is_required_and_dsg_needs_an_id_or_the_none_box(self):
        self.client.force_login(self.student)
        r = self.client.post(reverse('first-setup'), {'new_password1': 'My-own-pass-2468', 'new_password2': 'My-own-pass-2468', 'email': ''})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form'].errors.get('email'))
        self.assertTrue(r.context['form'].errors.get('dsg_login_id'))
        r = self.client.post(reverse('first-setup'), {'new_password1': 'My-own-pass-2468', 'new_password2': 'My-own-pass-2468',
                                                      'email': 'kid@example.com', 'no_dsg': 'on'})
        self.assertEqual(r.status_code, 302)

    def test_admin_sync_list_shows_entries_until_marked_done(self):
        self.client.force_login(self.student)
        self.client.post(reverse('first-setup'), {'new_password1': 'My-own-pass-2468', 'new_password2': 'My-own-pass-2468',
                                                  'email': 'kid@example.com', 'dsg_login_id': 'dsg_kid'})
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('operations:intranet-sync')), 'dsg_kid')
        csv = self.client.get(reverse('operations:intranet-sync'), {'format': 'csv'}).content.decode('utf-8-sig')
        self.assertIn('kid@example.com', csv)
        self.client.post(reverse('operations:intranet-sync'), {'user': [self.student.pk]})
        self.assertNotContains(self.client.get(reverse('operations:intranet-sync')), 'dsg_kid')

    def test_existing_accounts_are_not_forced(self):
        U = get_user_model()
        old = U.objects.create_user('old_student', password='x', role='STUDENT')
        self.client.force_login(old)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
