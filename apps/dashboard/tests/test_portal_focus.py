"""Read-only APIs, permissions, real-analysis routing and class lookup contracts."""
import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.test import Client, override_settings
from django.urls import reverse
from apps.lms.models import GroupMember
from django.utils import timezone
from django.db import OperationalError
from apps.accounts.models import User
from apps.operations.models import TeacherStudentAccess
from apps.lms.models import Message, Conversation, ConversationMember, ClassPost
from apps.lms.message_queries import summary_queryset
from apps.operations import class_student_search as cs
from apps.dashboard.class_catalog import TermSubjectOptions
from apps.dashboard.tests.test_home_messenger import HomeFixture


class PortalMessengerTests(HomeFixture):
    def setUp(self):
        self.client.force_login(self.student)
        self.url=reverse('lms:chat-summary')
        self.snap=reverse('lms:chat-snapshot',args=[self.conv.pk])
    def message(self,body='안녕하세요',sender=None):
        return Message.objects.create(conversation=self.conv,sender=sender or self.teacher,body=body,client_token=uuid4())
    def test_unread_at_top_home_and_summary(self):
        self.message();r=self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['chat_unread_count'],1);self.assertEqual(r.context['portal_unread_total'],1)
        self.assertContains(r,'data-portal-total');self.assertContains(r,'data-home-chat-list')
        self.assertEqual(self.client.get(self.url).json()['unread_count'],1)
    def test_snapshot_does_not_mark_read(self):
        self.message();self.client.get(self.snap)
        self.assertEqual(ConversationMember.objects.get(conversation=self.conv,user=self.student).last_read_id,0)
    def test_summary_does_not_mark_read(self):
        self.message();self.client.get(self.url)
        self.assertEqual(ConversationMember.objects.get(conversation=self.conv,user=self.student).last_read_id,0)
    def test_list_displays_peer_not_legacy_subject(self):
        self.message();r=self.client.get(self.url).json()
        item=next(i for i in r['items'] if i['id']==self.conv.pk)
        self.assertEqual(item['title'],self.teacher.effective_name);self.assertNotEqual(item['title'],self.conv.title)
        self.conv.refresh_from_db();self.assertEqual(self.conv.title,'수업 상담')
    def test_snapshot_group_title_uses_group_name(self):
        r=self.client.get(reverse('lms:chat-snapshot',args=[self.group_conv.pk])).json()
        self.assertEqual(r['title'],self.group.title+' · 그룹 대화')
    def test_own_message_not_unread(self):
        self.message(sender=self.student);self.assertEqual(self.client.get(self.url).json()['unread_count'],0)
    def test_regular_notification_and_chat_count_combined(self):
        self.message()
        with patch('apps.lms.portal_chat.visible_unread_notification_count',return_value=3):
            self.assertEqual(self.client.get(self.url).json()['total_unread'],4)
    def test_private_cache_headers(self):
        for url in [self.url,self.snap]:
            r=self.client.get(url);self.assertIn('no-store',r.headers['Cache-Control']);self.assertIn('private',r.headers['Cache-Control'])
    def test_snapshot_strict_cursor(self):
        for before in ['abc','-1','9'*19,'<script>']:
            self.assertEqual(self.client.get(self.snap,{'before':before}).status_code,400)
    def test_snapshot_paginates_without_duplicates(self):
        for n in range(65):self.message(str(n))
        a=self.client.get(self.snap).json();self.assertEqual(len(a['messages']),60)
        b=self.client.get(self.snap,{'before':a['before']}).json();self.assertEqual(len(b['messages']),5)
        self.assertFalse(set(i['id'] for i in a['messages']) & set(i['id'] for i in b['messages']))
        self.assertEqual(a['messages'][-1]['id'],a['last_id'])
    def test_read_only_after_explicit_ack(self):
        m=self.message();self.client.get(self.snap)
        r=self.client.post(reverse('lms:conversation-read',args=[self.conv.pk]),{'up_to':str(m.pk)})
        self.assertEqual(r.status_code,200);self.assertEqual(self.client.get(self.url).json()['unread_count'],0)
    def test_snapshot_other_student_hidden(self):
        self.client.force_login(self.other);self.assertEqual(self.client.get(self.snap).status_code,404)
    def test_parent_no_chat_permission(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(self.url).status_code,403);self.assertEqual(self.client.get(self.snap).status_code,404)
        self.assertNotContains(self.client.get(reverse('dashboard')),'data-chat-widget')
    def test_anonymous_redirected(self):
        self.client.logout()
        for url in [self.url,self.snap]:self.assertEqual(self.client.get(url).status_code,302)
    def test_revocation_immediately_hides_conversation(self):
        from apps.lms.models import GroupMember
        GroupMember.objects.filter(group=self.group).update(active=False)
        self.message();self.assertEqual(self.client.get(self.snap).status_code,404)
        self.assertEqual(self.client.get(self.url).json()['unread_count'],0)
    def test_preview_keeps_untrusted_body_as_data(self):
        self.message('<img src=x onerror=alert(1)>');r=self.client.get(self.snap).json()
        self.assertEqual(r['messages'][-1]['body'],'<img src=x onerror=alert(1)>')
    def test_new_conversation_does_not_require_subject(self):
        # 같은 상대와의 기존 1:1 대화는 다시 쓰므로(간편 등록 V1), 없는 상태에서 새로 만드는 경우를 본다.
        Conversation.objects.filter(pk=self.conv.pk).delete()
        r=self.client.post(reverse('lms:new-conversation'),{'recipients':[self.teacher.pk]})
        self.assertEqual(r.status_code,302)
        self.assertEqual(Conversation.objects.latest('pk').title,'개인 대화')
    def test_title_widget_is_hidden(self):
        r=self.client.get(reverse('lms:new-conversation'))
        visible=[name for name,field in r.context['form'].fields.items() if not field.widget.is_hidden]
        self.assertNotIn('title',visible)
    def test_ajax_send_idempotent_retry(self):
        url=reverse('lms:conversation',args=[self.conv.pk]);token=str(uuid4());data={'body':'한 번만','client_token':token}
        for _ in range(2):self.assertEqual(self.client.post(url,data,HTTP_ACCEPT='application/json').status_code,200)
        self.assertEqual(Message.objects.filter(client_token=token).count(),1)
    def test_ajax_send_csrf_required(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.student)
        self.assertEqual(client.post(reverse('lms:conversation',args=[self.conv.pk]),{'body':'x','client_token':str(uuid4())},HTTP_ACCEPT='application/json').status_code,403)
    def test_old_unread_is_in_notification_even_if_not_recent(self):
        self.message('old unread')
        for n in range(10):
            c=Conversation.objects.create(title=f'new {n}',created_by=self.student)
            ConversationMember.objects.create(conversation=c,user=self.student)
            ConversationMember.objects.create(conversation=c,user=self.teacher)
            Message.objects.create(conversation=c,sender=self.student,body='read',client_token=uuid4())
        r=self.client.get(self.url).json()
        self.assertNotIn(self.conv.pk,[i['id'] for i in r['items']])
        self.assertIn(self.conv.pk,[i['id'] for i in r['unread_items']])
    def test_summary_query_count_bounded(self):
        self.message()
        with self.assertNumQueries(5):
            # Summary rows+prefetch(+학생번호 표시용 student_links) and correlated visibility; no query per item.
            rows=list(summary_queryset(self.student)[:8])
        self.assertTrue(rows)


class PortalTeacherHomeTests(HomeFixture):
    def setUp(self):self.client.force_login(self.teacher)
    def test_requested_priority_panels_not_feature_placeholder(self):
        r=self.client.get(reverse('dashboard'))
        for v in ['공지사항','메시지','Zoom 바로 입장','담당 학생 지정','성적 분석']:self.assertContains(r,v)
        for v in ['담당 학생 바로 선택','현재 과정 중심','premium-dashboard-kpi','data-teacher-student-picker']:self.assertNotContains(r,v)
    def test_teacher_home_does_not_query_external_data(self):
        with patch('apps.students.services.StudentService.get_student',side_effect=AssertionError('external')):
            self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
    def test_teacher_home_only_their_group_notice(self):
        ClassPost.objects.create(group=self.group,created_by=self.teacher,kind='NOTICE',title='허용된공지',published=True)
        ClassPost.objects.create(group=self.other_group,created_by=self.other_teacher,kind='NOTICE',title='금지된공지',published=True)
        r=self.client.get(reverse('dashboard'));self.assertContains(r,'허용된공지');self.assertNotContains(r,'금지된공지')
    def test_home_single_global_message_script(self):
        r=self.client.get(reverse('dashboard')).content.decode()
        self.assertEqual(r.count('src="/static/lms/js/polling.js'),1)
        self.assertEqual(r.count('data-chat-widget'),1)
    def test_teacher_home_message_arrival_count(self):
        Message.objects.create(conversation=self.conv,sender=self.student,body='선생님',client_token=uuid4())
        r=self.client.get(reverse('dashboard'));self.assertEqual(r.context['teacher_home']['messages']['unread_count'],1)
    def test_teacher_no_group_empty_state_no_fake_success(self):
        self.client.force_login(self.other_teacher);r=self.client.get(reverse('dashboard'))
        self.assertContains(r,'참여 중인 대화가 없습니다.')
        self.assertNotContains(r,'인트라넷 연결 정상')


class PortalGradeHubTests(HomeFixture):
    def setUp(self):
        self.client.force_login(self.teacher);self.url=reverse('teacher_grades')
        TeacherStudentAccess.objects.create(teacher=self.teacher,student_no='6333',student_name='김지훈')
    def test_one_assigned_student_auto_selected_real_overview_template(self):
        r=self.client.get(self.url)
        self.assertEqual(r.status_code,200);self.assertEqual(r.context['selected_student_no'],'6333')
        self.assertTemplateUsed(r,'assessments/student_score_overview.html')
        self.assertContains(r,'누적 학습 분석');self.assertNotContains(r,'화면과 권한 구조가 준비되었습니다')
    def test_multiple_students_require_selection(self):
        TeacherStudentAccess.objects.create(teacher=self.teacher,student_no='7102',student_name='이서연')
        r=self.client.get(self.url);self.assertEqual(r.context['selected_student_no'],'');self.assertContains(r,'위 목록에서 학생 이름을 누르면')
    def test_search_by_student_number(self):
        r=self.client.get(self.url,{'q':'6333'});self.assertEqual(r.context['total'],1)
    def test_unassigned_student_404(self):
        self.assertEqual(self.client.get(self.url,{'student_no':'7102'}).status_code,404)
    def test_revoked_student_404(self):
        # 11/19: 강사는 담당 지정 + 자기 반 학생. 둘 다 끊기면 404
        TeacherStudentAccess.objects.filter(teacher=self.teacher).update(is_active=False)
        GroupMember.objects.filter(group=self.group,student_no='6333').update(active=False)
        self.assertEqual(self.client.get(self.url,{'student_no':'6333'}).status_code,404)
    def test_cross_role_access_blocked(self):
        for user in [self.student,self.parent]:
            self.client.force_login(user);self.assertEqual(self.client.get(self.url).status_code,403)
    def test_student_lookup_failure_not_blank_success(self):
        with patch('apps.dashboard.grade_hub.StudentService.get_student',side_effect=OperationalError('private db host')):
            r=self.client.get(self.url)
            self.assertContains(r,'학생 정보를 조회하지 못했습니다.');self.assertNotContains(r,'private db host')
    def test_missing_student_not_invented(self):
        with patch('apps.dashboard.grade_hub.StudentService.get_student',return_value=None):
            self.assertContains(self.client.get(self.url),'학생 원장 정보를 찾지 못했습니다.')
    def test_no_assignment_no_score_queries(self):
        TeacherStudentAccess.objects.filter(teacher=self.teacher).delete()
        GroupMember.objects.filter(group=self.group).update(active=False)
        with patch('apps.assessments.templatetags.assessment_tags.AssessmentService',side_effect=AssertionError('do not query')):
            self.assertContains(self.client.get(self.url),'볼 수 있는 학생이 없습니다.')


class ClassRosterSearchTests(HomeFixture):
    def setUp(self):self.client.force_login(self.teacher);self.url=reverse('operations:teacher-class-search')
    def test_class_name_only_search(self):
        d=self.client.get(self.url,{'q':'Advanced'}).json()
        self.assertTrue(d['ok']);self.assertEqual(d['total'],1);self.assertIn('Advanced',d['classes'][0]['title'])
    def test_class_filters_and_defaults(self):
        d=self.client.get(self.url).json();self.assertTrue(d['classes']);self.assertTrue(d['terms']);self.assertTrue(d['subjects'])
        item=d['classes'][0]
        result=self.client.get(self.url,{'term':item['term'],'subject':item['subject'],'status':item['status_code']}).json()
        self.assertGreater(result['total'],0)
    def test_bad_status_rejected(self):self.assertEqual(self.client.get(self.url,{'status':'xxx'}).status_code,400)
    def test_roster_marks_current_assignment(self):
        TeacherStudentAccess.objects.create(teacher=self.teacher,student_no='6333',student_name='김지훈')
        r=self.client.get(reverse('students:selector-browse'),{'mode':'teacher','source':'intranet','class_id':'201'}).json()
        self.assertTrue(next(i for i in r['results'] if i['student_id']=='6333')['assigned'])
    def test_querying_never_registers(self):
        self.client.get(self.url);self.client.get(reverse('students:selector-browse'),{'mode':'teacher','source':'intranet','class_id':'201'})
        self.assertFalse(TeacherStudentAccess.objects.filter(teacher=self.teacher).exists())
    def test_student_parent_admin_search_not_teacher(self):
        for user in [self.student,self.parent,self.admin]:
            self.client.force_login(user);self.assertEqual(self.client.get(self.url).status_code,403)
    def test_anonymous_search_401(self):self.client.logout();self.assertEqual(self.client.get(self.url).status_code,401)
    def test_get_only(self):self.assertEqual(self.client.post(self.url,{}).status_code,405)
    def test_connection_error_sanitized(self):
        with patch.object(cs,'search_classes',side_effect=OperationalError('secret password host')):
            r=self.client.get(self.url);self.assertEqual(r.status_code,503);self.assertNotIn('secret',r.content.decode())
    def test_readonly_cache_headers(self):self.assertIn('no-store',self.client.get(self.url).headers['Cache-Control'])
    def test_three_columns_visible_without_school_grade_filters(self):
        r=self.client.get(reverse('operations:teacher-student-assignment'))
        for v in ['① 수업 찾기','② 인트라넷 전체 학생','③ 현재 담당 학생','Term','Subject','수업명','전체선택']:self.assertContains(r,v)
        self.assertNotContains(r,'data-search-mode')
        self.assertNotContains(r,'name="school"');self.assertNotContains(r,'name="grade"')
