from __future__ import annotations
import json
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.db import OperationalError
from django.core.exceptions import ImproperlyConfigured
from apps.accounts.models import User
from apps.operations.models import TeacherStudentAccess, AccountAuditLog
from apps.operations import teacher_self_assignment as views
from apps.students.repositories import DEMO_STUDENTS

@override_settings(STUDENT_DATA_SOURCE='demo')
class TeacherAssignmentRepairTests(TestCase):
    def setUp(self):
        self.teacher=User.objects.create_user('repair_teacher',password='SafeTemporary!2026',role='TEACHER')
        self.other=User.objects.create_user('repair_teacher_other',password='SafeTemporary!2026',role='TEACHER')
        self.student=User.objects.create_user('repair_student',password='SafeTemporary!2026',role='STUDENT')
        self.parent=User.objects.create_user('repair_parent',password='SafeTemporary!2026',role='PARENT')
        self.client.force_login(self.teacher)
        self.page=reverse('operations:teacher-student-assignment')
        self.search=reverse('students:selector-browse')
        self.update=reverse('operations:teacher-student-assignment-update')

    def post(self,payload):
        return self.client.post(self.update,json.dumps(payload),content_type='application/json')

    def find(self,q):
        return self.client.get(self.search,{'mode':'teacher','q':q})

    def test_no_assignment_teacher_can_find_unassigned_student(self):
        p=self.find('7102').json()
        self.assertEqual(p['results'][0]['student_id'],'7102')
        self.assertFalse(p['results'][0]['assigned'])

    def test_native_get_form_renders_search_and_token(self):
        r=self.client.get(self.page,{'q':'7102'})
        for text in ['이서연','name="student_nos"','value="7102"','name="csrfmiddlewaretoken"','data-single-add','선택 추가']:
            self.assertContains(r,text)

    def test_native_add_redirect_and_persist(self):
        r=self.client.post(self.update,{'action':'add','student_nos':['7102'],'q':'이서연'})
        self.assertEqual(r.status_code,302)
        self.assertTrue(TeacherStudentAccess.objects.filter(teacher=self.teacher,student_no='7102',is_active=True).exists())
        self.assertContains(self.client.get(r.url),'이서연')

    def test_native_invalid_input_preserves_and_messages(self):
        r=self.client.post(self.update,{'action':'add','student_nos':[]},follow=True)
        self.assertContains(r,'추가하거나 제외할 학생을 선택해 주세요.')
        self.assertFalse(TeacherStudentAccess.objects.exists())

    def test_native_remove_preserves_record_and_other_teacher(self):
        a=TeacherStudentAccess.objects.create(teacher=self.teacher,student_no='7102',student_name='이서연')
        b=TeacherStudentAccess.objects.create(teacher=self.other,student_no='7102',student_name='이서연')
        r=self.client.post(self.update,{'action':'remove','student_nos':['7102']})
        self.assertEqual(r.status_code,302);a.refresh_from_db();b.refresh_from_db()
        self.assertFalse(a.is_active);self.assertTrue(b.is_active)

    def test_add_remove_add_same_search_student(self):
        for action in ['add','remove','add']:
            r=self.post({'action':action,'student_nos':['7102']});self.assertEqual(r.status_code,200)
            self.assertEqual(len(r.json()['assigned']),0 if action=='remove' else 1)
            p=self.find('7102').json();self.assertEqual(p['results'][0]['assigned'],action!='remove')
        self.assertEqual(TeacherStudentAccess.objects.count(),1)

    def test_repeated_add_is_idempotent_with_no_duplicate_audit(self):
        for _ in range(2):self.assertEqual(self.post({'action':'add','student_nos':['7102']}).status_code,200)
        self.assertEqual(TeacherStudentAccess.objects.count(),1)
        self.assertEqual(AccountAuditLog.objects.filter(action='TEACHER_STUDENT_ADDED').count(),1)

    def test_payload_cannot_assign_to_another_teacher(self):
        self.post({'action':'add','student_nos':['7102'],'teacher_id':self.other.pk,'user_id':self.other.pk})
        self.assertTrue(TeacherStudentAccess.objects.filter(teacher=self.teacher).exists())
        self.assertFalse(TeacherStudentAccess.objects.filter(teacher=self.other).exists())

    def test_non_object_json_is_400_not_500(self):
        for obj in [[],None,3,'x',True]:
            with self.subTest(obj=obj):self.assertEqual(self.post(obj).status_code,400)

    def test_invalid_student_numbers_rejected(self):
        for numbers in [[True],[None],[{}],[['7102']],['x'*51],['7102\x00'],[1.25],[''],['7102']*101]:
            with self.subTest(numbers=numbers):self.assertEqual(self.post({'action':'add','student_nos':numbers}).status_code,400)
        self.assertFalse(TeacherStudentAccess.objects.exists())

    def test_malformed_json_is_400(self):
        self.assertEqual(self.client.post(self.update,'{',content_type='application/json').status_code,400)

    def test_bulk_missing_causes_no_partial_add(self):
        r=self.post({'action':'add','student_nos':['7102','MISSING']})
        self.assertEqual(r.status_code,400);self.assertFalse(TeacherStudentAccess.objects.exists())

    def test_duplicates_normalized(self):
        r=self.post({'action':'add','student_nos':[' 7102 ',7102]})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['assigned_count'],1)

    def test_raw_repository_bypasses_negative_profile_cache(self):
        from config.cache_utils import safe_cache_set
        from apps.students.services import StudentService
        safe_cache_set(StudentService._cache_key('7102'),{'value':None},timeout=60)
        with self.captureOnCommitCallbacks(execute=True):
            r=self.post({'action':'add','student_nos':['7102']})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['assigned_count'],1)
        self.assertIsNotNone(StudentService().get_student('7102'))

    def test_atomic_rollback_on_second_add(self):
        original=views.add_teacher_student_access
        def fail(**kw):
            if kw['student_no']=='8201':raise OperationalError('test failure')
            return original(**kw)
        with patch.object(views,'add_teacher_student_access',side_effect=fail):
            r=self.post({'action':'add','student_nos':['7102','8201']})
        self.assertEqual(r.status_code,503);self.assertFalse(TeacherStudentAccess.objects.exists());self.assertFalse(AccountAuditLog.objects.exists())

    def test_search_connection_error_shown_not_empty_success(self):
        with patch('apps.students.bulk_selector.browse_students',side_effect=OperationalError('sensitive db detail')):
            r=self.find('7102')
            self.assertEqual(r.status_code,503);self.assertNotContains(r,'sensitive db detail',status_code=503)
        with patch.object(views.StudentService,'search_students',side_effect=OperationalError('sensitive db detail')):
            page=self.client.get(self.page,{'q':'7102'});self.assertContains(page,'학생 조회 연결을 확인하지 못했습니다.')

    def test_configuration_error_readable(self):
        with override_settings(STUDENT_DATA_SOURCE='invalid'):
            r=self.find('7102');self.assertEqual(r.status_code,503)

    def test_parent_student_cannot_assign(self):
        for user in [self.parent,self.student]:
            self.client.force_login(user)
            for method,url,data in [('get',self.page,{}),('get',self.search,{'mode':'teacher','q':'7102'}),('post',self.update,{'action':'add','student_nos':['7102']})]:
                self.assertEqual(getattr(self.client,method)(url,data).status_code,403)
        self.assertFalse(TeacherStudentAccess.objects.exists())

    def test_unauthenticated_search_redirects_to_login(self):
        self.client.logout();r=self.find('7102')
        self.assertEqual(r.status_code,302);self.assertIn(reverse('login'),r.url)

    def test_menu_has_explicit_assignment_link_teacher_only(self):
        r=self.client.get(reverse('dashboard'));self.assertContains(r,'담당 학생 지정')
        self.client.force_login(self.student);self.assertNotContains(self.client.get(reverse('dashboard')),'담당 학생 지정')

    def test_assigned_directory_explicit_registration_cta(self):
        r=self.client.get(reverse('students:list'))
        self.assertContains(r,'담당 학생 지정 · 학생 추가·제외')

    def test_csrf_protected_ajax_with_custom_cookie(self):
        with override_settings(CSRF_COOKIE_NAME='edutrack_local_preview_csrftoken'):
            c=Client(enforce_csrf_checks=True);c.force_login(self.teacher)
            import re
            r=c.get(self.page)
            token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.content.decode()).group(1)
            data=json.dumps({'action':'add','student_nos':['7102']})
            self.assertEqual(c.post(self.update,data,content_type='application/json').status_code,403)
            self.assertEqual(c.post(self.update,data,content_type='application/json',HTTP_X_CSRFTOKEN=token).status_code,200)

    def test_csrf_protected_native_form(self):
        import re
        c=Client(enforce_csrf_checks=True);c.force_login(self.teacher);r=c.get(self.page)
        token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',r.content.decode()).group(1)
        self.assertEqual(c.post(self.update,{'action':'add','student_nos':['7102'],'csrfmiddlewaretoken':token}).status_code,302)

    def test_no_cache_pages_and_search(self):
        for url,data in [(self.page,{}),(self.search,{'mode':'teacher','q':'7102'})]:
            self.assertIn('no-store',self.client.get(url,data).headers['Cache-Control'])

    def test_get_does_not_write(self):
        self.find('7102');self.client.get(self.page,{'q':'7102'})
        self.assertFalse(TeacherStudentAccess.objects.exists());self.assertFalse(AccountAuditLog.objects.exists())
