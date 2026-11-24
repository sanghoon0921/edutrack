"""11/19 반별 학습 '반 바로 가기': 첫 화면과 반 화면 머리에서 드롭다운으로 반을 고르면 바로 그 반으로."""
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.tests.test_lms import LmsFixture


class RoomJumpTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.other_group = LearningGroup.objects.create(title='남의 반', created_by=self.other_teacher)

    def test_rooms_page_has_jump_select_with_visible_groups_only(self):
        self.login(self.teacher)
        html = self.client.get(reverse('lms:rooms')).content.decode()
        self.assertIn('name="go"', html)
        jump = html.split('name="go"', 1)[1].split('</select>', 1)[0]
        self.assertIn(f'value="{self.group.pk}"', jump)
        self.assertNotIn(f'value="{self.other_group.pk}"', jump)

    def test_go_param_redirects_to_room(self):
        self.login(self.teacher)
        response = self.client.get(reverse('lms:rooms'), {'go': self.group.pk})
        self.assertRedirects(response, reverse('lms:room', args=[self.group.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('lms:rooms'), {'go': self.other_group.pk}).status_code, 404)

    def test_room_header_has_jump_select(self):
        self.login(self.student)
        html = self.client.get(reverse('lms:room', args=[self.group.pk])).content.decode()
        self.assertIn('name="go"', html)
        self.assertIn(f'value="{self.group.pk}" selected', html)
