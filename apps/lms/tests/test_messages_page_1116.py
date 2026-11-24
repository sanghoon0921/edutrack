"""11/16 요청: '메시지'를 누르면 작은 창 대신 메시지 페이지로 이동, 페이지에서 반·이름 검색, 반별 대화 시작, 인원 추가.

오른쪽 아래 둥근 버튼만 작은 메신저를 열고, 메시지 페이지 안에서는 그 버튼을 숨긴다.
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms import rooms
from apps.lms.models import Conversation, ConversationMember, GroupMember, Message
from apps.lms.tests.test_lms import LmsFixture


class LaunchOutsideWidget(HTMLParser):
    """작은 메신저 영역(#portal-messenger) 밖에서 data-chat-launch 가 붙은 링크·버튼을 모은다."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__()
        self.stack, self.found = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        inside = any(x.get('id') == 'portal-messenger' for _, x in self.stack) or a.get('id') == 'portal-messenger'
        if tag in ('a', 'button') and 'data-chat-launch' in a and not inside:
            self.found.append(a.get('href') or tag)
        if tag not in self.VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def fab_tag(html):
    match = re.search(r'<button[^>]*class="portal-chat-fab"[^>]*>', html)
    return match.group(0) if match else ''


class MessageLinksGoToPageTests(LmsFixture):
    def test_header_and_home_message_links_open_the_page_not_the_mini_window(self):
        self.login(self.teacher)
        html = self.client.get(reverse('dashboard')).content.decode()
        rule = LaunchOutsideWidget()
        rule.feed(html)
        self.assertEqual(rule.found, [])
        self.assertIn(f'class="portal-header-chat" href="{reverse("lms:inbox")}"', html)

    def test_widget_script_only_takes_over_clicks_inside_the_mini_window(self):
        js = (Path(settings.BASE_DIR) / 'apps/lms/static/lms/js/chat-widget.js').read_text(encoding='utf-8')
        self.assertIn('root.contains(element)', js)
        self.assertNotIn('href===root.dataset.inbox', js)

    def test_round_button_hidden_on_message_pages_and_shown_elsewhere(self):
        conv = rooms.direct_room(self.teacher, self.student)
        self.login(self.teacher)
        for url in [reverse('lms:inbox'), reverse('lms:conversation', args=[conv.pk]),
                    reverse('lms:new-conversation'), reverse('lms:conversation-members', args=[conv.pk])]:
            with self.subTest(url=url):
                self.assertIn(' hidden', fab_tag(self.client.get(url).content.decode()))
        self.assertNotIn(' hidden', fab_tag(self.client.get(reverse('dashboard')).content.decode()))

    def test_home_card_hint_no_longer_promises_a_small_window(self):
        self.login(self.teacher)
        self.assertNotContains(self.client.get(reverse('dashboard')), '작은 대화창이 열립니다')


class InboxSearchAndClassFilterTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.math = LearningGroup.objects.create(title='QA 수학반', created_by=self.teacher)
        GroupMember.objects.create(group=self.math, student_no='7102', student_name='학생 B')
        self.with_a = rooms.direct_room(self.teacher, self.student)
        self.with_b = rooms.direct_room(self.teacher, self.other)
        self.url_a = reverse('lms:conversation', args=[self.with_a.pk])
        self.url_b = reverse('lms:conversation', args=[self.with_b.pk])
        self.login(self.teacher)

    def test_name_search_narrows_the_list(self):
        r = self.client.get(reverse('lms:inbox'), {'q': '학생 A'})
        self.assertContains(r, self.url_a)
        self.assertNotContains(r, self.url_b)

    def test_class_filter_keeps_chats_of_that_class(self):
        r = self.client.get(reverse('lms:inbox'), {'group': self.math.pk})
        self.assertContains(r, self.url_b)
        self.assertNotContains(r, self.url_a)

    def test_class_dropdown_lists_my_classes(self):
        r = self.client.get(reverse('lms:inbox'))
        self.assertContains(r, 'name="group"')
        self.assertContains(r, 'QA 수학반')
        self.assertContains(r, 'QA 문학반')

    def test_live_refresh_uses_the_same_filters(self):
        data = self.client.get(reverse('lms:inbox-feed'), {'q': '학생 A'}).json()
        ids = {item['id'] for item in data['items']}
        self.assertIn(self.with_a.pk, ids)
        self.assertNotIn(self.with_b.pk, ids)

    def test_conversation_sidebar_keeps_the_filter(self):
        r = self.client.get(self.url_a, {'q': '학생 A'})
        self.assertContains(r, 'value="학생 A"')
        self.assertEqual([row['id'] for row in r.context['chat_rows'] if row['id'] == self.with_b.pk], [])

    def test_unknown_class_filter_is_ignored(self):
        r = self.client.get(reverse('lms:inbox'), {'group': 'abc'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.url_a)


class ClassStartActionTests(LmsFixture):
    def test_staff_see_class_room_and_pick_students_per_class(self):
        self.login(self.teacher)
        r = self.client.get(reverse('lms:inbox'))
        self.assertContains(r, reverse('lms:class-chat', args=[self.group.pk]))
        self.assertContains(r, f"{reverse('lms:new-conversation')}?group={self.group.pk}")

    def test_selected_class_shows_its_start_buttons_in_the_list(self):
        self.login(self.teacher)
        r = self.client.get(reverse('lms:inbox'), {'group': self.group.pk})
        self.assertContains(r, 'data-class-actions')

    def test_students_do_not_get_class_start_actions(self):
        self.login(self.student)
        r = self.client.get(reverse('lms:inbox'))
        self.assertNotContains(r, f"{reverse('lms:new-conversation')}?group=")
        self.assertNotContains(r, 'data-class-actions')


class AddMembersTests(LmsFixture):
    def group_chat(self):
        conv = Conversation.objects.create(title=self.group.title, kind=Conversation.Kind.GROUP, group=self.group, created_by=self.teacher)
        ConversationMember.objects.bulk_create([ConversationMember(conversation=conv, user=u) for u in (self.teacher, self.student)])
        return conv

    def url(self, conv):
        return reverse('lms:conversation-members', args=[conv.pk])

    def test_teacher_adds_a_student_who_sees_messages_from_now_on(self):
        conv = self.group_chat()
        before = Message.objects.create(conversation=conv, sender=self.teacher, body='초대 전 메시지', client_token=uuid4())
        self.login(self.teacher)
        r = self.client.post(self.url(conv), {'recipients': [self.other.pk]})
        self.assertRedirects(r, reverse('lms:conversation', args=[conv.pk]), fetch_redirect_response=False)
        member = ConversationMember.objects.get(conversation=conv, user=self.other)
        self.assertEqual(member.joined_after, before.pk)
        self.login(self.other)
        self.assertNotContains(self.client.get(reverse('lms:conversation', args=[conv.pk])), '초대 전 메시지')

    def test_inviting_into_a_one_to_one_chat_makes_a_new_group_chat(self):
        direct = rooms.direct_room(self.teacher, self.student)
        self.login(self.teacher)
        r = self.client.post(self.url(direct), {'recipients': [self.other.pk]})
        new = Conversation.objects.exclude(pk=direct.pk).get(kind=Conversation.Kind.GROUP)
        self.assertRedirects(r, reverse('lms:conversation', args=[new.pk]), fetch_redirect_response=False)
        self.assertEqual(set(new.participants.values_list('user_id', flat=True)), {self.teacher.pk, self.student.pk, self.other.pk})
        self.assertEqual(direct.participants.count(), 2)

    def test_class_room_people_come_from_the_roster(self):
        room = rooms.sync_class_room(self.group)
        self.login(self.teacher)
        r = self.client.get(self.url(room))
        self.assertRedirects(r, reverse('lms:roster', args=[self.group.pk]), fetch_redirect_response=False)

    def test_picker_lists_only_people_not_yet_in_the_chat(self):
        conv = self.group_chat()
        self.login(self.teacher)
        r = self.client.get(self.url(conv))
        choices = {u.pk for u in r.context['form'].fields['recipients'].queryset}
        self.assertIn(self.other.pk, choices)
        self.assertNotIn(self.student.pk, choices)
        self.assertNotIn(self.other_teacher.pk, choices)

    def test_people_outside_the_class_cannot_be_posted_in(self):
        conv = self.group_chat()
        self.login(self.teacher)
        r = self.client.post(self.url(conv), {'recipients': [self.other_teacher.pk]})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ConversationMember.objects.filter(conversation=conv, user=self.other_teacher).exists())

    def test_students_cannot_add_people(self):
        conv = self.group_chat()
        self.login(self.student)
        self.assertEqual(self.client.get(self.url(conv)).status_code, 403)
        self.assertEqual(self.client.post(self.url(conv), {'recipients': [self.other.pk]}).status_code, 403)

    def test_teacher_outside_the_chat_gets_not_found(self):
        conv = self.group_chat()
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(self.url(conv)).status_code, 404)

    def test_add_people_button_only_for_staff(self):
        conv = self.group_chat()
        self.login(self.teacher)
        self.assertContains(self.client.get(reverse('lms:conversation', args=[conv.pk])), self.url(conv))
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse('lms:conversation', args=[conv.pk])), self.url(conv))
