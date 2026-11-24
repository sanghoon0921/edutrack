"""11/19 전체 화면 점검: 역할마다 보이는 링크가 실제로 열려야 합니다(누르면 '권한 없음'·'없는 페이지'가 뜨던 곳).

- 관리자: 메시지의 '반별 대화' 표에서 자기가 참여자가 아닌 반의 '단체방'을 누르면 404 → 참여자인 반에만 단추를 보입니다.
- TA: 학습 탭이 학생용 주소로 가서 403이던 것 → 강사용 목록으로(11/19 오후: TA도 퀴즈·토론 열람·게시). 그룹(반) 관리는 숨김.
- 학부모: 학생 상세의 '← 학생 목록'(403).
"""
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.models import GroupStaff
from apps.lms.tests.test_lms import LmsFixture

User = get_user_model()


class AdminClassChatLinkTests(LmsFixture):
    def test_admin_sees_room_button_only_for_rooms_they_belong_to(self):
        mine = LearningGroup.objects.create(title='관리자 개설 반', created_by=self.admin)
        self.login(self.admin)
        html = self.client.get(reverse('lms:inbox')).content.decode()
        self.assertIn(reverse('lms:class-chat', args=[mine.pk]), html)
        self.assertNotIn(reverse('lms:class-chat', args=[self.group.pk]), html)

    def test_teacher_still_sees_room_button_for_own_class(self):
        self.login(self.teacher)
        html = self.client.get(reverse('lms:inbox')).content.decode()
        self.assertIn(reverse('lms:class-chat', args=[self.group.pk]), html)


class TaLinkTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.ta.role = User.Role.TA
        self.ta.save(update_fields=['role'])
        self.login(self.ta)

    def test_learning_tabs_point_to_staff_lists_and_hide_group_management(self):
        # 11/19 오후 TA 권한 결정: 반별 학습 전체(퀴즈·토론 포함) 열람·게시. 반 만들기(그룹 관리)는 관리자·강사만.
        html = self.client.get(reverse('assignments:list')).content.decode()
        self.assertNotIn(reverse('assignments:my'), html)
        self.assertIn(reverse('learning:quiz-list'), html)
        self.assertIn(reverse('learning:discussion-list'), html)
        self.assertNotIn(reverse('learning:group-manage'), html)

    def test_room_shows_quiz_and_discussion_create_and_detail_links(self):
        html = self.client.get(reverse('lms:room', args=[self.group.pk])).content.decode()
        self.assertIn(reverse('assignments:create'), html)
        self.assertIn(reverse('learning:quiz-create'), html)
        self.assertIn(reverse('learning:discussion-create'), html)
        self.assertIn(reverse('learning:quiz-detail', args=[self.quiz.pk]), html)

    def test_every_link_a_ta_sees_on_room_opens(self):
        import re
        html = self.client.get(reverse('lms:room', args=[self.group.pk])).content.decode()
        for href in set(re.findall(r'href="(/(?:learning|assignments)/[^"#?]*)', html)):
            self.assertNotIn(self.client.get(href).status_code, (403, 404), href)


class ParentStudentDetailLinkTests(LmsFixture):
    def test_parent_does_not_see_student_list_button(self):
        self.login(self.parent)
        html = self.client.get(reverse('students:detail', args=['6333'])).content.decode()
        self.assertNotIn(f'href="{reverse("students:list")}"', html)
