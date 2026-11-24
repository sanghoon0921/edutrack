"""11/16 요청: 계정관리 화면 정리. 최근 변경 기록은 펼쳐 두지 않고 버튼을 눌렀을 때 작은 창으로 본다."""
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.operations.models import AccountAuditLog


class AccountDashboardTidyTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.admin = U.objects.create_user('acct_admin', password='test-1234', role='ADMIN')
        self.target = U.objects.create_user('acct_target', password='test-1234', role='TEACHER', display_name='대상 강사')
        AccountAuditLog.objects.create(actor=self.admin, target_user=self.target, action=AccountAuditLog.Action.USER_CREATED, summary='대상 강사 계정 생성')
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse('operations:dashboard')).content.decode()

    def test_recent_changes_sit_in_a_popup_opened_by_a_button(self):
        dialog = re.search(r'<(div|section)[^>]*id="recent-changes"[^>]*>', self.html)
        self.assertIsNotNone(dialog)
        self.assertIn('popover', dialog.group(0))
        self.assertIn('popovertarget="recent-changes"', self.html)
        self.assertIn('대상 강사 계정 생성', self.html)

    def test_recent_changes_are_not_an_always_open_panel(self):
        self.assertNotIn('operations-two-column', self.html)
        self.assertNotIn('operations-mini-list', self.html)

    def test_one_tidy_set_of_buttons_without_duplicates(self):
        self.assertEqual(self.html.count(f'href="{reverse("operations:user-create")}"'), 1)
        self.assertEqual(self.html.count(f'href="{reverse("operations:user-list")}"'), 1)
        self.assertNotIn('operations-action-grid', self.html)
        self.assertIn(reverse('operations:audit-list'), self.html)
        self.assertIn(reverse('data_imports:dashboard'), self.html)

    def test_numbers_stay(self):
        for label in ('사용 중 계정', '관리자', '강사', '학생', '학부모', '담당 학생 배정'):
            self.assertIn(label, self.html)
