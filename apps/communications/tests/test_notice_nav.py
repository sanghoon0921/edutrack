"""11/10 요청: 왼쪽 메뉴 공지사항에 마우스를 올리거나 누르면 하위 '전체 공지'·'반 공지'가 펼쳐집니다."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


def sidebar(html):
    return html.split('<nav class="intranet-side-navigation"', 1)[1].split('</nav>', 1)[0]


class NoticeSubmenuTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('nav_admin', password='x', role='ADMIN')
        self.client.force_login(self.user)
        self.base = reverse('communications:notice-list')

    def test_notice_menu_has_academy_and_class_sub_links(self):
        nav = sidebar(self.client.get(reverse('dashboard')).content.decode())
        self.assertIn('data-nav-flyout', nav)
        self.assertIn(f'href="{self.base}?kind=academy"', nav)
        self.assertIn(f'href="{self.base}?kind=class"', nav)
        self.assertIn('전체 공지', nav)
        self.assertIn('반 공지', nav)
        self.assertIn('aria-expanded="false"', nav)  # 다른 화면에서는 접혀 있다가 마우스·누르기로 펼침

    def test_open_and_marks_the_current_kind_on_notice_pages(self):
        nav = sidebar(self.client.get(self.base, {'kind': 'class'}).content.decode())
        self.assertIn('aria-expanded="true"', nav)
        sub = nav.split(f'href="{self.base}?kind=class"', 1)[0].rsplit('<a', 1)[1]
        self.assertIn('is-active', sub)
