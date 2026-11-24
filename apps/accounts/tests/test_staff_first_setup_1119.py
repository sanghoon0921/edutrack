"""11/19 계정: 직원(관리자·강사·TA) 첫 로그인은 비밀번호만 바꿉니다(8자 이상, 영문+숫자). 계정은 명령 하나로 만듭니다."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.forms import StaffFirstSetupForm
from apps.learning.models import LearningGroup
from apps.lms.models import GroupStaff

User = get_user_model()


class StaffFirstSetupTests(TestCase):
    def setUp(self):
        self.ta = User.objects.create_user('first_ta', password='1234', role=User.Role.TA, needs_first_setup=True)

    def test_staff_with_flag_sees_password_only_form(self):
        self.client.force_login(self.ta)
        html = self.client.get(reverse('first-setup')).content.decode()
        self.assertIn('new_password1', html)
        self.assertNotIn('name="email"', html)
        self.assertNotIn('name="dsg_login_id"', html)

    def test_staff_password_rule(self):
        def ok(pw):
            return StaffFirstSetupForm({'new_password1': pw, 'new_password2': pw}, user=self.ta).is_valid()
        self.assertTrue(ok('abcd1234'))
        self.assertFalse(ok('12345678'))
        self.assertFalse(ok('abcdefgh'))
        self.assertFalse(ok('a1b2'))
        self.assertFalse(ok('1234'))

    def test_staff_forced_change_blocks_other_pages(self):
        self.client.force_login(self.ta)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('first-setup'), fetch_redirect_response=False)

    def test_staff_change_clears_flag_without_touching_intranet_list(self):
        self.client.force_login(self.ta)
        response = self.client.post(reverse('first-setup'), {'new_password1': 'newpass99', 'new_password2': 'newpass99'})
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.ta.refresh_from_db()
        self.assertFalse(self.ta.needs_first_setup)
        self.assertTrue(self.ta.check_password('newpass99'))
        self.assertIsNone(self.ta.first_setup_at)


class EnsureStaffAccountCommandTests(TestCase):
    def test_command_creates_superuser_and_ta(self):
        owner = User.objects.create_user('group_owner', password='x', role=User.Role.TEACHER)
        group = LearningGroup.objects.create(title='[체험] SAT 정규반', created_by=owner)
        call_command('ensure_staff_account', 'sm', '--role', 'ADMIN', '--superuser', '--password', 'pw-test-1', stdout=StringIO())
        call_command('ensure_staff_account', 'TA', '--role', 'TA', '--password', 'pw-test-2', '--force-change', '--group', 'SAT 정규반', stdout=StringIO())
        sm = User.objects.get(username='sm')
        self.assertTrue(sm.is_superuser)
        self.assertEqual(sm.role, User.Role.ADMIN)
        self.assertTrue(sm.check_password('pw-test-1'))
        self.assertFalse(sm.needs_first_setup)
        ta = User.objects.get(username='TA')
        self.assertEqual(ta.role, User.Role.TA)
        self.assertTrue(ta.needs_first_setup)
        self.assertTrue(GroupStaff.objects.filter(group=group, user=ta, duty='TA', active=True).exists())

    def test_command_updates_existing_account(self):
        User.objects.create_user('sm', password='old-pw', role=User.Role.TEACHER)
        call_command('ensure_staff_account', 'sm', '--role', 'ADMIN', '--superuser', '--password', 'pw-test-3', stdout=StringIO())
        sm = User.objects.get(username='sm')
        self.assertEqual(sm.role, User.Role.ADMIN)
        self.assertTrue(sm.is_superuser and sm.is_staff)
        self.assertTrue(sm.check_password('pw-test-3'))
