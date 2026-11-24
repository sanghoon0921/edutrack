"""메신저: 1:1 방은 두 사람당 하나(카카오톡처럼 계속 쌓임), 반별 단체방 자동 생성·명단 맞춤, 새 학생은 들어온 뒤 대화만, 안 읽음 숫자."""
import json

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import StudentAccountLink
from apps.lms import rooms
from apps.lms.access import can_converse
from apps.lms.models import Conversation, ConversationMember, GroupMember, GroupStaff, Message
from apps.lms.tests.test_lms import LmsFixture


def send(conv, user, body):
    message = Message.objects.create(conversation=conv, sender=user, body=body)
    ConversationMember.objects.filter(conversation=conv, user=user).update(last_read_id=message.pk)
    return message


class DirectRoomTests(LmsFixture):
    def start(self, user, other):
        self.login(user)
        return self.client.post(reverse("lms:new-conversation"), {"recipients": [other.pk]})

    def test_one_room_per_pair_whoever_starts(self):
        first = self.start(self.teacher, self.student)
        again = self.start(self.teacher, self.student)
        back = self.start(self.student, self.teacher)
        self.assertEqual(first["Location"], again["Location"])
        self.assertEqual(first["Location"], back["Location"])
        room = Conversation.objects.get()
        self.assertEqual(room.kind, Conversation.Kind.DIRECT)
        self.assertEqual(room.direct_key, rooms.direct_key(self.teacher, self.student))

    def test_duplicate_old_rooms_merge_into_the_oldest(self):
        old = Conversation.objects.create(title="개인 대화", created_by=self.teacher)
        new = Conversation.objects.create(title="개인 대화", created_by=self.student)
        for conv in (old, new):
            ConversationMember.objects.bulk_create([ConversationMember(conversation=conv, user=self.teacher),
                                                    ConversationMember(conversation=conv, user=self.student)])
        first = send(old, self.teacher, "첫 대화")
        second = send(new, self.student, "두 번째 방")
        ConversationMember.objects.filter(conversation=new, user=self.teacher).update(last_read_id=second.pk)
        rooms.merge_duplicate_direct_rooms(Conversation, ConversationMember, Message)
        room = Conversation.objects.get()
        self.assertEqual(room.pk, old.pk)
        self.assertEqual(list(room.messages.values_list("body", flat=True)), ["첫 대화", "두 번째 방"])
        self.assertEqual(room.participants.get(user=self.teacher).last_read_id, second.pk)
        self.assertEqual(room.kind, Conversation.Kind.DIRECT)
        self.assertNotEqual(first.pk, second.pk)


class ClassRoomTests(LmsFixture):
    def member_names(self, room):
        return set(room.participants.values_list("user__username", flat=True))

    def test_class_room_holds_students_teacher_and_ta(self):
        room = rooms.sync_class_room(self.group)
        self.assertEqual(room.kind, Conversation.Kind.CLASS)
        self.assertEqual(self.member_names(room), {"qa_teacher", "qa_ta", "qa_student", "qa_other_student"})
        self.assertEqual(rooms.sync_class_room(self.group).pk, room.pk)

    def test_roster_changes_follow_automatically(self):
        room = rooms.sync_class_room(self.group)
        GroupMember.objects.filter(group=self.group, student_no="7102").update(active=False)
        member = GroupMember.objects.get(group=self.group, student_no="7102")
        member.save()
        self.assertNotIn("qa_other_student", self.member_names(room))
        self.assertFalse(can_converse(self.other, room))
        GroupStaff.objects.filter(pk=self.staff.pk).update(active=False)
        self.staff.refresh_from_db()
        self.staff.save()
        self.assertNotIn("qa_ta", self.member_names(room))

    def test_new_student_sees_only_what_comes_after_joining(self):
        room = rooms.sync_class_room(self.group)
        send(room, self.teacher, "입학 전 안내")
        newcomer = get_user_model().objects.create_user("qa_new_student", password="test-1234", role="STUDENT")
        StudentAccountLink.objects.create(user=newcomer, student_no="8201", relationship="SELF", is_active=True)
        GroupMember.objects.create(group=self.group, student_no="8201", student_name="학생 C")
        self.assertIn("qa_new_student", self.member_names(room))
        send(room, self.teacher, "환영합니다")
        self.login(newcomer)
        page = self.client.get(reverse("lms:conversation", args=[room.pk]))
        self.assertContains(page, "환영합니다")
        self.assertNotContains(page, "입학 전 안내")
        feed = self.client.get(reverse("lms:conversation-feed", args=[room.pk]), {"after": "0"}).json()
        self.assertEqual([m["body"] for m in feed["messages"]], ["환영합니다"])

    def test_inbox_lists_the_class_room_for_its_students(self):
        self.login(self.student)
        page = self.client.get(reverse("lms:inbox"))
        self.assertContains(page, "QA 문학반")
        self.assertContains(page, "단체방")
        self.assertTrue(Conversation.objects.filter(kind=Conversation.Kind.CLASS, group=self.group).exists())

    def test_class_page_opens_the_room(self):
        self.login(self.teacher)
        response = self.client.get(reverse("lms:class-chat", args=[self.group.pk]))
        room = Conversation.objects.get(kind=Conversation.Kind.CLASS, group=self.group)
        self.assertRedirects(response, reverse("lms:conversation", args=[room.pk]), fetch_redirect_response=False)
        self.login(self.other_teacher)
        self.assertEqual(self.client.get(reverse("lms:class-chat", args=[self.group.pk])).status_code, 404)

    def test_parents_stay_out(self):
        room = rooms.sync_class_room(self.group)
        self.assertNotIn("qa_parent", self.member_names(room))


class UnreadCountTests(LmsFixture):
    def test_own_message_shows_how_many_have_not_read_it(self):
        room = rooms.direct_room(self.teacher, self.student)
        message = send(room, self.teacher, "숙제 확인했니?")
        self.login(self.teacher)
        page = self.client.get(reverse("lms:conversation", args=[room.pk]))
        self.assertEqual(page.context["blocks"][0]["messages"][0]["unread"], 1)
        ConversationMember.objects.filter(conversation=room, user=self.student).update(last_read_id=message.pk)
        page = self.client.get(reverse("lms:conversation", args=[room.pk]))
        self.assertEqual(page.context["blocks"][0]["messages"][0]["unread"], 0)

    def test_feed_reports_read_marks_for_live_counts(self):
        room = rooms.sync_class_room(self.group)
        send(room, self.teacher, "모두 확인하세요")
        self.login(self.teacher)
        feed = self.client.get(reverse("lms:conversation-feed", args=[room.pk]), {"after": "0"}).json()
        self.assertEqual(feed["messages"][0]["unread"], 3)
        self.assertEqual(len(feed["read_marks"]), 3)

    def test_messages_are_grouped_by_day_and_sender(self):
        room = rooms.direct_room(self.teacher, self.student)
        for body in ["하나", "둘"]:
            send(room, self.teacher, body)
        send(room, self.student, "셋")
        self.login(self.student)
        blocks = self.client.get(reverse("lms:conversation", args=[room.pk])).context["blocks"]
        self.assertEqual(len(blocks), 1)
        runs = [(m["body"], m["first_in_run"], m["last_in_run"]) for m in blocks[0]["messages"]]
        self.assertEqual(runs, [("하나", True, False), ("둘", False, True), ("셋", True, True)])
        self.assertIn("요일", blocks[0]["label"])
        self.assertTrue(json.dumps(blocks[0]["label"]))


class ClassPageButtonTests(LmsFixture):
    def test_class_page_links_to_its_room_but_not_for_parents(self):
        url = reverse("lms:class-chat", args=[self.group.pk])
        self.login(self.student)
        self.assertContains(self.client.get(reverse("lms:room", args=[self.group.pk])), url)
        self.login(self.parent)
        self.assertNotContains(self.client.get(reverse("lms:room", args=[self.group.pk])), url)


class PickSeveralTests(LmsFixture):
    """새 대화: 여러 명 체크 + 검색. 강사·관리자가 두 명 이상 고르면 그룹 대화, 학생은 한 명만."""

    def start(self, user, *others):
        self.login(user)
        return self.client.post(reverse("lms:new-conversation"), {"recipients": [o.pk for o in others]})

    def test_staff_picking_several_people_starts_a_group_chat(self):
        response = self.start(self.teacher, self.student, self.other)
        room = Conversation.objects.get()
        self.assertRedirects(response, reverse("lms:conversation", args=[room.pk]), fetch_redirect_response=False)
        self.assertEqual(room.kind, Conversation.Kind.GROUP)
        self.assertIsNone(room.group_id)
        self.assertEqual(room.participants.count(), 3)
        self.assertEqual(self.start(self.teacher, self.other, self.student)["Location"], response["Location"])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_everyone_in_the_group_chat_can_open_it_and_others_cannot(self):
        self.start(self.teacher, self.student, self.other)
        room = Conversation.objects.get()
        for user in (self.teacher, self.student, self.other):
            with self.subTest(user=user.username):
                self.assertTrue(can_converse(user, room))
                self.login(user)
                self.assertContains(self.client.get(reverse("lms:inbox")), reverse("lms:conversation", args=[room.pk]))
        for user in (self.other_teacher, self.parent, self.ta):
            with self.subTest(outsider=user.username):
                self.assertFalse(can_converse(user, room))

    def test_learners_start_only_one_to_one_chats(self):
        response = self.start(self.student, self.teacher, self.ta)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "학생은 한 명과만 대화를 시작할 수 있습니다")
        self.assertFalse(Conversation.objects.exists())

    def test_new_chat_page_is_a_searchable_checkbox_list(self):
        self.login(self.teacher)
        page = self.client.get(reverse("lms:new-conversation"))
        html = page.content.decode()
        self.assertIn(f'type="checkbox" name="recipients" value="{self.student.pk}"', html)
        self.assertIn("data-chat-search", html)
        self.assertIn(self.student.chat_name, html)
        self.assertIn('type="checkbox" data-chat-pick-all', html)
        self.assertIn("전체 선택", html)


class MemberListTests(LmsFixture):
    def test_group_room_shows_its_members_right_away(self):
        room = rooms.sync_class_room(self.group)
        self.login(self.teacher)
        page = self.client.get(reverse("lms:conversation", args=[room.pk]))
        names = [m["name"] for m in page.context["members"]]
        self.assertIn(self.student.chat_name, names)
        self.assertIn(self.ta.chat_name, names)
        html = page.content.decode()
        bar = html[html.index("data-chat-members"):]
        self.assertIn(self.other.chat_name, bar[:4000])
        self.assertNotIn("<details class=\"ux-chat-people\"", html)

    def test_direct_room_has_no_member_bar(self):
        room = rooms.direct_room(self.teacher, self.student)
        self.login(self.teacher)
        self.assertNotContains(self.client.get(reverse("lms:conversation", args=[room.pk])), "data-chat-members")

    def test_small_messenger_gets_the_member_names_for_group_rooms(self):
        room = rooms.sync_class_room(self.group)
        self.login(self.student)
        data = self.client.get(reverse("lms:chat-snapshot", args=[room.pk])).json()
        self.assertIn(self.teacher.chat_name, data["members"])
        direct = rooms.direct_room(self.teacher, self.student)
        self.assertEqual(self.client.get(reverse("lms:chat-snapshot", args=[direct.pk])).json()["members"], [])
