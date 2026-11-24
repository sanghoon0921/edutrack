"""11/19 쪽 번호 통일: 어떤 목록은 '이전 1/3 다음', 어떤 목록은 번호 1~10이던 것을 한 모양(‹ 이전 · 1~10 · 다음 ›)으로."""
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from apps.dashboard.templatetags.pager_tags import page_block

User = get_user_model()


class PageBlockTests(TestCase):
    def test_first_block_is_one_to_ten(self):
        self.assertEqual(page_block(1, 25), list(range(1, 11)))

    def test_page_past_ten_shows_next_block(self):
        self.assertEqual(page_block(13, 25), list(range(11, 21)))

    def test_last_block_stops_at_last_page(self):
        self.assertEqual(page_block(21, 25), [21, 22, 23, 24, 25])

    def test_few_pages_show_all(self):
        self.assertEqual(page_block(2, 3), [1, 2, 3])


class PagerTagTests(TestCase):
    def render(self, url, number, total=95, per=10):
        request = RequestFactory().get(url)
        page = Paginator(range(total), per).get_page(number)
        return Template('{% load pager_tags %}{% pager page %}').render(Context({'request': request, 'page': page}))

    def test_keeps_other_filters_and_marks_current(self):
        html = self.render('/x/?q=kim&page=2', 2)
        self.assertIn('class="et-pager"', html)
        self.assertIn('href="?q=kim&amp;page=1"', html)
        self.assertIn('href="?q=kim&amp;page=3"', html)
        self.assertIn('<span class="et-pager-num is-current" aria-current="page">2</span>', html)
        self.assertIn('>10</a>', html)
        self.assertNotIn('>11<', html)

    def test_single_page_draws_nothing(self):
        self.assertEqual(self.render('/x/', 1, total=5).strip(), '')

    def test_first_page_has_disabled_previous(self):
        html = self.render('/x/', 1)
        self.assertIn('<span class="et-pager-step is-disabled" aria-disabled="true">‹ 이전</span>', html)


class PagerOnListsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='pager_admin', password='x', role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        for i in range(45):
            User.objects.create_user(username=f'pager_user_{i:02d}', password='x', role=User.Role.TEACHER)
        self.client.force_login(self.admin)

    def test_user_list_uses_shared_pager(self):
        response = self.client.get('/operations/users/?role=TEACHER')
        html = response.content.decode()
        self.assertIn('class="et-pager"', html)
        self.assertIn('role=TEACHER&amp;page=2', html)
        self.assertNotIn('operations-pagination', html)
