"""11/24 전체 점검 1단계: 로그인 시도 제한, 업로드 파일 로그인 필수, 비밀번호 8자, TA 학생 고르기, 첨삭 글자 주소, 매일 백업."""
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.learning.models import LearningGroup
from apps.lms.models import GroupMember, GroupStaff

User = get_user_model()


class LoginLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('limit_user', password='right-pass-2026', role='TEACHER')
        self.url = reverse('login')

    def attempt(self, password, username='limit_user'):
        return self.client.post(self.url, {'username': username, 'password': password})

    def test_five_wrong_passwords_lock_the_account_for_a_while(self):
        for _ in range(5):
            self.attempt('wrong')
        response = self.attempt('right-pass-2026')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, '잠시 후')

    def test_lock_ends_after_the_wait(self):
        for _ in range(5):
            self.attempt('wrong')
        later = datetime.now().timestamp() + 16 * 60
        with mock.patch('apps.accounts.login_limit.time.time', return_value=later):
            response = self.attempt('right-pass-2026')
        self.assertEqual(response.status_code, 302)

    def test_success_resets_the_count(self):
        for _ in range(4):
            self.attempt('wrong')
        self.assertEqual(self.attempt('right-pass-2026').status_code, 302)
        self.client.logout()
        for _ in range(4):
            self.attempt('wrong')
        self.assertEqual(self.attempt('right-pass-2026').status_code, 302)

    def test_other_accounts_are_not_locked(self):
        User.objects.create_user('other_user', password='other-pass-2026', role='TEACHER')
        for _ in range(5):
            self.attempt('wrong')
        self.assertEqual(self.attempt('other-pass-2026', username='other_user').status_code, 302)


class MediaLoginTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='media-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / 'classroom').mkdir()
        (self.tmp / 'classroom' / 'notes.txt').write_text('수업 자료', encoding='utf-8')
        self.override = override_settings(MEDIA_ROOT=self.tmp, SERVE_MEDIA=True, DEBUG=False)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_anonymous_cannot_open_uploaded_files(self):
        response = self.client.get('/media/classroom/notes.txt')
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_logged_in_user_can_open_them(self):
        self.client.force_login(User.objects.create_user('media_user', password='media-pass-2026', role='STUDENT'))
        response = self.client.get('/media/classroom/notes.txt')
        self.assertEqual(response.status_code, 200)


class PasswordRuleTests(SimpleTestCase):
    def test_short_or_digit_only_passwords_are_refused(self):
        for weak in ('1234', 'abc123', '12345678'):
            with self.assertRaises(ValidationError, msg=weak):
                validate_password(weak)

    def test_eight_characters_with_letters_pass(self):
        validate_password('edutrack24')


@override_settings(STUDENT_DATA_SOURCE='demo', CLASS_CATALOG_DATA_SOURCE='demo')
class TaStudentPickerTests(TestCase):
    def setUp(self):
        teacher = User.objects.create_user('pick_teacher', password='x-Pick!2026', role='TEACHER')
        self.ta = User.objects.create_user('pick_ta', password='x-Pick!2026', role=User.Role.TA)
        self.group = LearningGroup.objects.create(title='TA 반', created_by=teacher)
        GroupMember.objects.create(group=self.group, student_no='6333', student_name='김지훈')
        GroupStaff.objects.create(group=self.group, user=self.ta, duty='TA')
        other = LearningGroup.objects.create(title='남의 반', created_by=teacher)
        GroupMember.objects.create(group=other, student_no='7102', student_name='이서연')
        self.client.force_login(self.ta)

    def test_ta_can_list_options_and_students_of_own_classes(self):
        options = self.client.get(reverse('students:selector-options'), {'source': 'all'})
        self.assertEqual(options.status_code, 200)
        self.assertEqual([g['name'] for g in options.json()['groups']], ['TA 반'])
        rows = self.client.get(reverse('students:selector-browse'), {'mode': 'activity', 'source': 'all'})
        self.assertEqual(rows.status_code, 200)
        self.assertEqual([r['student_id'] for r in rows.json()['results']], ['6333'])

    def test_ta_still_cannot_use_teacher_assignment_mode(self):
        response = self.client.get(reverse('students:selector-browse'), {'mode': 'teacher'})
        self.assertEqual(response.status_code, 403)


class WordsUrlTests(SimpleTestCase):
    def test_first_document_keeps_its_number_in_the_words_address(self):
        from apps.lms.document_views import page_url_pattern
        pattern = page_url_pattern('lms:document-words', 1)
        self.assertEqual(pattern.replace('{page}', '3'), reverse('lms:document-words', args=[1, 3]))
        self.assertEqual(page_url_pattern('lms:document-words', 11).replace('{page}', '1'), reverse('lms:document-words', args=[11, 1]))


class DailyBackupTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='backup-test-'))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.db = self.root / 'db.sqlite3'
        con = sqlite3.connect(self.db)
        con.execute('create table t (x)')
        con.execute('insert into t values (1)')
        con.commit()
        con.close()
        self.media = self.root / 'media'
        (self.media / 'classroom').mkdir(parents=True)
        (self.media / 'classroom' / 'a.txt').write_text('자료', encoding='utf-8')

    def test_makes_one_db_and_media_copy_per_day(self):
        from config.db_backup import daily_backup
        day = datetime(2026, 11, 24, 3, 0)
        first = daily_backup(self.db, self.media, now=day)
        second = daily_backup(self.db, self.media, now=day + timedelta(hours=5))
        names = sorted(p.name for p in (self.root / 'backups').iterdir())
        self.assertEqual(names, ['daily-db-20261124.sqlite3', 'daily-media-20261124.zip'])
        self.assertTrue(first)
        self.assertFalse(second)
        copy = sqlite3.connect(self.root / 'backups' / 'daily-db-20261124.sqlite3')
        self.assertEqual(copy.execute('select x from t').fetchone(), (1,))
        copy.close()

    def test_keeps_fourteen_days_and_never_touches_other_backups(self):
        from config.db_backup import daily_backup
        backups = self.root / 'backups'
        backups.mkdir()
        (backups / 'db-20261001-090000.sqlite3').write_text('migrate 전 백업')
        for days in range(20):
            daily_backup(self.db, self.media, now=datetime(2026, 11, 1) + timedelta(days=days))
        dates = sorted(p.name[9:17] for p in backups.glob('daily-db-*'))
        self.assertEqual(len(dates), 14)
        self.assertEqual(dates[0], '20261107')
        self.assertTrue((backups / 'db-20261001-090000.sqlite3').exists())
