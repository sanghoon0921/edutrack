"""11/10 요청: 리포트카드 '열기'는 학생·학부모가 보는 것과 같은 읽기 전용 화면, 옆에 '수정'. 저장하면 보기 화면으로.
보기 화면에서는 코멘트 속 주소가 파란 링크가 됩니다."""
import re

from django.urls import reverse

from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class ViewModeTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.create()
        self.batch = ReportBatch.objects.get(group=self.group)
        self.first, self.second = list(self.batch.cards.order_by('student_name'))
        from django.utils import timezone
        self.first.data['comment'] = '참고 자료: https://example.com/vocab 를 보세요.'
        self.first.saved_at = timezone.now()  # 한 번 저장한(완성된) 카드
        self.first.save()
        self.client.force_login(self.teacher)

    def view_url(self, card):
        return reverse('reports:card-view', args=[self.batch.pk, card.pk])

    def edit_url(self, card):
        return reverse('reports:card', args=[self.batch.pk, card.pk])

    def test_student_list_opens_view_and_has_edit_next_to_it(self):
        html = self.client.get(reverse('reports:batch', args=[self.batch.pk])).content.decode()
        row = html.split(self.first.student_name, 1)[1].split('</tr>', 1)[0]
        self.assertIn(f'href="{self.view_url(self.first)}"', row)
        self.assertIn(f'href="{self.edit_url(self.first)}"', row)
        self.assertRegex(row, r'>\s*열기\s*<')
        self.assertRegex(row, r'>\s*수정\s*<')

    def test_view_is_read_only_with_edit_button_and_arrows(self):
        response = self.client.get(self.view_url(self.first))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertFalse(re.search(r'name="[ds]\.', html), '보기 화면에는 입력칸이 없어야 합니다')
        self.assertIn(f'href="{self.edit_url(self.first)}"', html)
        self.assertIn(f'href="{self.view_url(self.second)}"', html)  # 다음 학생도 보기 화면으로

    def test_view_turns_comment_urls_into_links(self):
        html = self.client.get(self.view_url(self.first)).content.decode()
        self.assertRegex(html, r'<a [^>]*href="https://example.com/vocab"[^>]*target="_blank"')

    def test_save_goes_to_the_report_list(self):
        # 11/19 사용자 요청: 저장하면 리포트카드 첫 목록으로
        response = self.client.post(self.edit_url(self.first), {'save': '1', 'd.comment': '수정한 코멘트'})
        self.assertRedirects(response, reverse('reports:list'), fetch_redirect_response=False)

    def test_save_and_next_keeps_editing_the_next_student(self):
        response = self.client.post(self.edit_url(self.first), {'next': '1', 'd.comment': '다음으로'})
        self.assertRedirects(response, self.edit_url(self.second), fetch_redirect_response=False)

    def test_last_student_save_and_next_goes_to_the_report_list(self):
        response = self.client.post(self.edit_url(self.second), {'next': '1', 'd.comment': '마지막'})
        self.assertRedirects(response, reverse('reports:list'), fetch_redirect_response=False)

    def test_other_teacher_cannot_open_view(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(self.view_url(self.first)).status_code, 404)

    def test_edit_screen_links_back_to_view(self):
        html = self.client.get(self.edit_url(self.first)).content.decode()
        self.assertIn(f'href="{self.view_url(self.first)}"', html)
