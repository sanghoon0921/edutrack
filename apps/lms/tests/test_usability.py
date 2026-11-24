"""New contracts. Existing business/security tests remain in the full suite."""
from datetime import timedelta, datetime, timezone as dtz
from dataclasses import replace
from html.parser import HTMLParser
from uuid import uuid4
from unittest.mock import patch, MagicMock
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase, Client, override_settings
from django.urls import reverse
from django.db import OperationalError
from django.utils import timezone
from apps.lms.tests.test_lms import LmsFixture
from apps.lms.models import Conversation, ConversationMember, Message, ClassPost, GroupMember
from apps.lms.forms import ConversationForm, PostForm
from apps.lms.message_queries import message_summary
from apps.assignments.forms import AssignmentForm
from apps.assignments.models import Assignment
from apps.learning.forms import DiscussionForm, QuizForm
from apps.communications.forms import NoticeForm
from apps.students import bulk_selector as bulk
from apps.students.repositories import DEMO_STUDENTS


class WidgetClickRule(HTMLParser):
    """chat-widget.js 의 문서 클릭 규칙을 흉내 내, 본문(<main>)에서 작은 대화창이 가로챌 링크를 모은다.

    가로채는 대상: data-conversation-id, data-chat-launch, 또는 메시지 목록 주소로 가는 링크·버튼.
    data-chat-page 가 붙은 요소(또는 그 안)는 가로채지 않는다.
    """
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','source','track','wbr'}
    def __init__(self,inbox):super().__init__();self.inbox,self.stack,self.hijacked=inbox,[],[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);chain=[x for _,x in self.stack]+[a]
        if tag in('a','button') and any(x.get('id')=='main-content' for x in chain) and not any('data-chat-page' in x for x in chain):
            if 'data-conversation-id' in a or 'data-chat-launch' in a or a.get('href')==self.inbox:self.hijacked.append(a.get('href'))
        if tag not in self.VOID:self.stack.append((tag,a))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:del self.stack[i:];break


class MessageUsabilityTests(LmsFixture):
    def direct(self):
        c=Conversation.objects.create(title='기존 메일 제목',created_by=self.teacher)
        ConversationMember.objects.bulk_create([ConversationMember(conversation=c,user=u) for u in [self.teacher,self.student]])
        return c
    def new(self,user=None,**extra):
        self.login(user or self.teacher)
        return self.client.post(reverse('lms:new-conversation'),{'recipients':[self.student.pk],**extra})
    def test_title_field_removed(self):self.assertNotIn('title',ConversationForm().fields)
    def test_no_title_required_to_start(self):
        r=self.new();self.assertEqual(r.status_code,302);self.assertEqual(Conversation.objects.count(),1)
    def test_direct_reuses_existing_history(self):
        c=self.direct();Message.objects.create(conversation=c,sender=self.student,body='기존 대화',client_token=uuid4())
        r=self.new();self.assertEqual(r.url,reverse('lms:conversation',args=[c.pk]));self.assertEqual(Conversation.objects.count(),1)
    def test_full_page_messenger_links_are_not_hijacked_by_widget(self):
        c=self.direct();self.login(self.teacher);inbox=reverse('lms:inbox')
        for url in [inbox,reverse('lms:conversation',args=[c.pk]),reverse('lms:new-conversation')]:
            r=self.client.get(url);self.assertContains(r,'data-chat-widget')
            rule=WidgetClickRule(inbox);rule.feed(r.content.decode());self.assertEqual(rule.hijacked,[],url)
    def test_existing_title_is_not_rewritten_or_shown(self):
        c=self.direct();self.login(self.student);r=self.client.get(reverse('lms:conversation',args=[c.pk]));self.assertEqual(r.status_code,200)
        self.assertNotContains(r,'기존 메일 제목');c.refresh_from_db();self.assertEqual(c.title,'기존 메일 제목')
    def test_summary_shows_peer_identity(self):
        self.direct();self.assertEqual(message_summary(self.teacher)['items'][0]['title'],self.student.chat_name)
        self.assertEqual(message_summary(self.student)['items'][0]['title'],self.teacher.effective_name)
    def test_duplicate_create_reuses_room(self):self.new();self.new();self.assertEqual(Conversation.objects.count(),1)
    def test_student_can_resume_from_other_side(self):
        c=self.direct();self.login(self.student);r=self.client.post(reverse('lms:new-conversation'),{'recipients':[self.teacher.pk]});self.assertEqual(r.url,reverse('lms:conversation',args=[c.pk]))
    def test_group_exact_participants_reuse(self):
        self.new(group=str(self.group.pk));self.new(group=str(self.group.pk));self.assertEqual(Conversation.objects.count(),1)
    def test_group_different_participants_create_separate(self):
        self.new(group=str(self.group.pk));self.login();self.client.post(reverse('lms:new-conversation'),{'group':self.group.pk,'recipients':[self.student.pk,self.other.pk]});self.assertEqual(Conversation.objects.count(),2)
    def test_no_unrelated_contact_in_new_form(self):
        self.login(self.other_teacher);r=self.client.get(reverse('lms:new-conversation'));self.assertNotIn(self.student,list(r.context['form'].fields['recipients'].queryset))
    def test_several_recipients_make_a_group_chat_for_staff(self):
        # 메신저에서 여러 명 선택: 관리자·강사가 두 명 이상 고르면 그룹 대화(반 없이)를 만듭니다.
        self.login(self.admin);r=self.client.post(reverse('lms:new-conversation'),{'recipients':[self.student.pk,self.other.pk]});self.assertEqual(r.status_code,302);self.assertEqual(Conversation.objects.get().participants.count(),3)
    def test_send_response_includes_saved_message(self):
        c=self.direct();self.login(self.teacher);r=self.client.post(reverse('lms:conversation',args=[c.pk]),{'body':'안녕\n다음 줄','client_token':uuid4()},HTTP_ACCEPT='application/json');self.assertEqual(r.status_code,200);self.assertEqual(r.json()['message']['body'],'안녕\n다음 줄');self.assertTrue(r.json()['message']['own'])
    def test_retry_same_token_different_text_rejected(self):
        c=self.direct();self.login();u=reverse('lms:conversation',args=[c.pk]);t=uuid4();a=self.client.post(u,{'body':'원래 메시지','client_token':t},HTTP_ACCEPT='application/json');b=self.client.post(u,{'body':'다른 내용','client_token':t},HTTP_ACCEPT='application/json');self.assertEqual(a.status_code,200);self.assertEqual(b.status_code,403);self.assertEqual(c.messages.get().body,'원래 메시지')
    def test_before_feed_sorted_and_bounded(self):
        c=self.direct();Message.objects.bulk_create([Message(conversation=c,sender=self.student,body=str(i),client_token=uuid4()) for i in range(120)])
        self.login();r=self.client.get(reverse('lms:conversation-feed',args=[c.pk]),{'before':c.messages.order_by('-pk').first().pk});self.assertEqual(r.status_code,200);m=r.json()['messages'];self.assertEqual(len(m),100);self.assertEqual([x['id'] for x in m],sorted(x['id'] for x in m));self.assertTrue(r.json()['older']);self.assertTrue(r.json()['has_more'])
    def test_before_feed_does_not_mark_read(self):
        c=self.direct();m=Message.objects.create(conversation=c,sender=self.student,body='x',client_token=uuid4());self.login();self.client.get(reverse('lms:conversation-feed',args=[c.pk]),{'before':m.pk+1});self.assertEqual(c.participants.get(user=self.teacher).last_read_id,0)
    def test_parent_denied_chat_start(self):self.login(self.parent);self.assertEqual(self.client.get(reverse('lms:new-conversation')).status_code,403)
    def test_title_payload_cannot_override_display(self):
        r=self.new(title='공격 제목');c=Conversation.objects.get();self.assertNotEqual(c.title,'공격 제목')
    def test_new_send_has_csrf_protection(self):
        c=self.direct();client=Client(enforce_csrf_checks=True);client.force_login(self.teacher);self.assertEqual(client.post(reverse('lms:conversation',args=[c.pk]),{'body':'x','client_token':uuid4()},HTTP_ACCEPT='application/json').status_code,403)
    def test_message_xss_is_escaped(self):
        c=self.direct();Message.objects.create(conversation=c,sender=self.student,body='<script>evil()</script>',client_token=uuid4());self.login();r=self.client.get(reverse('lms:conversation',args=[c.pk]));self.assertNotContains(r,'<script>evil()</script>');self.assertContains(r,'&lt;script&gt;')


class PublicationAndDateTests(LmsFixture):
    def payload(self,**more):
        now=timezone.localtime();p={'title':'신규 과제','group':self.group.pk,'description':'본문','content':'본문','points':10,'submission_type':'BOTH','available_from':(now-timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'),'due_at':(now+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),'student_ids':'6333','max_attempts':1,'time_limit_minutes':20};p.update(more);return p
    def test_publication_fields_absent_in_all_target_forms(self):
        for cls in [AssignmentForm,DiscussionForm,QuizForm,NoticeForm,PostForm]:
            with self.subTest(form=cls):f=cls();self.assertNotIn('is_published',f.fields);self.assertNotIn('published',f.fields)
    def test_new_assignment_auto_published(self):
        f=AssignmentForm(self.payload(),user=self.teacher);self.assertTrue(f.is_valid(),f.errors);a=f.save(commit=False);self.assertTrue(a.is_published)
    def test_forged_unpublished_input_is_ignored(self):
        f=AssignmentForm(self.payload(is_published=False),user=self.teacher);self.assertTrue(f.is_valid(),f.errors);self.assertTrue(f.save(commit=False).is_published)
    def test_existing_draft_stays_private_without_publish_action(self):
        self.assignment.is_published=False;self.assignment.save();f=AssignmentForm(self.payload(),instance=self.assignment,user=self.teacher);self.assertTrue(f.is_valid(),f.errors);a=f.save();self.assertFalse(a.is_published)
    def test_existing_draft_explicit_publish_button(self):
        self.assignment.is_published=False;self.assignment.save();f=AssignmentForm(self.payload(publish_now='1'),instance=self.assignment,user=self.teacher);self.assertTrue(f.is_valid(),f.errors);self.assertTrue(f.save().is_published)
    def test_new_quiz_default_public(self):f=QuizForm(self.payload(),user=self.teacher);self.assertTrue(f.is_valid(),f.errors);self.assertTrue(f.save(commit=False).is_published)
    def test_new_discussion_default_public(self):f=DiscussionForm(self.payload(),user=self.teacher);self.assertTrue(f.is_valid(),f.errors);self.assertTrue(f.save(commit=False).is_published)
    def test_new_class_post_public(self):
        f=PostForm({'kind':'NOTICE','title':'안내','body':'본문'});self.assertTrue(f.is_valid(),f.errors);self.assertTrue(f.save(commit=False).published)
    def test_post_draft_not_bulk_published(self):
        post=ClassPost.objects.create(group=self.group,created_by=self.teacher,title='비공개',published=False)
        f=PostForm({'kind':'NOTICE','title':'수정','body':'본문'},instance=post);self.assertTrue(f.is_valid(),f.errors);self.assertFalse(f.save().published)
    def test_new_form_starts_without_schedule(self):
        # 등록 화면 정리: 공개 시작은 비워 두면 저장 즉시 공개('공개 시간 예약'을 켤 때만 입력).
        for cls in [AssignmentForm,QuizForm,DiscussionForm]:self.assertFalse(cls(user=self.teacher).fields['available_from'].initial)
    def test_bound_schedule_not_overwritten(self):
        f=AssignmentForm(self.payload(available_from='2026-01-02T08:00'),user=self.teacher);self.assertEqual(f['available_from'].value(),'2026-01-02T08:00')
    def test_invalid_order_rejected(self):
        f=AssignmentForm(self.payload(available_from='2030-05-02T08:00',due_at='2030-05-01T08:00'),user=self.teacher);self.assertFalse(f.is_valid());self.assertIn('due_at',f.errors)
    def test_empty_due_keeps_required_validation(self):f=AssignmentForm(self.payload(due_at=''),user=self.teacher);self.assertFalse(f.is_valid());self.assertIn('due_at',f.errors)
    def test_html_no_student_public_checkbox(self):
        self.login()
        for url in ['assignments:create','learning:quiz-create','learning:discussion-create','communications:notice-create']:
            with self.subTest(url=url):r=self.client.get(reverse(url));self.assertEqual(r.status_code,200);self.assertNotContains(r,'name="is_published"')
    def test_group_student_scope_still_checked_on_save(self):
        self.login(self.ta);r=self.client.post(reverse('assignments:create'),self.payload(student_ids='8201'));self.assertIn(r.status_code,[200,403]);self.assertFalse(Assignment.objects.filter(title='신규 과제').exists())


class BulkSelectionTests(LmsFixture):
    def browse(self,user=None,**query):self.login(user or self.admin);return self.client.get(reverse('students:selector-browse'),query)
    def opts(self,user=None,**query):self.login(user or self.admin);return self.client.get(reverse('students:selector-options'),query)
    def test_admin_can_browse_without_individual_search(self):r=self.browse();self.assertEqual(r.status_code,200);self.assertEqual(r.json()['total'],3)
    def test_teacher_only_assigned_by_default(self):self.assertEqual([s['student_id'] for s in self.browse(self.teacher).json()['results']],['6333'])
    def test_self_assignment_can_discover_new_students(self):self.assertEqual(self.browse(self.teacher,mode='teacher').json()['total'],3)
    def test_student_cannot_browse(self):self.assertEqual(self.browse(self.student).status_code,403)
    def test_parent_cannot_browse(self):self.assertEqual(self.browse(self.parent).status_code,403)
    def test_inactive_teacher_denied(self):self.teacher.is_active=False;self.teacher.save();self.assertEqual(self.browse(self.teacher).status_code,302)
    def test_no_login_redirect(self):self.client.logout();self.assertEqual(self.client.get(reverse('students:selector-browse')).status_code,302)
    def test_group_members_in_activity_scope(self):r=self.browse(self.ta,activity_group=self.group.pk);self.assertEqual({s['student_id'] for s in r.json()['results']},{'6333','7102'})
    def test_foreign_group_cannot_expand_scope(self):self.assertEqual(self.browse(self.other_teacher,activity_group=self.group.pk).status_code,404)
    def test_lms_filter_intersects_assigned_scope(self):r=self.browse(self.teacher,source='lms',filter_group=self.group.pk);self.assertEqual({s['student_id'] for s in r.json()['results']},{'6333'})
    def test_lms_filter_with_activity_group_includes_ta_roster(self):r=self.browse(self.ta,source='lms',filter_group=self.group.pk,activity_group=self.group.pk);self.assertEqual(r.json()['total'],2)
    def test_revoked_ta_loses_filter(self):self.staff.active=False;self.staff.save();self.assertEqual(self.browse(self.ta,source='lms',filter_group=self.group.pk).status_code,404)
    def test_class_filter_demo_read_only(self):r=self.browse(source='intranet',class_id='201');self.assertEqual(r.json()['total'],1);self.assertEqual(r.json()['results'][0]['student_id'],'6333')
    def test_unknown_class_returns_empty_not_all(self):self.assertEqual(self.browse(source='intranet',class_id='999999').json()['total'],0)
    def test_class_must_be_selected(self):self.assertEqual(self.browse(source='intranet').json()['results'],[])
    def test_grade_and_school_filter(self):r=self.browse(grade='10',school='Ekamai');self.assertEqual(r.json()['total'],1)
    def test_filter_query_no_matches(self):self.assertEqual(self.browse(q='not-a-real-name').json()['total'],0)
    def test_invalid_source_rejected(self):self.assertEqual(self.browse(source='bad').status_code,400)
    def test_malformed_class_id_rejected(self):self.assertEqual(self.browse(source='intranet',class_id='1 OR 1=1').status_code,400)
    def test_huge_id_rejected(self):self.assertEqual(self.browse(activity_group='9'*90).status_code,400)
    def test_pages_and_selection_total(self):
        students=tuple(replace(DEMO_STUDENTS[0],student_id=str(i+10000),name=f'학생{i:03}') for i in range(125))
        with patch('apps.students.bulk_selector.DEMO_STUDENTS',students):
            r=self.browse(page=2).json();self.assertEqual(len(r['results']),50);self.assertEqual(r['total'],125);self.assertEqual(r['pages'],3)
            self.assertEqual(len(self.browse(all='1').json()['results']),125)
    def test_all_over_limit_is_atomic_no_partial(self):
        students=tuple(replace(DEMO_STUDENTS[0],student_id=str(i+10000),name=f'학생{i:03}') for i in range(205))
        with patch('apps.students.bulk_selector.DEMO_STUDENTS',students):
            r=self.browse(all='1');self.assertEqual(r.status_code,409);self.assertEqual(r.json()['results'],[])
    def test_teacher_all_limit_100(self):
        students=tuple(replace(DEMO_STUDENTS[0],student_id=str(i+10000),name=f'학생{i:03}') for i in range(101))
        with patch('apps.students.bulk_selector.DEMO_STUDENTS',students):self.assertEqual(self.browse(self.teacher,mode='teacher',all='1').status_code,409)
    def test_empty_teacher_does_not_expose_class_names(self):self.assertEqual(self.opts(self.other_teacher,source='intranet').json()['total'],0)
    def test_admin_class_options_include_history_and_status_filter(self):self.assertGreater(self.opts(source='intranet').json()['total'],1);self.assertEqual(self.opts(source='intranet',status='E').json()['total'],1)
    def test_options_scope_denied_to_student(self):self.assertEqual(self.opts(self.student).status_code,403)
    def test_no_store_headers(self):self.assertIn('no-store',self.browse()['Cache-Control']);self.assertIn('no-store',self.opts()['Cache-Control'])
    def test_database_failure_does_not_leak_secrets(self):
        with patch('apps.students.bulk_selector.browse_students',side_effect=OperationalError('secret-host-and-password')):
            r=self.browse();self.assertEqual(r.status_code,503);self.assertNotIn('secret-host',r.content.decode())
    def test_browse_never_mutates_student_links(self):
        before=list(self.group.lms_members.values());self.browse(all='1');self.opts(source='intranet');self.assertEqual(before,list(self.group.lms_members.values()))


class UsabilityAssetTests(SimpleTestCase):
    def asset(self,path):return (Path(settings.BASE_DIR)/path).read_text()
    def test_widget_skips_links_inside_chat_page_areas(self):
        # 11/16부터 작은 메신저는 자기 영역 안의 클릭만 맡으므로, 메시지 화면(data-chat-page)의 링크는 늘 그 주소로 이동합니다.
        self.assertIn("root.contains(element)",self.asset('apps/lms/static/lms/js/chat-widget.js'))
    def test_scripts_work_on_the_office_lan_address_without_https(self):
        # 사무실 서버는 http://192.168.x.x:8020 (보안 연결 아님) 이라 crypto.randomUUID 가 없습니다. 첨삭 표시 id는 getRandomValues 로 만듭니다.
        for path in Path(settings.BASE_DIR).glob('**/static/**/*.js'):
            if '.venv' in path.parts or 'staticfiles' in path.parts or 'node_modules' in path.parts:continue
            with self.subTest(script=path.name):self.assertNotIn('crypto.randomUUID(',path.read_text(encoding='utf-8'))
        self.assertIn('crypto.getRandomValues',self.asset('apps/lms/static/lms/js/annotation.js'))
    def test_unread_count_bumps_only_when_it_grows(self):
        s=self.asset('apps/lms/static/lms/js/chat-widget.js')
        self.assertIn("function setCount(",s)
        self.assertIn("classList.add('is-bumped')",s)
        self.assertIn("Number(text)>Number(e.textContent)",s)
    def test_ime_guard_present(self):
        s=self.asset('apps/lms/static/lms/js/chat-composer.js')
        for x in ['compositionstart','compositionend','event.isComposing','event.keyCode===229','event.shiftKey','form.requestSubmit']:self.assertIn(x,s)
        messages=self.asset('apps/lms/static/lms/js/messages.js')
        self.assertIn('EduChatComposer',messages)
        self.assertNotIn("addEventListener('keydown'",messages)
    def test_no_full_message_reload_or_html_injection(self):
        s=self.asset('apps/lms/static/lms/js/messages.js');self.assertNotIn('location.reload',s);self.assertNotIn('innerHTML',s)
    def test_active_chat_is_fast_background_is_slow(self):self.assertIn('interval:2000',self.asset('apps/lms/static/lms/js/messages.js'));self.assertIn('INTERVAL = 15000',self.asset('apps/lms/static/lms/js/polling.js'))
    def test_date_helpers_use_named_timezone(self):
        # 11/19: 날짜 고르기는 date-picker.js 가 맡고, '오늘'은 학원 시간대로 계산
        s=self.asset('static/js/global/date-picker.js');self.assertIn('timeZone: zone',s);self.assertNotIn('toISOString()',s)
    def test_date_helpers_are_trimmed_to_what_is_needed(self):
        # 11/19: 마감 빠른 버튼 3개도 없애고(사용자 요청) 날짜 칸을 누르면 달력이 열립니다. '공개 시간 예약' 켜고 끄기는 그대로.
        s=self.asset('static/js/global/form-usability.js')
        for gone in ["'달력'","'지우기'","기준`","'오늘 밤'","'내일 밤'","'1주 뒤'"]:self.assertNotIn(gone,s)
        self.assertIn("data-schedule-toggle",s)
    def test_bulk_helpers_do_not_silently_slice_selected(self):s=self.asset('static/js/components/student-transfer-selector.js');self.assertIn('selected.size+candidates.length>max',s);self.assertNotIn('.slice(0, remaining)',s)
    def test_new_css_no_small_fonts_or_serif(self):
        import re
        s=self.asset('static/css/layers/90-usability.css');self.assertFalse(re.search(r'font-size:\s*(?:[0-9]|1[0-3])px',s));self.assertNotIn('Georgia',s)
    def test_no_database_or_cookies_in_ui_storage(self):
        for f in ['apps/lms/static/lms/js/messages.js','static/js/global/student-browser.js','static/js/global/form-usability.js']:self.assertNotIn('localStorage',self.asset(f))


class ExtraFormCoverageTests(LmsFixture):
    def test_notice_existing_private_has_explicit_publish_action(self):
        from apps.communications.models import Notice
        n=Notice.objects.create(title='비공개',content='안내',created_by=self.teacher,is_published=False)
        self.login();r=self.client.get(reverse('communications:notice-update',args=[n.pk]));self.assertEqual(r.status_code,200);self.assertContains(r,'공개하고 저장');self.assertContains(r,'name="publish_now"');self.assertNotContains(r,'name="is_published"')
    def test_new_notice_public_without_checkbox(self):
        self.login();r=self.client.post(reverse('communications:notice-create'),{'title':'공개 확인','content':'안내','audiences':['STUDENT']});self.assertEqual(r.status_code,302)
        from apps.communications.models import Notice
        self.assertTrue(Notice.objects.get(title='공개 확인').is_published)
    def test_date_and_hidden_selection_fields_in_forms(self):
        from html.parser import HTMLParser
        class Fields(HTMLParser):
            def __init__(self):super().__init__();self.names=set()
            def handle_starttag(self,tag,attrs):
                if tag in ('input','select','textarea'):
                    self.names.add(dict(attrs).get('name'))
        self.login()
        for url in ['assignments:create','learning:quiz-create','learning:discussion-create','communications:notice-create','classroom:board-create']:
            r=self.client.get(reverse(url));p=Fields();p.feed(r.content.decode());form=r.context['form']
            self.assertFalse(set(form.fields)-p.names,(url,set(form.fields)-p.names))


class InlineTextToolTests(SimpleTestCase):
    def test_text_tool_opens_a_box_on_the_document_where_you_click(self):
        # 첨삭 '글씨' 도구: 누른 자리에 바로 입력 칸이 뜨고, 글자를 치면 문서에 그대로 보입니다.
        s=(Path(settings.BASE_DIR)/'apps/lms/static/lms/js/annotation.js').read_text(encoding='utf-8')
        self.assertIn('function openInlineText(',s)
        self.assertIn("mark.type==='freetext'",s)
        self.assertIn('ann-inline-text',(Path(settings.BASE_DIR)/'apps/lms/static/lms/css/workspace.css').read_text(encoding='utf-8'))
