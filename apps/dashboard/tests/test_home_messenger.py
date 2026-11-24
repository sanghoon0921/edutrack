from dataclasses import replace
from datetime import datetime, timedelta, timezone as pytimezone
from uuid import uuid4
from unittest.mock import patch
from pathlib import Path
from django.conf import settings
from django.test import TestCase, SimpleTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User,StudentAccountLink
from apps.accounts.context_processors import navigation
from apps.assignments.models import Assignment,AssignmentRecipient,Submission
from apps.communications.models import Notice
from apps.learning.models import LearningGroup,Quiz,QuizRecipient,QuizAttempt
from apps.lms.models import RoomSettings,GroupMember,GroupStaff,ClassPost,Conversation,ConversationMember,Message
from apps.lms.access import can_converse
from apps.lms.message_queries import accessible_conversations,message_summary
from apps.students.contracts import CourseSummary,AttendanceRecord
from apps.dashboard.student_home import home_context,home_clock,safe_zoom_url,today_sessions,student_scope
from apps.communications.tests.audience_helpers import audience_flags

@override_settings(STUDENT_DATA_SOURCE='demo',ASSESSMENT_DATA_SOURCE='demo',CLASS_CATALOG_DATA_SOURCE='demo',ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
class HomeFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin=User.objects.create_user('hm_admin',password='QA-password',role='ADMIN')
        cls.teacher=User.objects.create_user('hm_teacher',password='QA-password',role='TEACHER')
        cls.student=User.objects.create_user('hm_student',password='QA-password',role='STUDENT',display_name='학습 학생')
        cls.other=User.objects.create_user('hm_other',password='QA-password',role='STUDENT')
        cls.parent=User.objects.create_user('hm_parent',password='QA-password',role='PARENT')
        cls.other_teacher=User.objects.create_user('hm_teacher_b',password='QA-password',role='TEACHER')
        for user,sid,rel in [(cls.student,'6333','SELF'),(cls.other,'7102','SELF'),(cls.parent,'6333','PARENT')]:
            StudentAccountLink.objects.create(user=user,student_no=sid,relationship=rel,is_primary=True,is_active=True)
        cls.group=LearningGroup.objects.create(title='학습 A반',created_by=cls.teacher)
        cls.other_group=LearningGroup.objects.create(title='비공개 B반',created_by=cls.other_teacher)
        GroupMember.objects.create(group=cls.group,student_no='6333',student_name='학습 학생')
        GroupMember.objects.create(group=cls.other_group,student_no='7102',student_name='다른 학생')
        RoomSettings.objects.create(group=cls.group,schedule='화·목 19시 (자유 입력)',zoom_url='https://us02web.zoom.us/j/123456?pwd=Test')
        RoomSettings.objects.create(group=cls.other_group,zoom_url='https://zoom.us/j/999999')
        cls.conv=Conversation.objects.create(title='수업 상담',created_by=cls.teacher)
        ConversationMember.objects.create(conversation=cls.conv,user=cls.student)
        ConversationMember.objects.create(conversation=cls.conv,user=cls.teacher)
        cls.group_conv=Conversation.objects.create(title='A반 대화',created_by=cls.teacher,group=cls.group)
        ConversationMember.objects.create(conversation=cls.group_conv,user=cls.student)
        ConversationMember.objects.create(conversation=cls.group_conv,user=cls.teacher)
    def home(self):
        self.client.force_login(self.student)
        return self.client.get(reverse('dashboard'))
    def make_assignment(self,title='오늘 과제',days=0,published=True,available=None,student_id='6333',done=False):
        _,beginning,_=home_clock()
        a=Assignment.objects.create(title=title,description='내용',group=self.group,created_by=self.teacher,
            due_at=beginning+timedelta(days=days,hours=23),is_published=published,available_from=available)
        r=AssignmentRecipient.objects.create(assignment=a,student_id=student_id,student_name='학생')
        if done:Submission.objects.create(recipient=r,text_answer='답안',submitted_at=timezone.now())
        return a,r

class NavigationHomeTests(HomeFixture):
    def test_home_label_all_roles(self):
        for user in [self.admin,self.teacher,self.student,self.parent]:
            self.client.force_login(user);r=self.client.get(reverse('dashboard'))
            self.assertContains(r,'EduTrack 홈');self.assertNotContains(r,'대시보드')
    def test_settings_last_and_existing_operations_route(self):
        self.client.force_login(self.admin);r=self.client.get(reverse('dashboard'))
        tree=r.context['sidebar_navigation'];self.assertEqual(tree[-1]['label'],'설정')
        self.assertEqual(tree[-1]['children'][0]['label'],'계정관리');self.assertEqual(tree[-1]['children'][0]['url_name'],'operations:dashboard')
    def test_messenger_has_message_and_notice_children(self):
        for user in [self.admin,self.teacher,self.student]:
            self.client.force_login(user);r=self.client.get(reverse('dashboard'))
            section=next(x for x in r.context['sidebar_navigation'] if x.get('key')=='messenger')
            self.assertEqual([x['label'] for x in section['children']],['메시지','공지사항'])
    def test_parent_no_new_message_permission(self):
        self.client.force_login(self.parent);r=self.client.get(reverse('dashboard'))
        section=next(x for x in r.context['sidebar_navigation'] if x.get('key')=='messenger')
        self.assertEqual([x['label'] for x in section['children']],['공지사항'])
        self.assertEqual(self.client.get(reverse('lms:inbox-feed')).status_code,403)
    def test_settings_children_stay_admin_only(self):
        for user in [self.teacher,self.student,self.parent]:
            self.client.force_login(user);r=self.client.get(reverse('dashboard'))
            self.assertFalse(any(x.get('key')=='settings' for x in r.context['sidebar_navigation']))
            self.assertEqual(self.client.get(reverse('operations:dashboard')).status_code,403)
    def test_account_page_keeps_controls(self):
        self.client.force_login(self.admin);r=self.client.get(reverse('operations:dashboard'))
        for v in ['계정관리','담당 학생 배정',reverse('operations:user-list'),reverse('data_imports:dashboard'),reverse('operations:audit-list')]:self.assertContains(r,v)
    def test_message_active_submenu(self):
        self.client.force_login(self.student);r=self.client.get(reverse('lms:conversation',args=[self.conv.pk]))
        section=next(x for x in r.context['sidebar_navigation'] if x.get('key')=='messenger')
        self.assertTrue(section['children'][0]['is_active']);self.assertFalse(section['children'][1]['is_active'])
    def test_flat_nav_contract_unchanged(self):
        r=self.home()
        self.assertTrue(all('url_name' in x for x in r.context['role_navigation']))
    def test_student_home_has_requested_panels(self):
        r=self.home()
        for v in ['오늘 일정','공지사항','Zoom 바로 입장','메시지','오늘 마감','Asia/Seoul']:self.assertContains(r,v)
    def test_initial_home_never_calls_external_db(self):
        with patch('apps.dashboard.student_home.CourseService',side_effect=AssertionError('external')),patch('apps.dashboard.student_home.AttendanceService',side_effect=AssertionError('external')):
            self.assertEqual(self.home().status_code,200)
    def test_only_current_room_zoom_visible(self):
        r=self.home();self.assertContains(r,'us02web.zoom.us');self.assertNotContains(r,'999999');self.assertNotContains(r,'비공개 B반')
    def test_room_revocation_removes_home_content(self):
        GroupMember.objects.filter(group=self.group).update(active=False)
        r=self.home();self.assertNotContains(r,'us02web.zoom.us')
    def test_unlinked_real_account_has_no_demo_inference(self):
        user=User.objects.create_user('student_test',role='STUDENT')
        with override_settings(STUDENT_DATA_SOURCE='intranet',STUDENT_TEST_STUDENT_ID='6333'):
            self.assertEqual(student_scope(user),[])
    def test_parent_relationship_not_used_for_student_home(self):
        StudentAccountLink.objects.filter(user=self.student).update(relationship='PARENT')
        self.assertEqual(student_scope(self.student),[])
    def test_notice_visibility_global_and_room(self):
        for title,audience in [('전체공개','ALL'),('학생공개','STUDENT'),('강사전용','TEACHER')]:
            Notice.objects.create(title=title,content='안내',**audience_flags(audience),is_published=True,created_by=self.teacher)
        for title,group,public in [('내반공개',self.group,True),('다른반공지',self.other_group,True),('초안공지',self.group,False)]:
            ClassPost.objects.create(title=title,kind='NOTICE',created_by=self.teacher,group=group,published=public)
        r=self.home()
        for t in ['전체공개','학생공개','내반공개']:self.assertContains(r,t)
        for t in ['강사전용','다른반공지','초안공지']:self.assertNotContains(r,t)
    def test_home_notices_do_not_auto_mark_read(self):
        from apps.communications.models import NoticeRead
        Notice.objects.create(title='안내',content='내용',is_published=True,created_by=self.teacher)
        self.home();self.assertFalse(NoticeRead.objects.exists())
    def test_due_scope_and_dates(self):
        self.make_assignment();self.make_assignment('내일과제',days=1);self.make_assignment('어제과제',days=-1)
        self.make_assignment('비공개과제',published=False);self.make_assignment('타인과제',student_id='7102')
        self.make_assignment('아직공개전',available=timezone.now()+timedelta(days=1))
        r=self.home();self.assertEqual(r.context['student_home']['due_count'],1)
        for t in ['내일과제','어제과제','비공개과제','타인과제','아직공개전']:self.assertNotContains(r,t)
    def test_completed_assignment_not_mislabelled_pending(self):
        self.make_assignment(done=True)
        r=self.home();self.assertTrue(r.context['student_home']['deadlines'][0]['done']);self.assertContains(r,'제출완료')
    def test_quiz_deadline_and_completed_state(self):
        _,beginning,_=home_clock();q=Quiz.objects.create(title='오늘 퀴즈',group=self.group,created_by=self.teacher,due_at=beginning+timedelta(hours=23))
        qr=QuizRecipient.objects.create(quiz=q,student_id='6333',student_name='학생')
        self.assertEqual(self.home().context['student_home']['due_count'],1)
        QuizAttempt.objects.create(recipient=qr,user=self.student,attempt_no=1,submitted_at=timezone.now())
        self.assertContains(self.home(),'응시완료')
    def test_schedule_endpoint_requires_student(self):
        for user in [self.admin,self.teacher,self.parent]:
            self.client.force_login(user);self.assertEqual(self.client.get(reverse('home-today')).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(reverse('home-today')).status_code,302)
    def test_schedule_failure_keeps_home_success(self):
        self.client.force_login(self.student)
        with patch('apps.dashboard.home_views.today_sessions',side_effect=RuntimeError('db secret')):
            r=self.client.get(reverse('home-today'));self.assertEqual(r.status_code,503);self.assertNotContains(r,'db secret',status_code=503)
            self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
    def test_schedule_is_no_store(self):
        self.client.force_login(self.student)
        with patch('apps.dashboard.home_views.today_sessions',return_value={'items':[]}):
            r=self.client.get(reverse('home-today'));self.assertIn('no-store',r['Cache-Control'])
    def test_other_student_get_parameter_not_used(self):
        self.client.force_login(self.student)
        with patch('apps.dashboard.home_views.today_sessions',return_value={'items':[]}) as service:
            self.client.get(reverse('home-today'),{'student_id':'7102'})
            self.assertEqual(service.call_args.args[0].pk,self.student.pk)

class ScheduleTests(HomeFixture):
    def run_schedule(self,records,now=None,zooms=None):
        day=home_clock(now)[0].date()
        course=CourseSummary(assign_id='11',class_id='21',class_name='실제 계획 수업',start_date=day,end_date=day,is_active=True,display_status='진행 중')
        with patch('apps.dashboard.student_home.CourseService') as cs,patch('apps.dashboard.student_home.AttendanceService') as ats,patch('apps.dashboard.student_home._zoom_for_lessons',return_value=zooms or {}):
            cs.return_value.get_student_courses.return_value=[course]
            ats.return_value.get_attendance_for_courses.return_value={'11':(records,None)}
            return today_sessions(self.student,now)
    def record(self,**kw):
        base={'assign_id':'11','lesson_id':'31','lesson_date':home_clock()[0].date(),'time_summary':'19:00–20:00','payment_code':'PAID'};base.update(kw);return AttendanceRecord(**base)
    def test_actual_day_records_only(self):
        day=home_clock()[0].date();r=self.run_schedule([self.record(),self.record(lesson_id='32',lesson_date=day+timedelta(days=1))]);self.assertEqual(len(r['items']),1)
    def test_duplicate_registration_rows_not_duplicated(self):
        r=self.run_schedule([self.record(),self.record()]);self.assertEqual(len(r['items']),1)
    def test_cancelled_no_join_button(self):
        r=self.run_schedule([self.record(is_class_cancelled=True)],zooms={('11','31'):'https://zoom.us/j/123'})
        self.assertEqual(r['items'][0]['label'],'휴강');self.assertEqual(r['items'][0]['zoom_url'],'')
    def test_refund_no_join(self):
        r=self.run_schedule([self.record(payment_code='REFUND')],zooms={('11','31'):'https://zoom.us/j/123'})
        self.assertEqual(r['items'][0]['state'],'cancelled')
    def test_carry_over_not_a_today_session(self):
        r=self.run_schedule([self.record(payment_code='CARRY_OVER')]);self.assertEqual(r['items'],[])
    def test_ongoing_and_finished_by_local_clock(self):
        day=home_clock()[0].date();now=timezone.make_aware(datetime.combine(day,datetime.min.time()))+timedelta(hours=19,minutes=30)
        r=self.run_schedule([self.record()],now=now);self.assertEqual(r['items'][0]['label'],'진행 중')
        r=self.run_schedule([self.record()],now=now+timedelta(hours=1));self.assertEqual(r['items'][0]['label'],'종료')
    def test_ambiguous_time_not_fabricated(self):
        r=self.run_schedule([self.record(time_summary='')]);self.assertEqual(r['items'][0]['label'],'시간 확인')
    def test_free_text_schedule_not_converted_to_today(self):
        r=self.run_schedule([]);self.assertEqual(r['items'],[])
    def test_timezone_boundary_is_seoul(self):
        instant=datetime(2026,10,11,16,tzinfo=pytimezone.utc)
        local,begin,end=home_clock(instant);self.assertEqual(str(local.date()),'2026-10-12');self.assertEqual((end-begin).total_seconds(),86400)

class SafeLinkTests(SimpleTestCase):
    def test_zoom_https_paths_allowed(self):
        for url in ['https://zoom.us/j/123?pwd=abc','https://us02web.zoom.us/j/123','https://zoom.com/j/123']:
            self.assertEqual(safe_zoom_url(url),url)
    def test_unsafe_urls_rejected(self):
        for url in ['javascript:alert(1)','//zoom.us/j/1','http://zoom.us/j/1','https://zoom.us.evil.com/j/1','https://zoom.us@evil.com','https://user@zoom.us/j/1','https://zoom.us:8000/j/1','https://zoom.us/\nabc','https://zoom.us\\@evil.com','https://example.com/']:
            with self.subTest(url=url):self.assertEqual(safe_zoom_url(url),'')

class MessageHomeTests(HomeFixture):
    def msg(self,conv=None,user=None,body='문의'):
        return Message.objects.create(conversation=conv or self.conv,sender=user or self.teacher,body=body)
    def test_accessible_queryset_matches_existing_permissions(self):
        for user in [self.admin,self.teacher,self.other_teacher,self.student,self.other,self.parent]:
            expected={c.pk for c in Conversation.objects.all() if can_converse(user,c)}
            self.assertEqual(set(accessible_conversations(user).values_list('pk',flat=True)),expected)
    def test_own_messages_not_unread(self):
        self.msg(user=self.student)
        self.assertEqual(message_summary(self.student)['unread_count'],0)
    def test_incoming_unread_and_home_preview_no_read_mutation(self):
        self.msg();r=self.home();self.assertEqual(r.context['student_home']['messages']['unread_count'],1)
        self.assertEqual(ConversationMember.objects.get(conversation=self.conv,user=self.student).last_read_id,0)
    def test_summary_and_feed_do_not_mark_seen(self):
        self.msg();self.client.force_login(self.student)
        self.client.get(reverse('lms:inbox-feed'));self.client.get(reverse('lms:conversation-feed',args=[self.conv.pk]))
        self.assertEqual(ConversationMember.objects.get(conversation=self.conv,user=self.student).last_read_id,0)
    def test_only_own_threads_in_summary(self):
        c=Conversation.objects.create(title='다른 학생 대화',created_by=self.other_teacher,group=self.other_group)
        ConversationMember.objects.create(conversation=c,user=self.other);ConversationMember.objects.create(conversation=c,user=self.other_teacher)
        self.msg(c,self.other_teacher,'타인정보')
        self.client.force_login(self.student);r=self.client.get(reverse('lms:inbox-feed'))
        self.assertNotIn('타인정보',r.content.decode())
    def test_revoked_relationship_removes_summary(self):
        self.msg();GroupMember.objects.filter(group=self.group).update(active=False)
        self.assertEqual(message_summary(self.student)['items'],[])
    def test_inactive_peer_cannot_leak_private_preview(self):
        self.teacher.is_active=False;self.teacher.save(update_fields=['is_active'])
        self.assertNotIn(self.conv.pk,list(accessible_conversations(self.student).values_list('pk',flat=True)))
    def test_read_ack_requires_post_and_csrf(self):
        self.client.force_login(self.student)
        url=reverse('lms:conversation-read',args=[self.conv.pk]);self.assertEqual(self.client.get(url).status_code,405)
        c=Client(enforce_csrf_checks=True);c.force_login(self.student);self.assertEqual(c.post(url,{'up_to':'1'}).status_code,403)
    def test_read_ack_monotonic_and_own_thread(self):
        m1=self.msg();m2=self.msg();foreign=self.msg(self.group_conv)
        self.client.force_login(self.student);url=reverse('lms:conversation-read',args=[self.conv.pk])
        self.assertEqual(self.client.post(url,{'up_to':m2.pk}).status_code,200)
        self.client.post(url,{'up_to':m1.pk})
        self.assertEqual(ConversationMember.objects.get(conversation=self.conv,user=self.student).last_read_id,m2.pk)
        self.assertEqual(self.client.post(url,{'up_to':foreign.pk}).status_code,400)
    def test_feed_pages_catch_up_without_dropping(self):
        Message.objects.bulk_create([Message(conversation=self.conv,sender=self.teacher,body=str(n)) for n in range(105)])
        self.client.force_login(self.student);url=reverse('lms:conversation-feed',args=[self.conv.pk]);a=self.client.get(url).json()
        self.assertEqual(len(a['messages']),100);self.assertTrue(a['has_more'])
        b=self.client.get(url,{'after':a['messages'][-1]['id']}).json();self.assertEqual(len(b['messages']),5);self.assertFalse(b['has_more'])
    def test_ajax_send_success_and_replay_idempotent(self):
        self.client.force_login(self.student);url=reverse('lms:conversation',args=[self.conv.pk]);token=str(uuid4())
        data={'body':'작성 답변','client_token':token}
        a=self.client.post(url,data,HTTP_ACCEPT='application/json');b=self.client.post(url,data,HTTP_ACCEPT='application/json')
        self.assertEqual(a.status_code,200);self.assertTrue(a.json()['ok']);self.assertEqual(a.json()['id'],b.json()['id'])
        self.assertEqual(Message.objects.filter(client_token=token).count(),1)
    def test_ajax_validation_error_not_html(self):
        self.client.force_login(self.student)
        r=self.client.post(reverse('lms:conversation',args=[self.conv.pk]),{'body':'','client_token':str(uuid4())},HTTP_ACCEPT='application/json')
        self.assertEqual(r.status_code,400);self.assertFalse(r.json()['ok'])
    def test_normal_post_still_redirects(self):
        self.client.force_login(self.student)
        r=self.client.post(reverse('lms:conversation',args=[self.conv.pk]),{'body':'답변','client_token':str(uuid4())});self.assertEqual(r.status_code,302)
    def test_send_after_revocation_blocked(self):
        GroupMember.objects.filter(group=self.group).update(active=False);self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('lms:conversation',args=[self.conv.pk]),{'body':'x','client_token':str(uuid4())},HTTP_ACCEPT='application/json').status_code,404)
    def test_huge_feed_cursor_rejected(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('lms:conversation-feed',args=[self.conv.pk]),{'after':'9'*100}).status_code,400)
    def test_message_json_never_cached(self):
        self.client.force_login(self.student)
        for url in [reverse('lms:inbox-feed'),reverse('lms:conversation-feed',args=[self.conv.pk])]:
            self.assertIn('no-store',self.client.get(url)['Cache-Control'])
    def test_five_second_assets_loaded_once(self):
        self.client.force_login(self.student)
        pages={reverse('dashboard'):'data-home-chat-list',reverse('lms:inbox'):'data-message-summary',reverse('lms:conversation',args=[self.conv.pk]):'data-message-summary'}
        for url,marker in pages.items():
            r=self.client.get(url);self.assertContains(r,'polling.js',count=1);self.assertContains(r,marker)
    def test_messages_summary_query_count_bounded(self):
        self.msg()
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as captured:message_summary(self.student)
        self.assertLessEqual(len(captured),12)

class PollingContractTests(SimpleTestCase):
    def test_poller_is_five_seconds_no_full_reload(self):
        source=(Path(settings.BASE_DIR)/'apps/lms/static/lms/js/polling.js').read_text()
        self.assertIn('INTERVAL = 15000',source);self.assertIn('AbortController',source);self.assertIn('visibilitychange',source)
        self.assertNotIn('setInterval(',source);self.assertNotIn('location.reload',source)
    def test_message_draft_and_scroll_contract(self):
        source=(Path(settings.BASE_DIR)/'apps/lms/static/lms/js/messages.js').read_text()
        for token in ['textarea.value===snapshot','atBottom()','client_token','textContent','has_more']:self.assertIn(token,source)
        self.assertNotIn('innerHTML',source)
