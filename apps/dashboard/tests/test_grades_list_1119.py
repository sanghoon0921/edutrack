"""11/19 성적 분석: 학생관리처럼 학생 목록을 먼저 보여 주고, 반 고르기·이름/번호 검색·쪽 번호. 줄을 누르면 아래에 DSG 분석.
강사: 담당 지정 + 자기 반 학생, TA: 담당 반 학생, 관리자: 전체(모든 반 학생 + 담당 지정)."""
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember
from apps.lms.tests.test_lms import LmsFixture

User = get_user_model()


class GradesListTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.ta.role = User.Role.TA
        self.ta.save(update_fields=['role'])
        self.second = LearningGroup.objects.create(title='QA 수학반', created_by=self.teacher)
        GroupMember.objects.create(group=self.second, student_no='8201', student_name='박민준')

    def rows(self, user, **params):
        self.login(user)
        response = self.client.get(reverse('teacher_grades'), params)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        return html.split('<tbody>', 1)[1].split('</tbody>', 1)[0] if '<tbody>' in html else ''

    def test_grades_lists_class_members_and_assigned(self):
        body = self.rows(self.teacher)
        for no in ('6333', '7102', '8201'):
            self.assertIn(no, body)

    def test_group_filter_narrows_rows(self):
        body = self.rows(self.teacher, group=self.second.pk)
        self.assertIn('8201', body)
        self.assertNotIn('7102', body)

    def test_search_by_name_and_number(self):
        self.assertIn('8201', self.rows(self.teacher, q='박민'))
        self.assertNotIn('6333', self.rows(self.teacher, q='박민'))
        self.assertIn('7102', self.rows(self.teacher, q='7102'))

    def test_uses_shared_pager(self):
        for i in range(25):
            GroupMember.objects.create(group=self.second, student_no=f'95{i:02d}', student_name=f'가나다{i:02d}')
        self.login(self.teacher)
        html = self.client.get(reverse('teacher_grades')).content.decode()
        self.assertIn('class="et-pager"', html)

    def test_teacher_opens_class_member_insight(self):
        self.login(self.teacher)
        response = self.client.get(reverse('teacher_grades'), {'student_no': '8201'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse('assessments:student-insight', args=['8201'])).status_code, 200)

    def test_ta_sees_only_class_students(self):
        body = self.rows(self.ta)
        self.assertIn('6333', body)
        self.assertNotIn('8201', body)
        self.login(self.ta)
        self.assertIn(self.client.get(reverse('teacher_grades'), {'student_no': '8201'}).status_code, (403, 404))

    def test_class_dropdown_lists_only_visible_classes(self):
        self.login(self.ta)
        html = self.client.get(reverse('teacher_grades')).content.decode()
        self.assertIn(f'value="{self.group.pk}"', html)
        self.assertNotIn(f'value="{self.second.pk}"', html)
