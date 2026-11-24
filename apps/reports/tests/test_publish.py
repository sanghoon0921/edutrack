"""리포트카드 공개(운영팀 요청 10.29): 반별 학생 목록, '공개' 버튼, 학생·학부모 리포트카드 메뉴, 알림."""
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import StudentAccountLink
from apps.communications.models import Notification
from apps.reports.models import ReportBatch
from apps.reports.tests.test_views import ReportFixture


class PublishFixture(ReportFixture):
    def setUp(self):
        super().setUp()
        self.parent = get_user_model().objects.create_user('rc_parent', password='x', role='PARENT')
        StudentAccountLink.objects.create(user=self.parent, student_no='6333', relationship='PARENT', is_active=True)
        self.other_student = get_user_model().objects.create_user('rc_student2', password='x', role='STUDENT')
        StudentAccountLink.objects.create(user=self.other_student, student_no='7102', relationship='SELF', is_active=True)
        self.create()
        self.batch = ReportBatch.objects.get()
        self.kim = self.batch.cards.get(student_no='6333')
        self.lee = self.batch.cards.get(student_no='7102')

    def publish(self):
        # 11/17: 공개(발송)는 관리자만
        self.client.force_login(self.admin)
        return self.client.post(reverse('reports:publish', args=[self.batch.pk]))

    def test_teachers_cannot_publish(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse('reports:publish', args=[self.batch.pk])).status_code, 404)
        self.batch.refresh_from_db()
        self.assertIsNone(self.batch.published_at)


class StudentListPageTests(PublishFixture):
    def test_opening_a_batch_lists_its_students_first(self):
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('reports:list')), reverse('reports:batch', args=[self.batch.pk]))
        page = self.client.get(reverse('reports:batch', args=[self.batch.pk]))
        self.assertContains(page, '김지훈')
        self.assertContains(page, '이서연')
        self.assertContains(page, reverse('reports:card', args=[self.batch.pk, self.lee.pk]))

    def test_card_page_links_back_to_the_student_list(self):
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse('reports:card', args=[self.batch.pk, self.kim.pk])),
                            reverse('reports:batch', args=[self.batch.pk]))

    def test_other_teacher_cannot_open_the_list(self):
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(reverse('reports:batch', args=[self.batch.pk])).status_code, 404)


class PublishTests(PublishFixture):
    def test_nothing_is_visible_before_publishing(self):
        self.client.force_login(self.student)
        self.assertNotContains(self.client.get(reverse('reports:my')), self.batch.title)
        self.assertEqual(self.client.get(reverse('reports:my-card', args=[self.kim.pk])).status_code, 404)

    def test_publish_shows_cards_to_the_student_and_parent_and_notifies_them(self):
        response = self.publish()
        self.assertRedirects(response, reverse('reports:batch', args=[self.batch.pk]), fetch_redirect_response=False)
        self.batch.refresh_from_db()
        self.assertIsNotNone(self.batch.published_at)

        for user in (self.student, self.parent):
            self.client.force_login(user)
            page = self.client.get(reverse('reports:my'))
            self.assertContains(page, 'AP Psychology (일)')
            self.assertContains(page, reverse('reports:my-card', args=[self.kim.pk]))
            self.assertNotContains(page, reverse('reports:my-card', args=[self.lee.pk]))
            card = self.client.get(reverse('reports:my-card', args=[self.kim.pk]))
            self.assertContains(card, 'AP REPORT CARD')
            self.assertContains(card, 'PDF')
            self.assertNotContains(card, 'name="d.comment"')
            note = Notification.objects.get(user=user, event_key__startswith='report:')
            self.assertEqual(note.title, '리포트카드가 업데이트되었습니다')
            self.assertEqual(note.target_url, reverse('reports:my-card', args=[self.kim.pk]))

    def test_a_student_cannot_open_someone_elses_card(self):
        self.publish()
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('reports:my-card', args=[self.lee.pk])).status_code, 404)

    def test_unpublish_hides_it_again(self):
        self.publish()
        self.client.post(reverse('reports:unpublish', args=[self.batch.pk]))
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('reports:my-card', args=[self.kim.pk])).status_code, 404)

    def test_publishing_again_sends_a_fresh_notification(self):
        self.publish()
        Notification.objects.filter(user=self.student, event_key__startswith='report:').update(is_read=True)
        self.publish()
        self.assertEqual(Notification.objects.filter(user=self.student, event_key__startswith='report:', is_read=False).count(), 1)

    def test_students_cannot_publish(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('reports:publish', args=[self.batch.pk])).status_code, 404)

    def test_students_and_parents_have_a_report_card_menu(self):
        for user in (self.student, self.parent):
            self.client.force_login(user)
            self.assertContains(self.client.get(reverse('reports:my')), 'href="' + reverse('reports:my') + '"')
