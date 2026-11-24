import io
import json
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase,Client,override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import StudentAccountLink
from apps.operations.models import TeacherStudentAccess
from apps.learning.models import LearningGroup,Quiz,QuizRecipient,QuizAttempt,QuizQuestion,QuizChoice,QuizAnswer
from apps.assignments.models import Assignment,AssignmentRecipient,Submission
from apps.assignments.forms import AssignmentForm,SubmissionForm
from apps.lms.models import GroupMember,GroupStaff,ClassPost,PostFile,ReviewDocument,Conversation,ConversationMember,Message,RoomSettings,SubmissionFile
from apps.lms.access import can_manage,contacts_for,can_converse
from apps.lms.documents import clean_annotations,version_token,document_is_current,create_preview,PreviewError
from apps.lms.forms import validate_file,MultiFileField
from apps.lms.grade_views import review_version


def pdf_bytes():
    out=io.BytesIO();im=Image.new('RGB',(320,440),'white');im.save(out,format='PDF');im.close();return out.getvalue()

def image_upload(name='answer.png'):
    out=io.BytesIO();im=Image.new('RGB',(220,280),'white');im.save(out,format='PNG');im.close()
    return SimpleUploadedFile(name,out.getvalue(),'image/png')

class LmsFixture(TestCase):
    def setUp(self):
        self.tmp=tempfile.mkdtemp(prefix='lms-test-');self.override=override_settings(MEDIA_ROOT=self.tmp,STUDENT_DATA_SOURCE='demo',ASSESSMENT_DATA_SOURCE='demo',CLASS_CATALOG_DATA_SOURCE='demo',ADMIN_AUTO_LINK_TEST_ACCOUNTS=False)
        self.override.enable();self.addCleanup(self.override.disable);self.addCleanup(lambda:shutil.rmtree(self.tmp,ignore_errors=True))
        U=get_user_model()
        self.admin=U.objects.create_user('qa_admin',password='test-1234',role='ADMIN')
        self.teacher=U.objects.create_user('qa_teacher',password='test-1234',role='TEACHER')
        self.ta=U.objects.create_user('qa_ta',password='test-1234',role='TEACHER')
        self.other_teacher=U.objects.create_user('qa_other_teacher',password='test-1234',role='TEACHER')
        self.student=U.objects.create_user('qa_student',password='test-1234',role='STUDENT',display_name='학생 A')
        self.other=U.objects.create_user('qa_other_student',password='test-1234',role='STUDENT',display_name='학생 B')
        self.parent=U.objects.create_user('qa_parent',password='test-1234',role='PARENT')
        for user,no,relationship in [(self.student,'6333','SELF'),(self.other,'7102','SELF'),(self.parent,'6333','PARENT')]:
            StudentAccountLink.objects.create(user=user,student_no=no,relationship=relationship,is_active=True)
        TeacherStudentAccess.objects.create(teacher=self.teacher,student_no='6333',student_name='학생 A',assigned_by=self.admin)
        self.group=LearningGroup.objects.create(title='QA 문학반',created_by=self.teacher)
        self.members=[]
        for no,name in [('6333','학생 A'),('7102','학생 B')]:self.members.append(GroupMember.objects.create(group=self.group,student_no=no,student_name=name))
        self.staff=GroupStaff.objects.create(group=self.group,user=self.ta,duty='TA')
        self.assignment=Assignment.objects.create(title='문학 과제',description='근거를 작성하세요.',group=self.group,created_by=self.teacher,due_at=timezone.now()+timedelta(days=3),points=10)
        self.recipient=AssignmentRecipient.objects.create(assignment=self.assignment,student_id='6333',student_name='학생 A')
        self.recipient2=AssignmentRecipient.objects.create(assignment=self.assignment,student_id='7102',student_name='학생 B')
        self.sub=Submission.objects.create(recipient=self.recipient,text_answer='학생 답안',submitted_at=timezone.now())
        self.quiz=Quiz.objects.create(title='VOCAB 퀴즈',group=self.group,created_by=self.teacher,due_at=timezone.now()+timedelta(days=3))
        self.qr=QuizRecipient.objects.create(quiz=self.quiz,student_id='6333',student_name='학생 A')
        self.attempt=QuizAttempt.objects.create(recipient=self.qr,user=self.student,attempt_no=1,score=3,max_score=5,submitted_at=timezone.now())
        self.question=QuizQuestion.objects.create(quiz=self.quiz,prompt='A word',points=5,correct_text='answer',question_type='SHORT')
        QuizAnswer.objects.create(attempt=self.attempt,question=self.question,text_answer='student answer',earned_points=3)
    def login(self,user=None):self.client.force_login(user or self.teacher)
    def post_grade(self,score='9',version=None,as_user=None):
        self.login(as_user or self.teacher)
        return self.client.post(reverse('lms:submission-review',args=[self.sub.pk]),{'score':score,'feedback':'총평','version':version or review_version(self.sub)})
    def doc(self):
        doc=ReviewDocument(submission=self.sub,original_name='answer.pdf',source_key='text',source_token=version_token(self.sub),page_count=1)
        doc.pdf.save('answer.pdf',ContentFile(pdf_bytes()));return doc
    def mark(self,kind='point'):
        return {'id':str(uuid4()),'type':kind,'page':1,'x':.1,'y':.2,'w':.2,'h':.1,'text':'설명 <script>alert(1)</script>','color':'#dc2626','size':16,'points':[[.1,.2],[.3,.4]] if kind=='freehand' else []}

class ClassroomTests(LmsFixture):
    def test_roles_see_authorized_group(self):
        for user in [self.admin,self.teacher,self.ta,self.student,self.parent]:
            with self.subTest(user=user.role):self.login(user);self.assertEqual(self.client.get(reverse('lms:room',args=[self.group.pk])).status_code,200)
    def test_other_teacher_cannot_open_group(self):
        self.login(self.other_teacher);self.assertEqual(self.client.get(reverse('lms:room',args=[self.group.pk])).status_code,404)
    def test_student_cannot_change_settings(self):
        self.login(self.student);self.assertEqual(self.client.post(reverse('lms:room-settings',args=[self.group.pk]),{}).status_code,403)
    def test_ta_can_author_class_notice(self):
        self.login(self.ta);r=self.client.post(reverse('lms:post-new',args=[self.group.pk]),{'kind':'NOTICE','title':'공지','body':'안내','published':'on'})
        self.assertEqual(r.status_code,302);self.assertEqual(ClassPost.objects.get().created_by,self.ta)
    def test_class_page_not_global_notice(self):
        self.login();self.client.post(reverse('lms:post-new',args=[self.group.pk]),{'kind':'PAGE','title':'단어장','body':'vocab','published':'on'})
        from apps.communications.models import Notice
        self.assertEqual(ClassPost.objects.count(),1);self.assertEqual(Notice.objects.count(),0)
    def test_draft_hidden_from_student(self):
        p=ClassPost.objects.create(group=self.group,kind='NOTICE',title='draft',body='private',created_by=self.teacher,published=False)
        self.login(self.student);self.assertEqual(self.client.get(reverse('lms:post',args=[p.pk])).status_code,404)
    def test_group_settings_https_validation(self):
        self.login();r=self.client.post(reverse('lms:room-settings',args=[self.group.pk]),{'zoom_url':'http://example.com','schedule':'schedule'})
        self.assertEqual(r.status_code,200);self.assertFalse(RoomSettings.objects.exists())
    def test_group_settings_saved(self):
        self.login();r=self.client.post(reverse('lms:room-settings',args=[self.group.pk]),{'zoom_url':'https://example.com','schedule':'Mon','dsg_guide':'DSG','classroom_url':'https://classroom.google.com','canvas_url':'https://example.com/canvas'})
        self.assertEqual(r.status_code,302);self.assertEqual(RoomSettings.objects.get().schedule,'Mon')
    def test_ta_cannot_change_roster_or_promote(self):
        self.login(self.ta);self.assertEqual(self.client.get(reverse('lms:roster',args=[self.group.pk])).status_code,403)
    def test_revoked_ta_blocked_even_own_post(self):
        p=ClassPost.objects.create(group=self.group,created_by=self.ta,kind='NOTICE',title='x',body='x')
        self.staff.active=False;self.staff.save();self.login(self.ta)
        self.assertFalse(can_manage(self.ta,p));self.assertEqual(self.client.get(reverse('lms:post',args=[p.pk])).status_code,404)
    def test_ta_student_search_is_group_scoped(self):
        self.login(self.ta);r=self.client.get(reverse('lms:group-students',args=[self.group.pk]))
        self.assertEqual(r.status_code,200);self.assertEqual({a['student_id'] for a in r.json()['results']},{'6333','7102'})
    def test_learner_cannot_call_group_search(self):
        self.login(self.student);self.assertEqual(self.client.get(reverse('lms:group-students',args=[self.group.pk])).status_code,403)
    def test_new_assignment_prefills_group_members_for_ta(self):
        self.login(self.ta);r=self.client.get(reverse('assignments:create')+f'?group={self.group.pk}')
        self.assertEqual(r.status_code,200);self.assertEqual(set(r.context['form']['student_ids'].value().split(',')),{'6333','7102'})
        self.assertIn('/lms/groups/',r.context['student_selector']['search_url'])
    def test_post_file_requires_membership(self):
        p=ClassPost.objects.create(group=self.group,created_by=self.teacher,kind='FILE',title='파일')
        f=PostFile.objects.create(post=p,file=SimpleUploadedFile('lesson.txt',b'data'),original_name='lesson.txt',size=4)
        self.login(self.other_teacher);self.assertEqual(self.client.get(reverse('lms:post-file',args=[f.pk])).status_code,404)
        self.login(self.student);r=self.client.get(reverse('lms:post-file',args=[f.pk]));self.assertEqual(r.status_code,200);r.close()
    def test_raw_private_media_is_blocked(self):
        self.login(self.admin);self.assertEqual(self.client.get('/media/lms_private/answer.pdf').status_code,404)
    def test_csrf_required_for_new_mutations(self):
        client=Client(enforce_csrf_checks=True);client.force_login(self.teacher)
        self.assertEqual(client.post(reverse('lms:post-new',args=[self.group.pk]),{}).status_code,403)
    def test_delete_only_post(self):
        p=ClassPost.objects.create(group=self.group,created_by=self.teacher,kind='PAGE',title='x')
        self.login();self.assertEqual(self.client.get(reverse('lms:post-delete',args=[p.pk])).status_code,405);self.assertTrue(ClassPost.objects.filter(pk=p.pk).exists())
    def test_invalid_group_filter_no_crash(self):
        self.login();self.assertEqual(self.client.get(reverse('lms:gradebook'),{'group':'not-an-id'}).status_code,200)

class GradeTests(LmsFixture):
    def test_assignment_score_and_comment(self):
        self.assertEqual(self.post_grade('8.5').status_code,302);self.sub.refresh_from_db();self.assertEqual(self.sub.score,Decimal('8.50'));self.assertEqual(self.sub.feedback,'총평')
    def test_zero_is_recorded_not_missing(self):
        self.post_grade('0');self.sub.refresh_from_db();self.assertEqual(self.sub.score,Decimal('0'))
        r=self.client.get(reverse('lms:gradebook'));self.assertContains(r,'<strong>0.00</strong>',html=True)
    def test_maximum_score_enforced(self):
        self.assertEqual(self.post_grade('11').status_code,200);self.sub.refresh_from_db();self.assertIsNone(self.sub.score)
    def test_negative_rejected(self):self.assertEqual(self.post_grade('-1').status_code,200)
    def test_parent_cannot_grade(self):self.assertEqual(self.post_grade('10',as_user=self.parent).status_code,404)
    def test_other_student_cannot_read_feedback(self):
        self.login(self.other);self.assertEqual(self.client.get(reverse('lms:submission-review',args=[self.sub.pk])).status_code,404)
    def test_ta_can_grade_assigned_class(self):self.assertEqual(self.post_grade('9',as_user=self.ta).status_code,302)
    def test_other_teacher_cannot_grade(self):self.assertEqual(self.post_grade('9',as_user=self.other_teacher).status_code,404)
    def test_stale_grade_rejected_without_overwrite(self):
        old=review_version(self.sub);self.post_grade('7');r=self.post_grade('9',version=old)
        self.assertContains(r,'다른 채점');self.sub.refresh_from_db();self.assertEqual(self.sub.score,Decimal('7'))
    def test_quiz_adjustment_preserves_auto_score(self):
        self.login();r=self.client.post(reverse('lms:quiz-review',args=[self.attempt.pk]),{'score':'4','feedback':'수정','version':review_version(self.attempt)})
        self.assertEqual(r.status_code,302);self.attempt.refresh_from_db();self.assertEqual(self.attempt.score,3);self.assertEqual(self.attempt.final_score,4)
    def test_quiz_grade_blank_resets_override(self):
        self.attempt.manual_score=5;self.attempt.save();self.login();r=self.client.post(reverse('lms:quiz-review',args=[self.attempt.pk]),{'score':'','feedback':'','version':review_version(self.attempt)})
        self.assertEqual(r.status_code,302);self.attempt.refresh_from_db();self.assertEqual(self.attempt.final_score,3)
    def test_quiz_maximum_rejected(self):
        self.login();r=self.client.post(reverse('lms:quiz-review',args=[self.attempt.pk]),{'score':'6','feedback':'','version':review_version(self.attempt)})
        self.assertEqual(r.status_code,200);self.attempt.refresh_from_db();self.assertIsNone(self.attempt.manual_score)
    def test_gradebook_rows_restricted_to_learner(self):
        self.login(self.student);r=self.client.get(reverse('lms:gradebook'));self.assertEqual(r.context['student_count'],1);self.assertEqual(r.context['rows'][0]['id'],'6333');self.assertNotContains(r,'학생 B')
    def test_parent_gradebook_child_only(self):
        self.login(self.parent);r=self.client.get(reverse('lms:gradebook'));self.assertEqual(r.context['student_count'],1)
    def test_gradebook_missing_is_not_zero(self):
        self.login();r=self.client.get(reverse('lms:gradebook'));self.assertContains(r,'배정 없음');self.assertContains(r,'미제출');self.assertContains(r,'—')
    def test_gradebook_individual_filter(self):
        self.login();r=self.client.get(reverse('lms:gradebook'),{'item':f'a:{self.assignment.pk}'})
        self.assertEqual(r.context['column_count'],1)
    def test_gradebook_latest_attempt_used(self):
        QuizAttempt.objects.create(recipient=self.qr,user=self.student,attempt_no=2,score=1,max_score=5,submitted_at=timezone.now())
        self.login();r=self.client.get(reverse('lms:gradebook'),{'kind':'quiz'});self.assertEqual(r.context['rows'][0]['cells'][0]['attempt'],2)
    def test_assignment_file_only_rejects_text(self):
        self.assignment.submission_type='FILE';self.assignment.save();self.login(self.student)
        r=self.client.post(reverse('assignments:my-detail',args=[self.recipient.pk]),{'text_answer':'no file'})
        self.assertEqual(r.status_code,200);self.assertContains(r,'파일 업로드 과제')
    def test_multiple_student_files(self):
        self.login(self.student);r=self.client.post(reverse('assignments:my-detail',args=[self.recipient.pk]),{'text_answer':'','uploads':[SimpleUploadedFile('a.txt',b'A'),SimpleUploadedFile('b.txt',b'B')]})
        self.assertEqual(r.status_code,302);self.assertEqual(self.sub.extra_files.count(),2)
    def test_submit_clears_old_grade_archives_annotations(self):
        doc=self.doc();self.sub.score=8;self.sub.feedback='old';self.sub.feedback_at=timezone.now();self.sub.save()
        self.login(self.student);r=self.client.post(reverse('assignments:my-detail',args=[self.recipient.pk]),{'text_answer':'new answer'})
        self.assertEqual(r.status_code,302);self.sub.refresh_from_db();doc.refresh_from_db();self.assertIsNone(self.sub.score);self.assertEqual(self.sub.feedback,'');self.assertFalse(document_is_current(doc));self.assertTrue(doc.pdf.storage.exists(doc.pdf.name))
    @override_settings(LMS_ALLOW_PARENT_SUBMISSION=False)
    def test_parent_proxy_can_be_disabled_explicitly(self):
        self.login(self.parent);r=self.client.post(reverse('assignments:my-detail',args=[self.recipient.pk]),{'text_answer':'proxy'})
        self.assertEqual(r.status_code,403)
    def test_rejected_foreign_group_assignment(self):
        self.login(self.other_teacher);r=self.client.get(reverse('assignments:update',args=[self.assignment.pk]));self.assertEqual(r.status_code,403)

class AnnotationTests(LmsFixture):
    def test_six_tools_validation(self):
        for kind in ['point','highlight','freetext','strikeout','freehand','area']:
            with self.subTest(kind=kind):self.assertEqual(clean_annotations([self.mark(kind)],1)[0]['type'],kind)
    def test_invalid_geometry_rejected(self):
        m=self.mark();m['x']=float('nan')
        with self.assertRaises(ValidationError):clean_annotations([m],1)
    def test_off_page_rejected(self):
        m=self.mark();m['x']=.9;m['w']=.5
        with self.assertRaises(ValidationError):clean_annotations([m],1)
    def test_invalid_page_rejected(self):
        m=self.mark();m['page']=2
        with self.assertRaises(ValidationError):clean_annotations([m],1)
    def test_save_six_tools_and_revision(self):
        doc=self.doc();self.login();marks=[self.mark(t) for t in ['point','highlight','freetext','strikeout','freehand','area']]
        r=self.client.post(reverse('lms:document-annotations',args=[doc.pk]),json.dumps({'revision':0,'annotations':marks}),content_type='application/json')
        self.assertEqual(r.status_code,200);doc.refresh_from_db();self.assertEqual(len(doc.annotations),6);self.assertEqual(doc.revision,1)
    def test_concurrent_annotation_returns_409(self):
        doc=self.doc();self.login();url=reverse('lms:document-annotations',args=[doc.pk]);body=json.dumps({'revision':0,'annotations':[self.mark()]})
        self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,200)
        self.assertEqual(self.client.post(url,body,content_type='application/json').status_code,409)
    def test_student_and_parent_read_only(self):
        doc=self.doc()
        for user in [self.student,self.parent]:
            self.login(user);self.assertEqual(self.client.get(reverse('lms:document',args=[doc.pk])).status_code,200)
            self.assertEqual(self.client.post(reverse('lms:document-annotations',args=[doc.pk]),'{}',content_type='application/json').status_code,404)
    def test_other_student_cannot_get_document_or_image(self):
        doc=self.doc();self.login(self.other)
        self.assertEqual(self.client.get(reverse('lms:document',args=[doc.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('lms:document-page',args=[doc.pk,1])).status_code,404)
    def test_stale_document_cannot_modify(self):
        doc=self.doc();self.sub.submitted_at=timezone.now()+timedelta(minutes=1);self.sub.save();self.login()
        r=self.client.post(reverse('lms:document-annotations',args=[doc.pk]),json.dumps({'revision':0,'annotations':[]}),content_type='application/json')
        self.assertEqual(r.status_code,409)
    def test_actual_pdf_image_response(self):
        doc=self.doc();self.login();r=self.client.get(reverse('lms:document-page',args=[doc.pk,1]))
        self.assertEqual(r.status_code,200);self.assertTrue(r.content.startswith(b'\x89PNG'));self.assertEqual(r['Cache-Control'],'private, no-store')
    def test_actual_image_preview_creation_idempotent(self):
        self.sub.attachment.save('answer.png',image_upload());self.sub.attachment_name='answer.png';self.sub.save()
        self.login();url=reverse('lms:prepare-submission',args=[self.sub.pk]);r=self.client.post(url,{'source':'primary'})
        self.assertEqual(r.status_code,302);r=self.client.post(url,{'source':'primary'});self.assertEqual(r.status_code,302);self.assertEqual(ReviewDocument.objects.count(),1)
    def test_actual_quiz_answer_preview(self):
        self.login();r=self.client.post(reverse('lms:prepare-quiz',args=[self.attempt.pk]));self.assertEqual(r.status_code,302);self.assertEqual(ReviewDocument.objects.get().attempt_id,self.attempt.pk)
    def test_invalid_pdf_upload_rejected(self):
        self.login();r=self.client.post(reverse('lms:prepare-submission',args=[self.sub.pk]),{'source':'text','preview':SimpleUploadedFile('x.pdf',b'not a pdf')})
        self.assertEqual(r.status_code,422);self.assertFalse(ReviewDocument.objects.exists())
    def test_manual_pdf_for_office_preserves_source(self):
        self.sub.attachment.save('answer.xlsx',ContentFile(b'original placeholder'));self.sub.attachment_name='answer.xlsx';self.sub.save()
        self.login();r=self.client.post(reverse('lms:prepare-submission',args=[self.sub.pk]),{'source':'primary','preview':SimpleUploadedFile('preview.pdf',pdf_bytes())})
        self.assertEqual(r.status_code,302)
        with self.sub.attachment.open('rb') as f:self.assertEqual(f.read(),b'original placeholder')
    def test_invalid_document_json_does_not_500(self):
        doc=self.doc();self.login()
        for body in ['[1]','null','{bad json}']:
            with self.subTest(body=body):self.assertEqual(self.client.post(reverse('lms:document-annotations',args=[doc.pk]),body,content_type='application/json').status_code,400)
    def test_pdf_first_and_last_page_boundaries(self):
        doc=self.doc();self.login();self.assertEqual(self.client.get(reverse('lms:document-page',args=[doc.pk,2])).status_code,404)

class MessagingTests(LmsFixture):
    def conversation(self,group=None,users=None):
        c=Conversation.objects.create(title='질문',created_by=self.teacher,group=group)
        for user in users or [self.teacher,self.student]:ConversationMember.objects.create(conversation=c,user=user)
        return c
    def test_student_can_contact_only_current_teachers(self):
        self.assertEqual(set(contacts_for(self.student).values_list('pk',flat=True)),{self.teacher.pk,self.ta.pk})
    def test_teacher_cannot_contact_unassigned_student(self):
        GroupMember.objects.filter(group=self.group,student_no='7102').update(active=False)
        self.assertNotIn(self.other.pk,contacts_for(self.teacher).values_list('pk',flat=True))
    def test_parent_cannot_use_inbox(self):
        self.login(self.parent);self.assertEqual(self.client.get(reverse('lms:inbox')).status_code,403)
    def test_personal_thread_create(self):
        self.login(self.student);r=self.client.post(reverse('lms:new-conversation'),{'title':'질문','recipients':[self.teacher.pk]})
        self.assertEqual(r.status_code,302);self.assertEqual(Conversation.objects.count(),1)
    def test_foreign_recipient_rejected(self):
        self.login(self.student);r=self.client.post(reverse('lms:new-conversation'),{'title':'질문','recipients':[self.other_teacher.pk]})
        self.assertEqual(r.status_code,200);self.assertFalse(Conversation.objects.exists())
    def test_group_chat_staff_can_create(self):
        self.login(self.teacher);r=self.client.post(reverse('lms:new-conversation')+f'?group={self.group.pk}',{'title':'그룹 질문','recipients':[self.student.pk,self.other.pk,self.ta.pk]})
        self.assertEqual(r.status_code,302);self.assertEqual(ConversationMember.objects.count(),4)
    def test_student_cannot_create_group_chat(self):
        self.login(self.student);r=self.client.get(reverse('lms:new-conversation')+f'?group={self.group.pk}');self.assertEqual(r.status_code,403)
    def test_post_message_idempotency(self):
        c=self.conversation();self.login(self.student);token=str(uuid4());data={'body':'질문입니다.','client_token':token}
        for _ in range(2):self.assertEqual(self.client.post(reverse('lms:conversation',args=[c.pk]),data).status_code,302)
        self.assertEqual(Message.objects.count(),1)
    def test_unauthorized_person_cannot_read_or_post(self):
        c=self.conversation();self.login(self.other)
        self.assertEqual(self.client.get(reverse('lms:conversation',args=[c.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('lms:conversation',args=[c.pk]),{'body':'x','client_token':uuid4()}).status_code,404)
        self.assertEqual(self.client.get(reverse('lms:conversation-feed',args=[c.pk])).status_code,404)
    def test_removed_group_member_cannot_read_old_thread(self):
        c=self.conversation(group=self.group);self.members[0].active=False;self.members[0].save();self.login(self.student)
        self.assertEqual(self.client.get(reverse('lms:conversation',args=[c.pk])).status_code,404)
    def test_new_member_not_automatically_in_old_thread(self):
        c=self.conversation(group=self.group);self.assertFalse(can_converse(self.other,c))
    def test_feed_orders_messages_and_pagination(self):
        c=self.conversation();m=Message.objects.create(conversation=c,sender=self.teacher,body='one');n=Message.objects.create(conversation=c,sender=self.student,body='two')
        self.login(self.student);r=self.client.get(reverse('lms:conversation-feed',args=[c.pk]),{'after':m.pk});self.assertEqual([i['id'] for i in r.json()['messages']],[n.pk])
    def test_invalid_feed_cursor(self):
        c=self.conversation();self.login(self.student);self.assertEqual(self.client.get(reverse('lms:conversation-feed',args=[c.pk]),{'after':'bad'}).status_code,400)
    def test_message_xss_escaped(self):
        c=self.conversation();Message.objects.create(conversation=c,sender=self.teacher,body='<script>alert(1)</script>')
        self.login(self.student);r=self.client.get(reverse('lms:conversation',args=[c.pk]));self.assertNotContains(r,'<script>alert(1)</script>');self.assertContains(r,'&lt;script&gt;')
    def test_message_length_enforced(self):
        c=self.conversation();self.login(self.student);r=self.client.post(reverse('lms:conversation',args=[c.pk]),{'body':'x'*4001,'client_token':uuid4()});self.assertEqual(r.status_code,200);self.assertFalse(Message.objects.exists())

class UploadValidationTests(TestCase):
    def test_non_pdf_rejected(self):
        with self.assertRaises(ValidationError):validate_file(SimpleUploadedFile('test.pdf',b'bad'))
    def test_script_rejected(self):
        with self.assertRaises(ValidationError):validate_file(SimpleUploadedFile('test.html',b'<script>'))
    def test_fake_office_rejected(self):
        with self.assertRaises(ValidationError):validate_file(SimpleUploadedFile('test.docx',b'bad'))
    def test_image_validated(self):self.assertIsNotNone(validate_file(image_upload()))
    def test_resource_audio_allowed(self):self.assertIsNotNone(validate_file(SimpleUploadedFile('lesson.mp3',b'ID3sample'),resource=True))
    def test_student_audio_not_silently_allowed(self):
        with self.assertRaises(ValidationError):validate_file(SimpleUploadedFile('answer.mp3',b'ID3sample'))
    def test_multiple_files_cap(self):
        with self.assertRaises(ValidationError):MultiFileField().clean([SimpleUploadedFile(f'{i}.txt',b'x') for i in range(6)])


class CommunicationConsistencyTests(LmsFixture):
    def test_ta_private_contacts_include_own_class_only(self):
        from apps.lms.access import contacts_for
        self.assertTrue(contacts_for(self.ta).filter(pk=self.student.pk).exists())
        self.assertTrue(contacts_for(self.ta).filter(pk=self.other.pk).exists())
        outsider=get_user_model().objects.create_user('outside',role='STUDENT')
        StudentAccountLink.objects.create(user=outsider,student_no='99999',relationship='SELF',is_active=True)
        self.assertFalse(contacts_for(self.ta).filter(pk=outsider.pk).exists())

    def test_student_to_class_ta_conversation_is_bidirectional(self):
        from apps.lms.access import can_converse
        from apps.lms.models import Conversation,ConversationMember
        conv=Conversation.objects.create(title='TA 문의',created_by=self.student)
        ConversationMember.objects.create(conversation=conv,user=self.student)
        ConversationMember.objects.create(conversation=conv,user=self.ta)
        self.assertTrue(can_converse(self.student,conv))
        self.assertTrue(can_converse(self.ta,conv))
        self.staff.active=False;self.staff.save()
        self.assertFalse(can_converse(self.ta,conv))
        self.assertFalse(can_converse(self.student,conv))

    def test_raw_legacy_submission_media_is_blocked(self):
        self.login(self.admin)
        self.assertEqual(self.client.get('/media/assignments/submissions/answer.pdf').status_code,404)


class PrivateFileLifecycleTests(LmsFixture):
    def test_submission_form_does_not_expose_private_storage_url(self):
        self.sub.attachment.save('long_name.pdf',ContentFile(pdf_bytes()))
        self.login(self.student)
        response=self.client.get(reverse('assignments:my-detail',args=[self.recipient.pk]))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,self.sub.attachment.url)
        self.assertContains(response,'기존 대표 파일 삭제')

    def test_cascading_delete_cleans_preview_after_commit(self):
        doc=self.doc();storage,name=doc.pdf.storage,doc.pdf.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assignment.delete()
        self.assertFalse(storage.exists(name))

    def test_cascading_delete_cleans_class_files_after_commit(self):
        post=ClassPost.objects.create(group=self.group,created_by=self.teacher,kind='FILE',title='File')
        file=PostFile.objects.create(post=post,file=SimpleUploadedFile('audio.mp3',b'data'),original_name='audio.mp3',size=4)
        storage,name=file.file.storage,file.file.name
        with self.captureOnCommitCallbacks(execute=True):
            self.group.delete()
        self.assertFalse(storage.exists(name))


class ActivityHistoryProtectionTests(LmsFixture):
    def test_assignment_recipient_removal_preserves_submission(self):
        from apps.assignments.services import AssignmentService,UnknownStudentsError
        from types import SimpleNamespace
        form=SimpleNamespace(save=lambda commit: self.assignment,cleaned_data={'student_ids':['7102']})
        with self.assertRaises(UnknownStudentsError):AssignmentService().save_assignment(form=form,user=self.teacher)
        self.assertTrue(Submission.objects.filter(pk=self.sub.pk).exists())
        self.assertTrue(AssignmentRecipient.objects.filter(pk=self.recipient.pk).exists())

    def test_quiz_recipient_removal_preserves_attempt(self):
        from apps.learning.services import save_quiz,UnknownStudentsError
        from types import SimpleNamespace
        form=SimpleNamespace(save=lambda commit: self.quiz,cleaned_data={'student_ids':['7102']})
        with self.assertRaises(UnknownStudentsError):save_quiz(form=form,user=self.teacher)
        self.assertTrue(QuizAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_ta_can_save_class_assignment_without_global_student_grant(self):
        from apps.assignments.services import AssignmentService
        from types import SimpleNamespace
        obj=Assignment(title='TA assignment',group=self.group,points=10,due_at=timezone.now()+timedelta(days=2))
        form=SimpleNamespace(save=lambda commit: obj,cleaned_data={'student_ids':['7102']})
        saved=AssignmentService().save_assignment(form=form,user=self.ta)
        self.assertEqual(saved.created_by,self.ta)
        self.assertEqual(list(saved.recipients.values_list('student_id',flat=True)),['7102'])
        self.assertFalse(TeacherStudentAccess.objects.filter(teacher=self.ta).exists())

    def test_new_form_contains_group_search_switch(self):
        self.login(self.ta);r=self.client.get(reverse('assignments:create'))
        self.assertContains(r,'data-lms-student-search-pattern')

    def test_discussion_file_scope_and_raw_media_guard(self):
        from apps.learning.models import Discussion,DiscussionRecipient
        d=Discussion.objects.create(title='Discussion',content='hello',group=self.group,created_by=self.teacher,due_at=timezone.now()+timedelta(days=1))
        d.attachment.save('lesson.txt',ContentFile(b'private'))
        DiscussionRecipient.objects.create(discussion=d,student_id='6333',student_name='A')
        self.login(self.student);r=self.client.get(reverse('lms:discussion-file',args=[d.pk]));self.assertEqual(r.status_code,200);r.close()
        self.assertEqual(self.client.get(d.attachment.url).status_code,404)
        self.login(self.other);self.assertEqual(self.client.get(reverse('lms:discussion-file',args=[d.pk])).status_code,404)


class ExtraFileContentTests(LmsFixture):
    def test_extra_files_count_as_submission_content(self):
        self.sub.text_answer='';self.sub.attachment='';self.sub.save()
        SubmissionFile.objects.create(submission=self.sub,file=SimpleUploadedFile('answer.txt',b'answer'),original_name='answer.txt')
        self.assertTrue(self.sub.has_content)
