"""메신저 대화방 이름 바꾸기(운영팀 요청 10.29): 관리자·강사만, 바뀐 이름은 학생·학부모 등 모두에게 보입니다."""
from django.urls import reverse

from apps.lms import rooms
from apps.lms.message_queries import conversation_name, serialize_summary, summary_queryset
from apps.lms.models import Conversation
from apps.lms.tests.test_lms import LmsFixture


class RenameTests(LmsFixture):
    def setUp(self):
        super().setUp()
        self.login(self.teacher)
        self.client.post(reverse('lms:new-conversation'), {'recipients': [self.student.pk, self.other.pk]})
        self.room = Conversation.objects.get(kind=Conversation.Kind.GROUP)
        self.url = reverse('lms:conversation-rename', args=[self.room.pk])

    def test_teacher_renames_a_group_chat_and_everyone_sees_it(self):
        response = self.client.post(self.url, {'title': '문학반 보강 상담방'})
        self.assertRedirects(response, reverse('lms:conversation', args=[self.room.pk]), fetch_redirect_response=False)
        self.room.refresh_from_db()
        for user in (self.teacher, self.student, self.other):
            self.assertEqual(conversation_name(self.room, user), '문학반 보강 상담방')
            self.login(user)
            self.assertContains(self.client.get(reverse('lms:inbox')), '문학반 보강 상담방')
        listed = summary_queryset(self.student).get(pk=self.room.pk)  # 작은 메신저 목록도 같은 이름
        self.assertEqual(serialize_summary(listed)['title'], '문학반 보강 상담방')

    def test_rename_box_is_shown_to_staff_only(self):
        page = self.client.get(reverse('lms:conversation', args=[self.room.pk]))
        self.assertContains(page, self.url)
        self.login(self.student)
        self.assertNotContains(self.client.get(reverse('lms:conversation', args=[self.room.pk])), self.url)

    def test_students_cannot_rename(self):
        self.login(self.student)
        self.assertEqual(self.client.post(self.url, {'title': '학생이 바꾼 이름'}).status_code, 403)
        self.room.refresh_from_db()
        self.assertEqual(self.room.custom_title, '')

    def test_blank_name_goes_back_to_the_automatic_name(self):
        self.client.post(self.url, {'title': '잠깐 이름'})
        self.client.post(self.url, {'title': '  '})
        self.room.refresh_from_db()
        self.assertEqual(self.room.custom_title, '')
        self.assertNotEqual(conversation_name(self.room, self.student), '잠깐 이름')

    def test_class_room_can_be_renamed_by_its_teacher(self):
        room = rooms.sync_class_room(self.group)
        self.client.post(reverse('lms:conversation-rename', args=[room.pk]), {'title': '문학반 공지방'})
        room.refresh_from_db()
        self.assertEqual(conversation_name(room, self.student), '문학반 공지방')

    def test_one_to_one_chats_keep_the_person_name(self):
        self.login(self.student)
        self.client.post(reverse('lms:new-conversation'), {'recipients': [self.teacher.pk]})
        direct = Conversation.objects.get(kind=Conversation.Kind.DIRECT)
        self.login(self.teacher)
        self.assertEqual(self.client.post(reverse('lms:conversation-rename', args=[direct.pk]), {'title': '이름'}).status_code, 404)
