"""반 만들기(11/20 사용자): 만들면서 학생·수업(클래스)과 TA·공동 강사를 함께 넣고, Term 은 인트라넷 목록에서 고릅니다.

- 학생 고르기는 '명단·TA 지정'과 같은 화면(수업·반을 고르면 그 반 학생이 한 번에 나오고 모두 추가, 이름 검색으로 하나씩 넣고 빼기).
- TA 계정(역할 TA)도 담당자 목록에 나옵니다.
- 인트라넷 Term 목록을 못 불러오면 글자로 입력합니다. 수정 화면에서는 예전 값(예: 26FW)도 남깁니다.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from django.test import SimpleTestCase
from django.urls import reverse

from apps.dashboard.class_catalog import TermSubjectOptions
from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember, GroupStaff
from apps.lms.tests.test_lms import LmsFixture
from apps.reports.formats import season_heading

User = get_user_model()
URL = reverse('learning:group-manage')
TERMS = 'apps.learning.forms.term_subject_options'


class CreateWithRosterTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.ta_account = User.objects.create_user('qa_ta_role', password='x', role=User.Role.TA, display_name='조교 TA')
        self.login(self.admin)

    def post(self, **extra):
        data = {'title': '26FW SAT 새 반', 'term': '2026 가을 정규', 'description': '', 'sort_order': 0,
                'student_ids': '6333,7102', 'staff': [self.ta_account.pk], **extra}
        return self.client.post(URL, data)

    def test_page_has_student_picker_and_ta_accounts(self):
        page = self.client.get(URL)
        self.assertContains(page, 'name="student_ids"')
        self.assertContains(page, '검색된 학생 모두 추가')
        self.assertContains(page, '조교 TA')  # 역할 TA 계정도 목록에
        self.assertContains(page, 'name="staff"')

    def test_create_saves_students_and_ta_together(self):
        response = self.post()
        group = LearningGroup.objects.get(title='26FW SAT 새 반')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(group.term, '2026 가을 정규')
        self.assertEqual(set(GroupMember.objects.filter(group=group, active=True).values_list('student_no', flat=True)), {'6333', '7102'})
        self.assertTrue(GroupStaff.objects.filter(group=group, user=self.ta_account, active=True, duty='TA').exists())

    def test_create_without_students_still_works(self):
        self.post(student_ids='', staff=[])
        group = LearningGroup.objects.get(title='26FW SAT 새 반')
        self.assertFalse(group.lms_members.exists())

    def test_student_lookup_failure_makes_nothing(self):
        with mock.patch('apps.learning.services.StudentService.get_students', side_effect=OperationalError(2013, 'Lost connection')):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '만들지 않았습니다')
        self.assertFalse(LearningGroup.objects.filter(title='26FW SAT 새 반').exists())

    def test_teacher_cannot_add_students_outside_scope(self):
        self.login(self.teacher)  # 담당 학생은 6333 하나
        response = self.post(student_ids='6333,8201', staff=[])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LearningGroup.objects.filter(title='26FW SAT 새 반').exists())

    def test_teacher_creates_with_own_student(self):
        self.login(self.teacher)
        self.post(student_ids='6333', staff=[])
        group = LearningGroup.objects.get(title='26FW SAT 새 반')
        self.assertEqual(group.created_by, self.teacher)
        self.assertEqual(list(group.lms_members.values_list('student_no', flat=True)), ['6333'])


class TermChoiceTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.login(self.admin)

    def test_term_is_a_list_from_the_intranet(self):
        page = self.client.get(URL)
        self.assertContains(page, '<select name="term"')
        self.assertContains(page, '2026 가을 정규')

    def test_unknown_term_is_refused(self):
        response = self.client.post(URL, {'title': '반', 'term': '없는 학기', 'sort_order': 0, 'student_ids': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LearningGroup.objects.filter(title='반').exists())

    def test_falls_back_to_typing_when_list_unavailable(self):
        with mock.patch(TERMS, return_value=TermSubjectOptions((), (), False)):
            page = self.client.get(URL)
            self.assertContains(page, '<input type="text" name="term"')
            self.client.post(URL, {'title': '직접 입력 반', 'term': '26FW', 'sort_order': 0, 'student_ids': ''})
        self.assertEqual(LearningGroup.objects.get(title='직접 입력 반').term, '26FW')

    def test_edit_keeps_old_code_term(self):
        self.group.term = '26FW'
        self.group.save()
        page = self.client.get(reverse('learning:group-update', args=[self.group.pk]))
        self.assertContains(page, '26FW (기존 값)')


class SeasonHeadingTests(SimpleTestCase):
    def test_intranet_term_names_become_report_headings(self):
        self.assertEqual(season_heading('2026 가을 정규'), '2026 FALL / WINTER')
        self.assertEqual(season_heading('2026 여름특강'), '2026 SUMMER')
        self.assertEqual(season_heading('2026 봄학기'), '2026 SPRING')
        self.assertEqual(season_heading('2026 겨울 특강'), '2026 WINTER')
        self.assertEqual(season_heading('26FW'), '2026 FALL / WINTER')
        self.assertEqual(season_heading('기타 과정'), '기타 과정')
