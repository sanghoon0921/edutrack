"""11/19 TA 권한(사용자 결정 5가지). 담당 반 = 반별 학습 '명단·TA 지정'에서 지정된 반.

1. 담당 반 학생 정보  2. 그 학생들의 DSG  3. 반별 학습 전체 열람·게시(퀴즈·토론 포함)
4. 리포트카드(작업 3에서)  5. 메신저·공지(열람 + 담당 반 반 공지 작성)
"""
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.communications.models import Notice
from apps.learning.models import LearningGroup
from apps.lms.access import contacts_for
from apps.lms.tests.test_lms import LmsFixture

User = get_user_model()


class TaPermissionTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.ta.role = User.Role.TA
        self.ta.save(update_fields=['role'])
        self.other_group = LearningGroup.objects.create(title='다른 반', created_by=self.other_teacher)
        self.login(self.ta)

    def test_ta_opens_class_student_detail_and_insight(self):
        self.assertEqual(self.client.get(reverse('students:detail', args=['6333'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('assessments:student-insight', args=['6333'])).status_code, 200)

    def test_ta_cannot_open_student_outside_classes(self):
        self.assertIn(self.client.get(reverse('students:detail', args=['8201'])).status_code, (403, 404))
        self.assertIn(self.client.get(reverse('assessments:student-insight', args=['8201'])).status_code, (403, 404))

    def test_ta_student_list_shows_only_class_students(self):
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('6333', html)
        self.assertNotIn('8201', html)

    def test_ta_can_create_quiz_and_discussion_for_own_class(self):
        for name in ('learning:quiz-create', 'learning:discussion-create'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
            groups = set(response.context['form'].fields['group'].queryset)
            self.assertIn(self.group, groups)
            self.assertNotIn(self.other_group, groups)
        self.assertEqual(self.client.get(reverse('learning:quiz-detail', args=[self.quiz.pk])).status_code, 200)

    def test_ta_menu_has_students_grades_messages_notices(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        for name in ('students:list', 'teacher_grades', 'lms:inbox', 'communications:notice-list', 'lms:rooms', 'reports:list'):
            self.assertIn(f'href="{reverse(name)}"', html, name)

    def test_ta_can_write_class_notice_for_own_class_only(self):
        response = self.client.get(reverse('communications:notice-create'))
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(set(form.fields['group'].queryset), {self.group})
        self.assertEqual([value for value, _ in form.fields['category'].choices if value], [Notice.Category.CLASS])
        ok = self.client.post(reverse('communications:notice-create'), {
            'title': 'TA 반 공지', 'content': '내일 과제 안내', 'category': Notice.Category.CLASS,
            'group': self.group.pk, 'audiences': ['STUDENT'], 'is_published': 'on'})
        self.assertEqual(ok.status_code, 302)
        self.assertTrue(Notice.objects.filter(title='TA 반 공지', group=self.group, created_by=self.ta).exists())
        bad = self.client.post(reverse('communications:notice-create'), {
            'title': 'TA 학원 공지', 'content': 'x', 'category': Notice.Category.ACADEMY, 'audiences': ['STUDENT']})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(Notice.objects.filter(title='TA 학원 공지').exists())

    def test_ta_contacts_are_class_students_and_class_teachers(self):
        contacts = set(contacts_for(self.ta))
        self.assertIn(self.student, contacts)
        self.assertIn(self.teacher, contacts)
        self.assertNotIn(self.other_teacher, contacts)

    def test_student_contacts_include_class_ta(self):
        self.assertIn(self.ta, set(contacts_for(self.student)))

    def test_ta_sees_no_group_management_link_on_learning_lists(self):
        for name in ('assignments:list', 'learning:quiz-list', 'learning:discussion-list'):
            html = self.client.get(reverse(name)).content.decode()
            self.assertNotIn(reverse('learning:group-manage'), html, name)

    def test_ta_student_list_has_no_teacher_assignment_button(self):
        html = self.client.get(reverse('students:list')).content.decode()
        self.assertNotIn(reverse('operations:teacher-student-assignment'), html)
