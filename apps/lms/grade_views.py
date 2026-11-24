from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from apps.assignments.models import Assignment, AssignmentRecipient, Submission
from apps.learning import quiz_types
from apps.learning.models import Quiz, QuizRecipient, QuizAttempt
from apps.operations.access import is_admin, is_teacher, learner_student_ids, is_ta
from .access import staff_scope, can_manage, require_submission, require_attempt, visible_groups
from .documents import version_token, clean_annotations, document_is_current
from .document_views import annotator_data
from .forms import GradeForm
from .models import ReviewDocument
from .room_views import audit


def review_version(target):
    def score(value): return format(Decimal(value), ".2f") if value is not None else "null"
    if isinstance(target,Submission):
        raw=f'{version_token(target)}|{score(target.score)}|{target.feedback_at}|{target.feedback}'
    else:raw=f'{target.pk}|{target.submitted_at}|{score(target.manual_score)}|{target.feedback_at}|{target.feedback}'
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_submission(pk):
    return get_object_or_404(Submission.objects.select_related('recipient__assignment__group','recipient__assignment__created_by'),pk=pk)


INSTANT_PREVIEW={'.pdf','.png','.jpg','.jpeg','.webp'}
OFFICE_PREVIEW={'.doc','.docx','.ppt','.pptx','.xls','.xlsx','.odt','.odp','.rtf'}


def _review_files(submission,chosen,staff):
    """제출 파일마다 탭 하나: 원본 파일 → 추가 파일 → 텍스트 답안. 현재 제출본의 첨삭 문서가 있으면 함께 붙입니다.
    instant: 화면을 열 때 바로 첨삭 문서로 바꿔도 되는 파일(PDF·이미지·텍스트, 변환기가 있으면 Word·PPT도)."""
    converter=getattr(settings,'LMS_OFFICE_CONVERTER','')
    office=bool(converter) and Path(converter).is_file()
    def instant(name):
        suffix=Path(name).suffix.lower()
        return suffix in INSTANT_PREVIEW or (office and suffix in OFFICE_PREVIEW)
    files=[]
    if submission.attachment:
        label=submission.attachment_name or Path(submission.attachment.name).name
        files.append({'source':'primary','key':submission.attachment.name,'label':label,'instant':instant(label),
          'download':reverse('assignments:submission-attachment',args=[submission.pk]) if staff else reverse('assignments:my-submission-attachment',args=[submission.recipient_id])})
    for extra in submission.extra_files.all():
        files.append({'source':str(extra.pk),'key':extra.file.name,'label':extra.original_name,'instant':instant(extra.original_name),
          'download':reverse('lms:submission-file',args=[extra.pk])})
    if submission.text_answer.strip():
        files.append({'source':'text','key':'text','label':'텍스트 답안','instant':True,'download':None})
    docs={doc.source_key:doc for doc in submission.review_documents.filter(source_token=version_token(submission))}
    selected=next((f for f in files if f['source']==chosen),files[0] if files else None)
    for f in files:
        f['document']=docs.get(f['key']);f['selected']=f is selected
    return files,selected


def _switcher(assignment,current_pk):
    """제출한 학생 사이를 ◀ ▶ 로 이동합니다(이름순)."""
    submitted=[r for r in assignment.recipients.select_related('submission','assignment').order_by('student_name','pk') if r.submission_object]
    urls=[reverse('lms:submission-review',args=[r.submission_object.pk]) for r in submitted]
    index=next(i for i,r in enumerate(submitted) if r.submission_object.pk==current_pk)
    return {'position':index+1,'total':len(submitted),'graded':sum(1 for r in submitted if r.submission_object.feedback_at),
            'prev':urls[index-1] if index>0 else None,'next':urls[index+1] if index+1<len(urls) else None,
            'options':[{'url':url,'label':f'{r.student_name} · {r.status_label}','selected':i==index} for i,(r,url) in enumerate(zip(submitted,urls))]}


def _posted_marks(request,current):
    """'의견 제출'에 함께 실린 첨삭: (잠근 문서, 정리된 첨삭, 기준 판) 또는 오류 문구."""
    raw=request.POST.get('document')
    if not raw:return None,None
    if len(request.POST.get('annotations',''))>800_000:return None,'첨삭 데이터가 너무 큽니다.'
    try:
        doc=ReviewDocument.objects.select_for_update().get(pk=int(raw),submission=current)
        revision=int(request.POST['document_revision'])
        marks=clean_annotations(json.loads(request.POST['annotations']),doc.page_count)
    except ReviewDocument.DoesNotExist:
        return None,'이 학생의 제출 파일이 아닙니다. 화면을 새로고침해 주세요.'
    except ValidationError as exc:
        return None,exc.messages[0]
    except (KeyError,ValueError,TypeError):
        return None,'첨삭 입력을 확인하세요.'
    if not document_is_current(doc):return None,'학생 재제출이 먼저 저장되었습니다. 새 제출물을 열어 주세요.'
    if doc.revision!=revision:return None,'다른 사용자가 먼저 첨삭을 저장했습니다. 새로고침 전 입력 내용을 보관해 주세요.'
    return (doc,marks,revision),None


@login_required
def submission_review(request,submission_id):
    submission=_get_submission(submission_id)
    staff=require_submission(request.user,submission,write=request.method=='POST')
    assignment=submission.recipient.assignment
    version=review_version(submission)
    chosen=request.GET.get('file','')
    # Legacy feedback-only clients remain compatible; new UI always sends version.
    data=request.POST.copy() if request.method=='POST' else None
    if data is not None and 'version' not in data:
        data['version']=version
    form=GradeForm(data,maximum=assignment.points,initial={'score':submission.score,'feedback':submission.feedback,'version':version})
    if request.method=='POST' and form.is_valid():
        # '의견 제출': 첨삭·점수·총평을 한 번에 저장합니다. 하나라도 막히면 아무것도 저장하지 않습니다.
        with transaction.atomic():
            current=Submission.objects.select_for_update().select_related('recipient__assignment').get(pk=submission.pk)
            require_submission(request.user,current,write=True)
            if review_version(current)!=form.cleaned_data['version']:
                form.add_error(None,'다른 채점 또는 학생 재제출이 먼저 저장되었습니다. 입력 내용을 복사한 뒤 새로고침해 비교하세요.')
            else:
                marks,error=_posted_marks(request,current)
                if error:
                    form.add_error(None,error)
                else:
                    if marks:
                        doc,clean,revision=marks
                        ReviewDocument.objects.filter(pk=doc.pk).update(annotations=clean,revision=revision+1,updated_by=request.user,updated_at=timezone.now())
                        audit(request.user,'annotation.save',doc.pk,revision=revision+1,count=len(clean))
                    current.score=form.cleaned_data['score'];current.feedback=form.cleaned_data['feedback']
                    current.feedback_by=request.user;current.feedback_at=timezone.now()
                    current.save(update_fields=['score','feedback','feedback_by','feedback_at','updated_at'])
                    audit(request.user,'assignment.grade',current.pk,score=str(current.score) if current.score is not None else None)
                    messages.success(request,'의견을 제출했습니다. 학생·연결 학부모가 첨삭과 점수를 확인할 수 있습니다.')
                    # 11/19: 의견을 내면 그 과제의 제출 현황(학생 목록)으로 돌아갑니다
                    return redirect('assignments:detail',assignment_id=current.recipient.assignment_id)
    files,selected=_review_files(submission,chosen,staff)
    doc=selected and selected['document']
    context={'page_title':'제출물 검토','submission':submission,'recipient':submission.recipient,'assignment':assignment,
      'staff':staff,'form':form,'files':files,'selected_file':selected,
      'document_data':annotator_data(doc,editable=staff,mode='review') if doc else None,
      'history':[d for d in submission.review_documents.all() if not document_is_current(d)]}
    if staff:context['switcher']=_switcher(assignment,submission.pk)
    return render(request,'lms/review.html',context)


@login_required
def quiz_review(request,attempt_id):
    attempt=get_object_or_404(QuizAttempt.objects.select_related('recipient__quiz__group','recipient__quiz__created_by'),pk=attempt_id)
    staff=require_attempt(request.user,attempt,write=request.method=='POST')
    form=GradeForm(request.POST or None,maximum=attempt.max_score,initial={
      'score':attempt.manual_score,'feedback':attempt.feedback,'version':review_version(attempt)})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            current=QuizAttempt.objects.select_for_update().select_related('recipient__quiz').get(pk=attempt.pk)
            require_attempt(request.user,current,write=True)
            if review_version(current)!=form.cleaned_data['version']:
                form.add_error(None,'다른 채점이 먼저 저장되었습니다. 새로고침 후 비교해 주세요.')
            else:
                current.manual_score=form.cleaned_data['score'];current.feedback=form.cleaned_data['feedback']
                current.feedback_at=timezone.now();current.feedback_by=request.user
                current.save(update_fields=['manual_score','feedback','feedback_at','feedback_by'])
                audit(request.user,'quiz.grade',current.pk,score=str(current.manual_score) if current.manual_score is not None else None)
                messages.success(request,'퀴즈 점수와 총평을 저장했습니다. 자동채점 원점수는 보존됩니다.')
                return redirect('lms:quiz-review',current.pk)
    # 문항마다 부분별 '학생 답 · 정답'. 학생·학부모에게는 마감 뒤에만 정답을 보여 줍니다.
    show_expected=staff or attempt.recipient.quiz.is_closed
    answers=[]
    for answer in attempt.answers.select_related('question','selected_choice').prefetch_related('question__choices').order_by('question__order','pk'):
        question=answer.question
        rows=quiz_types.review(question,quiz_types.response_for(answer))
        if not show_expected and question.question_type==quiz_types.MULTI:
            rows=[row for row in rows if row['given']==quiz_types.PICKED]
        answers.append({'answer':answer,'question':question,'prompt':quiz_types.display_prompt(question),'rows':rows})
    return render(request,'lms/quiz_review.html',{'page_title':'퀴즈 채점·첨삭','attempt':attempt,'staff':staff,
      'form':form,'answers':answers,'show_expected':show_expected,'documents':attempt.review_documents.all()})


def _activity_columns(user,request):
    staff=is_admin(user) or is_teacher(user) or is_ta(user)
    assignments=Assignment.objects.select_related('group')
    quizzes=Quiz.objects.select_related('group')
    if staff:
        assignments=staff_scope(assignments,user);quizzes=staff_scope(quizzes,user)
    else:
        ids=learner_student_ids(user);now=timezone.now()
        assignments=assignments.filter(recipients__student_id__in=ids,is_published=True).filter(Q(available_from__isnull=True)|Q(available_from__lte=now)).distinct()
        quizzes=quizzes.filter(recipients__student_id__in=ids,is_published=True).filter(Q(available_from__isnull=True)|Q(available_from__lte=now)).distinct()
    gid=request.GET.get('group','')
    if gid:
        if gid.isdigit():assignments=assignments.filter(group_id=int(gid));quizzes=quizzes.filter(group_id=int(gid))
        elif gid=='none':assignments=assignments.filter(group__isnull=True);quizzes=quizzes.filter(group__isnull=True)
        else:assignments=assignments.none();quizzes=quizzes.none()
    q=request.GET.get('q','').strip()[:100]
    if q:assignments=assignments.filter(title__icontains=q);quizzes=quizzes.filter(title__icontains=q)
    kind=request.GET.get('kind','')
    if kind=='assignment':quizzes=quizzes.none()
    if kind=='quiz':assignments=assignments.none()
    item=request.GET.get('item','')
    if item:
        if item.startswith('a:') and item[2:].isdigit():assignments=assignments.filter(pk=int(item[2:]));quizzes=quizzes.none()
        elif item.startswith('q:') and item[2:].isdigit():quizzes=quizzes.filter(pk=int(item[2:]));assignments=assignments.none()
        else:assignments=assignments.none();quizzes=quizzes.none()
    # Bounded per-response columns; pagination never silently drops columns.
    columns=[{'key':f'a:{a.pk}','kind':'과제','obj':a,'title':a.title,'max':a.points,'due':a.due_at} for a in assignments]
    columns += [{'key':f'q:{q.pk}','kind':'퀴즈','obj':q,'title':q.title,'max':q.total_points,'due':q.due_at} for q in quizzes.prefetch_related('questions')]
    return sorted(columns,key=lambda c:(c['due'],c['key']),reverse=True),staff


@login_required
def gradebook(request):
    columns,staff=_activity_columns(request.user,request)
    cpage=Paginator(columns,12).get_page(request.GET.get('col_page'))
    aid=[c['obj'].pk for c in columns if c['key'].startswith('a:')]
    qid=[c['obj'].pk for c in columns if c['key'].startswith('q:')]
    ar=AssignmentRecipient.objects.filter(assignment_id__in=aid).select_related('assignment','submission')
    qr=QuizRecipient.objects.filter(quiz_id__in=qid).select_related('quiz').prefetch_related('attempts')
    if not staff:
        ids=learner_student_ids(request.user);ar=ar.filter(student_id__in=ids);qr=qr.filter(student_id__in=ids)
    search=request.GET.get('student','').strip()[:100]
    if search:
        ar=ar.filter(Q(student_name__icontains=search)|Q(student_id__icontains=search))
        qr=qr.filter(Q(student_name__icontains=search)|Q(student_id__icontains=search))
    names={};cells={}
    for r in ar:
        names[r.student_id]=r.student_name;s=r.submission_object
        cells[(r.student_id,f'a:{r.assignment_id}')]= {'status':r.status_label,'code':r.status_code,
          'score':s.score if s else None,'url':reverse('lms:submission-review',args=[s.pk]) if s else '',
          'feedback':s.feedback if s else '', 'attempt':None}
    for r in qr:
        names[r.student_id]=r.student_name;a=next((a for a in r.attempts.all() if a.submitted_at),None)
        cells[(r.student_id,f'q:{r.quiz_id}')]= {'status':('채점완료' if a else ('마감지남' if r.quiz.is_closed else '미응시')),
          'code':'FEEDBACK_COMPLETE' if a else ('OVERDUE' if r.quiz.is_closed else 'PENDING'),
          'score':a.final_score if a else None,'url':reverse('lms:quiz-review',args=[a.pk]) if a else '',
          'feedback':a.feedback if a else '', 'attempt':a.attempt_no if a else None}
    rpage=Paginator(sorted(names.items(),key=lambda x:(x[1],x[0])),30).get_page(request.GET.get('page'))
    rows=[{'id':sid,'name':name,'cells':[cells.get((sid,c['key'])) for c in cpage]} for sid,name in rpage]
    params=request.GET.copy();params.pop('page',None);row_query=params.urlencode()
    params=request.GET.copy();params.pop('col_page',None);col_query=params.urlencode()
    return render(request,'lms/gradebook.html',{'page_title':'과제·퀴즈 성적 및 제출 현황','rows':rows,
      'columns':cpage,'row_page':rpage,'column_count':len(columns),'student_count':len(names),
      'groups':visible_groups(request.user),'filters':request.GET,'row_query':row_query,'col_query':col_query,
      'items':columns,'staff':staff})
