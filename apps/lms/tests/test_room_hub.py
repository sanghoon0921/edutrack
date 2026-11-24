"""반 하나에 모으기(운영팀 요청 10.29): 반 화면 탭, 관리자·강사 메뉴 정리, 반 목록 Term·강사 필터, 공지사항은 전체 공지 + 반별 공지 묶음."""
import re
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.communications.models import Notice
from apps.learning.models import Discussion, DiscussionRecipient, LearningGroup
from apps.lms.models import ClassPost
from apps.lms.tests.test_lms import LmsFixture


def sidebar(html):
    return html.split('<nav class="intranet-side-navigation"', 1)[1].split('</nav>', 1)[0]


class RoomTabTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.discussion = Discussion.objects.create(title='토론 주제', content='의견을 쓰세요', group=self.group, created_by=self.teacher,
                                                    due_at=timezone.now() + timedelta(days=2))
        DiscussionRecipient.objects.create(discussion=self.discussion, student_id='6333', student_name='학생 A')
        ClassPost.objects.create(group=self.group, kind='NOTICE', title='반 공지 글', body='내일 휴강', created_by=self.teacher)
        ClassPost.objects.create(group=self.group, kind='FILE', title='수업 자료 글', body='교재', created_by=self.teacher)
        self.url = reverse('lms:room', args=[self.group.pk])

    def tab(self, name, user=None):
        self.login(user)
        return self.client.get(self.url, {'tab': name}).content.decode()

    def test_room_has_tabs_for_everything_about_the_class(self):
        html = self.tab('')
        for name in ('assignments', 'discussions', 'quizzes', 'materials', 'notices'):
            self.assertIn(f'?tab={name}', html)
        self.assertIn(reverse('lms:gradebook') + f'?group={self.group.pk}', html)

    def test_each_tab_lists_its_own_kind(self):
        assignments = self.tab('assignments')
        self.assertIn('문학 과제', assignments)
        self.assertIn(reverse('assignments:create') + f'?group={self.group.pk}', assignments)
        self.assertNotIn('VOCAB 퀴즈', assignments)
        self.assertIn('VOCAB 퀴즈', self.tab('quizzes'))
        self.assertIn('토론 주제', self.tab('discussions'))
        materials = self.tab('materials')
        self.assertIn('수업 자료 글', materials)
        self.assertNotIn('반 공지 글', materials)
        self.assertIn(reverse('classroom:board-list'), materials)

    def test_notice_tab_shows_class_posts_and_class_notices(self):
        Notice.objects.create(title='반 전체 안내', content='반 공지사항', group=self.group, created_by=self.admin, is_published=True, published_at=timezone.now(), for_student=True)
        # 공지사항의 대상 규칙(학생·학부모·강사)은 그대로: 학생 대상 반 공지는 그 반 학생 화면에 보입니다.
        notices = self.tab('notices', self.student)
        self.assertIn('반 공지 글', notices)
        self.assertIn('반 전체 안내', notices)
        self.assertNotIn('수업 자료 글', notices)

    def test_students_see_only_their_own_activities(self):
        self.assertIn('문학 과제', self.tab('assignments', self.student))
        self.assertNotIn(reverse('assignments:create'), self.tab('assignments', self.student))


class StaffMenuTests(LmsFixture):
    def test_admin_and_teacher_menus_gather_learning_under_the_class(self):
        for user in (self.admin, self.teacher):
            self.login(user)
            nav = sidebar(self.client.get(reverse('dashboard')).content.decode())
            self.assertIn(reverse('lms:rooms'), nav)
            for name in ('assignments:list', 'classroom:board-list', 'lms:gradebook'):
                self.assertNotIn(f'href="{reverse(name)}"', nav)

    def test_learning_pages_light_up_the_class_menu(self):
        self.login(self.teacher)
        html = self.client.get(reverse('assignments:list')).content.decode()
        active = re.search(r'<a[^>]*aria-current="page"[^>]*>', sidebar(html))
        self.assertIsNotNone(active)
        self.assertIn(reverse('lms:rooms'), active.group(0))

    def test_student_menu_is_unchanged(self):
        self.login(self.student)
        nav = sidebar(self.client.get(reverse('dashboard')).content.decode())
        self.assertIn(reverse('lms:gradebook'), nav)
        self.assertIn(reverse('assignments:my'), nav)


class RoomListFilterTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.group.term = '26FW'
        self.group.save()
        self.winter = LearningGroup.objects.create(title='겨울 SAT반', term='2627WT', created_by=self.other_teacher)

    def titles(self, **query):
        self.login(self.admin)
        return self.client.get(reverse('lms:rooms'), query).content.decode()

    def listed(self, **query):
        # 11/19: 위쪽 '반 바로 가기' 드롭다운에는 모든 반이 있으므로, 거르기 결과는 표에서만 봅니다.
        html = self.titles(**query)
        return html.split('<tbody>', 1)[1].split('</tbody>', 1)[0] if '<tbody>' in html else html.split('u-room-jump', 1)[-1].split('</form>', 1)[-1]

    def test_filter_by_term(self):
        html = self.listed(term='2627WT')
        self.assertIn('겨울 SAT반', html)
        self.assertNotIn('QA 문학반', html)
        self.assertIn('<option value="26FW"', self.titles())

    def test_filter_by_teacher_includes_staffed_classes(self):
        html = self.listed(teacher=self.ta.pk)
        self.assertIn('QA 문학반', html)
        self.assertNotIn('겨울 SAT반', html)

    def test_group_form_saves_the_term(self):
        self.login(self.admin)
        # 11/20: Term 은 인트라넷 목록에서 고릅니다(데모 목록의 값).
        self.client.post(reverse('learning:group-update', args=[self.winter.pk]), {'title': '겨울 SAT반', 'description': '', 'sort_order': 0, 'term': '2026 가을 정규'})
        self.winter.refresh_from_db()
        self.assertEqual(self.winter.term, '2026 가을 정규')


class NoticeListTests(LmsFixture):
    def test_academy_notices_first_and_class_notices_grouped_below(self):
        Notice.objects.create(title='학원 전체 휴원 안내', content='전체', created_by=self.admin, is_published=True, published_at=timezone.now(), for_student=True)
        Notice.objects.create(title='문학반 보강 안내', content='반', group=self.group, created_by=self.admin, is_published=True, published_at=timezone.now(), for_student=True)
        self.login(self.student)
        html = self.client.get(reverse('communications:notice-list')).content.decode()
        main, _, classes = html.partition('data-class-notices')
        self.assertIn('학원 전체 휴원 안내', main)
        self.assertNotIn('문학반 보강 안내', main)
        self.assertIn('QA 문학반', classes)
        self.assertIn('문학반 보강 안내', classes)


class RoomHomeHintTests(LmsFixture):
    def test_home_hint_points_to_the_class_tabs_not_removed_menus(self):
        self.login(None)
        html = self.client.get(reverse('lms:room', args=[self.group.pk])).content.decode()
        self.assertNotIn('과제·퀴즈·토론 메뉴', html)  # 메뉴는 10/29 반 하나에 모으기로 없어졌습니다.
        self.assertIn('위 과제·퀴즈·토론 탭', html)
